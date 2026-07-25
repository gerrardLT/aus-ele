from __future__ import annotations

from math import sqrt

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import csr_matrix

# Default rolling foresight horizon. A single year-long perfect-foresight solve
# is methodologically unrealistic (real operators dispatch against a limited
# forecast horizon, e.g. AEMO pre-dispatch / ST-PASA). We therefore solve the
# arbitrage problem with a receding-horizon (MPC) scheme: at each step we solve
# over [commit horizon + lookahead buffer] but only *commit* the first
# ``window_hours`` of decisions, carry the resulting state-of-charge forward,
# and roll on. The lookahead buffer means the committed portion is optimized
# with knowledge of near-future prices, which eliminates the terminal-value
# "end-effect" (liquidating stored energy at every window boundary) that a
# naive non-overlapping window suffers from, while still capturing the
# realistic limited-foresight haircut versus perfect hindsight.
DEFAULT_FORESIGHT_WINDOW_HOURS = 24.0
DEFAULT_LOOKAHEAD_HOURS = 24.0

# B5 scale guard: the minimum-duration MILP coupling generates O(n *
# min_duration) constraint rows. Beyond this many rows we degrade to the LP
# relaxation for tractability rather than stalling the solve. Normal ~24h
# windows are orders of magnitude below this ceiling, so this never engages on
# realistic horizons.
MILP_MAX_MIN_DURATION_CONSTRAINTS = 200_000

# The per-interval "no simultaneous charge and discharge" rule is enforced in a
# mixed-integer formulation by a binary variable. That binary is mathematically
# redundant here: with any round-trip loss (eta < 1) or any positive per-MWh
# discharge cost, charging and discharging in the same interval is strictly
# dominated (it burns energy and/or incurs cost for zero net-revenue gain), so
# the linear-programming relaxation is exact. Solving the LP in-process with
# HiGHS (scipy) instead of spawning a CBC subprocess per window makes the
# full-year rolling backtest tractable (seconds instead of minutes).


def _empty_result(params) -> dict:
    return {
        "timeline": [],
        "summary": {
            "soc_start_mwh": params.initial_soc_mwh,
            "soc_end_mwh": params.initial_soc_mwh,
            "soc_min_mwh": params.initial_soc_mwh,
            "soc_max_mwh": params.initial_soc_mwh,
            "charge_throughput_mwh": 0.0,
            "discharge_throughput_mwh": 0.0,
            "equivalent_cycles": 0.0,
            "gross_revenue": 0.0,
            "net_revenue": 0.0,
            "costs": {
                "network_fees": 0.0,
                "degradation": 0.0,
                "variable_om": 0.0,
            },
            "warnings": ["no_intervals"],
            "foresight_window_hours": 0.0,
            "window_count": 0,
        },
    }


def _window_boundaries(intervals: list[dict], window_hours: float) -> list[tuple[int, int]]:
    """Return consecutive commit-window ``(start, end)`` index ranges (end exclusive).

    Splitting by accumulated interval time (rather than parsing timestamps) is
    robust to data gaps and DST transitions, and keeps ~24h daily windows
    aligned for regular 5-minute or 30-minute price series. A non-positive
    *window_hours* collapses to a single window (full perfect-foresight).
    """
    if window_hours <= 0:
        return [(0, len(intervals))]

    bounds: list[tuple[int, int]] = []
    start = 0
    acc = 0.0
    for i, row in enumerate(intervals):
        acc += float(row.get("interval_hours", 5.0 / 60.0))
        if acc >= window_hours - 1e-9:
            bounds.append((start, i + 1))
            start = i + 1
            acc = 0.0
    if start < len(intervals):
        bounds.append((start, len(intervals)))
    return bounds


def _effective_power_limits(params) -> tuple[float, float]:
    """Resolve independent charge/discharge power ceilings.

    A BESS can be de-rated asymmetrically (inverter/thermal limits often differ
    between charge and discharge). When the optional ``max_charge_mw`` /
    ``max_discharge_mw`` are unset they fall back to the symmetric ``power_mw``
    rating, which reproduces the original single-limit behaviour exactly.
    """
    max_charge = getattr(params, "max_charge_mw", None)
    max_discharge = getattr(params, "max_discharge_mw", None)
    return (
        params.power_mw if max_charge is None else float(max_charge),
        params.power_mw if max_discharge is None else float(max_discharge),
    )


def _intervals_per_block(params, interval_hours: list[float]) -> int:
    """How many price intervals must share a single dispatch decision.

    Market gate-closure can force dispatch to stay constant over a coarser grid
    than the settlement resolution (e.g. 30-minute bids on 5-minute prices).
    An unset alignment (or one that is <= a single interval) keeps full
    per-interval freedom, i.e. no alignment coupling.
    """
    alignment = getattr(params, "dispatch_alignment_minutes", None)
    if not alignment or not interval_hours:
        return 1
    interval_minutes = interval_hours[0] * 60.0
    if interval_minutes <= 0:
        return 1
    return max(1, int(round(float(alignment) / interval_minutes)))


def _extract_window_rows(
    params,
    intervals: list[dict],
    interval_hours: list[float],
    prices: list[float],
    x,
    c_off: int,
    d_off: int,
    s_off: int,
) -> list[dict]:
    """Turn a solved variable vector into per-interval revenue/cost rows."""
    rows_out: list[dict] = []
    for i, row_data in enumerate(intervals):
        dt = interval_hours[i]
        charge_mw = max(0.0, float(x[c_off + i]))
        discharge_mw = max(0.0, float(x[d_off + i]))
        soc_mwh = float(x[s_off + i])
        charge_mwh = charge_mw * dt
        discharge_mwh = discharge_mw * dt
        interval_gross_revenue = (discharge_mwh - charge_mwh) * prices[i]
        interval_network_fees = discharge_mwh * params.network_fee_per_mwh
        interval_degradation = discharge_mwh * params.degradation_cost_per_mwh
        interval_variable_om = discharge_mwh * params.variable_om_per_mwh
        interval_net_revenue = (
            interval_gross_revenue
            - interval_network_fees
            - interval_degradation
            - interval_variable_om
        )

        rows_out.append(
            {
                "timestamp": row_data.get("timestamp"),
                "price": prices[i],
                "interval_hours": dt,
                "charge_mw": charge_mw,
                "discharge_mw": discharge_mw,
                "charge_mwh": charge_mwh,
                "discharge_mwh": discharge_mwh,
                "soc_mwh": soc_mwh,
                "gross_revenue": interval_gross_revenue,
                "net_revenue": interval_net_revenue,
                "network_fees": interval_network_fees,
                "degradation": interval_degradation,
                "variable_om": interval_variable_om,
            }
        )

    return rows_out


def _solve_window(
    params,
    intervals: list[dict],
    start_soc: float,
    force_end_soc: float | None,
    warnings_sink: list[str] | None = None,
) -> list[dict]:
    """Optimize charge/discharge for a single solve horizon.

    The base formulation is a pure LP over variables [charge(n), discharge(n),
    soc(n)] solved with HiGHS. Optional market/physical constraints extend it:

    * ``max_charge_mw`` / ``max_discharge_mw`` -- independent power ceilings
      (LP variable bounds); default to the symmetric ``power_mw`` rating.
    * ``auxiliary_power_mw`` -- parasitic self-consumption drained from SoC each
      interval (folded into the SoC-balance right-hand side).
    * ``registered_capacity_mw`` -- cap on simultaneous charge+discharge
      headroom (LP inequality).
    * ``min_duration_intervals`` / ``dispatch_alignment_minutes`` -- require a
      binary charging-mode variable, so they switch the solve to a MILP (scipy
      HiGHS branch-and-bound) with a per-interval ``is_charging`` binary and
      mutual-exclusion coupling. These are engaged **only** when set beyond
      their no-op defaults, so the common case stays on the fast LP path with
      zero behavioural or performance change.

    ``start_soc`` carries the state of charge from the previous commit;
    ``force_end_soc`` pins the terminal SoC (used only on the final commit
    window to keep the whole horizon energy-neutral). Returns per-interval rows
    for the *entire* solve horizon; the caller commits only the leading portion.
    """
    eta = sqrt(params.round_trip_efficiency)
    min_soc_mwh = params.energy_mwh * (params.min_soc_pct / 100.0)
    max_soc_mwh = params.energy_mwh * (params.max_soc_pct / 100.0)
    unit_discharge_cost = (
        params.network_fee_per_mwh
        + params.degradation_cost_per_mwh
        + params.variable_om_per_mwh
    )

    interval_hours = [float(row.get("interval_hours", 5.0 / 60.0)) for row in intervals]
    prices = [float(row.get("price", 0.0)) for row in intervals]
    window_days = sum(interval_hours) / 24.0
    throughput_limit_mwh = params.max_cycles_per_day * window_days * params.energy_mwh

    max_charge_mw, max_discharge_mw = _effective_power_limits(params)
    aux_power_mw = float(getattr(params, "auxiliary_power_mw", 0.0) or 0.0)
    registered_capacity_mw = getattr(params, "registered_capacity_mw", None)
    min_duration_intervals = int(getattr(params, "min_duration_intervals", 1) or 1)
    intervals_per_block = _intervals_per_block(params, interval_hours)
    needs_binary = min_duration_intervals > 1 or intervals_per_block > 1
    if (
        needs_binary
        and min_duration_intervals > 1
        and len(intervals) * min_duration_intervals > MILP_MAX_MIN_DURATION_CONSTRAINTS
    ):
        # Degrade to the LP relaxation (drop the min-duration / alignment
        # coupling) rather than let the MILP blow up on a pathologically long
        # solve horizon. Surfaced as a warning so the caller can flag it.
        if warnings_sink is not None:
            warnings_sink.append("milp_downgraded_to_lp_scale_guard")
        min_duration_intervals = 1
        intervals_per_block = 1
        needs_binary = False

    n = len(intervals)
    c_off = 0
    d_off = n
    s_off = 2 * n
    b_off = 3 * n  # is_charging column offset (MILP path only)
    num_vars = 4 * n if needs_binary else 3 * n

    # Objective: maximize net revenue -> minimize -net_revenue.
    obj = np.zeros(num_vars)
    for i in range(n):
        dt = interval_hours[i]
        obj[c_off + i] = dt * prices[i]  # -(-charge*dt*price)
        obj[d_off + i] = -dt * (prices[i] - unit_discharge_cost)

    # SoC dynamics (equalities): soc_i - eta*dt*charge_i + (dt/eta)*discharge_i
    #   - soc_{i-1} = (start_soc if i == 0 else 0) - aux_power*dt. The auxiliary
    #   term drains a fixed parasitic load from stored energy every interval.
    eq_rows: list[int] = []
    eq_cols: list[int] = []
    eq_data: list[float] = []
    b_eq: list[float] = []
    for i in range(n):
        dt = interval_hours[i]
        row = len(b_eq)
        eq_rows.append(row); eq_cols.append(s_off + i); eq_data.append(1.0)
        eq_rows.append(row); eq_cols.append(c_off + i); eq_data.append(-eta * dt)
        eq_rows.append(row); eq_cols.append(d_off + i); eq_data.append(dt / eta)
        aux_drain = aux_power_mw * dt
        if i == 0:
            b_eq.append(start_soc - aux_drain)
        else:
            eq_rows.append(row); eq_cols.append(s_off + i - 1); eq_data.append(-1.0)
            b_eq.append(-aux_drain)

    if force_end_soc is not None:
        row = len(b_eq)
        eq_rows.append(row); eq_cols.append(s_off + n - 1); eq_data.append(1.0)
        b_eq.append(force_end_soc)

    # Dispatch alignment (equalities): every interval in a block shares its
    # block-leader's charging state. Needs the binary -> MILP path only.
    if needs_binary and intervals_per_block > 1:
        num_blocks = (n + intervals_per_block - 1) // intervals_per_block
        for block_idx in range(num_blocks):
            block_start = block_idx * intervals_per_block
            block_end = min(block_start + intervals_per_block, n)
            for i in range(block_start + 1, block_end):
                row = len(b_eq)
                eq_rows.append(row); eq_cols.append(b_off + i); eq_data.append(1.0)
                eq_rows.append(row); eq_cols.append(b_off + block_start); eq_data.append(-1.0)
                b_eq.append(0.0)

    # Inequalities, all expressed as A_ub @ x <= b_ub.
    ub_rows: list[int] = []
    ub_cols: list[int] = []
    ub_data: list[float] = []
    b_ub: list[float] = []

    # Charge-throughput (cycle-life) limit: sum_i dt_i * charge_i <= limit.
    tp_row = len(b_ub)
    for i in range(n):
        ub_rows.append(tp_row); ub_cols.append(c_off + i); ub_data.append(interval_hours[i])
    b_ub.append(throughput_limit_mwh)

    # Registered capacity: charge_i + discharge_i <= registered_capacity_mw.
    if registered_capacity_mw is not None:
        for i in range(n):
            row = len(b_ub)
            ub_rows.append(row); ub_cols.append(c_off + i); ub_data.append(1.0)
            ub_rows.append(row); ub_cols.append(d_off + i); ub_data.append(1.0)
            b_ub.append(float(registered_capacity_mw))

    if needs_binary:
        # Mutual exclusion tying the binary to real dispatch:
        #   charge_i <= max_charge * is_charging_i            (-> c_i - Mc*b_i <= 0)
        #   discharge_i <= max_discharge * (1 - is_charging_i)(-> d_i + Md*b_i <= Md)
        for i in range(n):
            row = len(b_ub)
            ub_rows.append(row); ub_cols.append(c_off + i); ub_data.append(1.0)
            ub_rows.append(row); ub_cols.append(b_off + i); ub_data.append(-max_charge_mw)
            b_ub.append(0.0)

            row = len(b_ub)
            ub_rows.append(row); ub_cols.append(d_off + i); ub_data.append(1.0)
            ub_rows.append(row); ub_cols.append(b_off + i); ub_data.append(max_discharge_mw)
            b_ub.append(max_discharge_mw)

        # Minimum duration: after a mode switch at i, hold the new mode for
        # min_duration_intervals consecutive intervals. Linearized exactly as
        # the reference MILP formulation.
        if min_duration_intervals > 1:
            for i in range(1, n):
                for j in range(i + 1, min(i + min_duration_intervals, n)):
                    # b_j >= b_i - b_{i-1}  ->  -b_j + b_i - b_{i-1} <= 0
                    row = len(b_ub)
                    ub_rows.append(row); ub_cols.append(b_off + j); ub_data.append(-1.0)
                    ub_rows.append(row); ub_cols.append(b_off + i); ub_data.append(1.0)
                    ub_rows.append(row); ub_cols.append(b_off + i - 1); ub_data.append(-1.0)
                    b_ub.append(0.0)
                    # b_j <= 1 - (b_{i-1} - b_i)  ->  b_j + b_{i-1} - b_i <= 1
                    row = len(b_ub)
                    ub_rows.append(row); ub_cols.append(b_off + j); ub_data.append(1.0)
                    ub_rows.append(row); ub_cols.append(b_off + i - 1); ub_data.append(1.0)
                    ub_rows.append(row); ub_cols.append(b_off + i); ub_data.append(-1.0)
                    b_ub.append(1.0)

    a_eq = csr_matrix((eq_data, (eq_rows, eq_cols)), shape=(len(b_eq), num_vars))
    a_ub = csr_matrix((ub_data, (ub_rows, ub_cols)), shape=(len(b_ub), num_vars))

    lb = np.zeros(num_vars)
    ub = np.empty(num_vars)
    ub[c_off:c_off + n] = max_charge_mw
    ub[d_off:d_off + n] = max_discharge_mw
    lb[s_off:s_off + n] = min_soc_mwh
    ub[s_off:s_off + n] = max_soc_mwh
    if needs_binary:
        ub[b_off:b_off + n] = 1.0

    if needs_binary:
        integrality = np.zeros(num_vars)
        integrality[b_off:b_off + n] = 1
        constraints = [LinearConstraint(a_ub, -np.inf, np.asarray(b_ub, dtype=float))]
        if len(b_eq):
            beq = np.asarray(b_eq, dtype=float)
            constraints.append(LinearConstraint(a_eq, beq, beq))
        result = milp(
            c=obj,
            constraints=constraints,
            integrality=integrality,
            bounds=Bounds(lb, ub),
        )
        if not result.success or result.x is None:
            raise RuntimeError(f"Backtest MILP solve failed: {result.message}")
        x = result.x
    else:
        bounds = list(zip(lb.tolist(), ub.tolist()))
        result = linprog(
            c=obj,
            A_ub=a_ub,
            b_ub=b_ub,
            A_eq=a_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs",
        )
        if not result.success:
            raise RuntimeError(f"Backtest solve failed: {result.message}")
        x = result.x

    return _extract_window_rows(
        params, intervals, interval_hours, prices, x, c_off, d_off, s_off
    )


def run_bess_backtest_v1(
    params,
    intervals: list[dict],
    window_hours: float = DEFAULT_FORESIGHT_WINDOW_HOURS,
    lookahead_hours: float | None = None,
    compute_perfect_foresight_benchmark: bool = False,
) -> dict:
    """Optimized-hindsight arbitrage backtest with receding-horizon foresight.

    The horizon is split into consecutive commit windows of ``window_hours``.
    Each step solves an LP over the commit window plus a ``lookahead_hours``
    buffer of subsequent prices, but only the commit window's decisions are
    kept and the resulting state-of-charge is carried into the next step. The
    lookahead buffer gives the committed decisions realistic near-future
    knowledge without perfect year-ahead foresight, and avoids the
    terminal-value end-effect of naive non-overlapping windows. Only the final
    commit window pins its terminal SoC back to the initial level, keeping the
    whole horizon energy-neutral. Passing a non-positive ``window_hours``
    recovers the single full-horizon perfect-foresight solve (the denominator
    for the industry-standard "% of perfect foresight" metric).
    """
    if not intervals:
        return _empty_result(params)

    if lookahead_hours is None:
        lookahead_hours = DEFAULT_LOOKAHEAD_HOURS

    initial_soc_mwh = params.initial_soc_mwh
    interval_hours_all = [float(row.get("interval_hours", 5.0 / 60.0)) for row in intervals]
    bounds = _window_boundaries(intervals, window_hours)

    timeline: list[dict] = []
    warnings: list[str] = []
    start_soc = initial_soc_mwh
    last_index = len(bounds) - 1
    terminal_relaxed = False
    for w_idx, (start, end) in enumerate(bounds):
        is_final = w_idx == last_index
        # Extend the solve horizon with a lookahead buffer of future intervals
        # so the committed decisions are not distorted by an artificial
        # zero-value terminal state. The buffer's own decisions are discarded.
        solve_end = end
        if not is_final and window_hours > 0:
            acc = 0.0
            j = end
            while j < len(intervals) and acc < lookahead_hours - 1e-9:
                acc += interval_hours_all[j]
                j += 1
            solve_end = j
        force_end_soc = initial_soc_mwh if is_final else None
        try:
            solved_rows = _solve_window(
                params, intervals[start:solve_end], start_soc, force_end_soc, warnings
            )
        except RuntimeError:
            # Pinning the terminal SoC back to the initial level can be
            # infeasible on a degenerate final window (e.g. a large data gap
            # leaves only a couple of short intervals that cannot move the SoC
            # far enough within the power limit). Real contiguous horizons end
            # on a full day and never hit this. Degrade gracefully by relaxing
            # the energy-neutrality constraint rather than failing the run.
            if force_end_soc is None:
                raise
            solved_rows = _solve_window(
                params, intervals[start:solve_end], start_soc, None, warnings
            )
            terminal_relaxed = True
        commit_len = end - start
        committed_rows = solved_rows[:commit_len]
        timeline.extend(committed_rows)
        start_soc = committed_rows[-1]["soc_mwh"]

    totals = {
        "gross": 0.0,
        "net": 0.0,
        "network_fees": 0.0,
        "degradation": 0.0,
        "variable_om": 0.0,
        "charge": 0.0,
        "discharge": 0.0,
    }
    for row in timeline:
        totals["gross"] += row["gross_revenue"]
        totals["net"] += row["net_revenue"]
        totals["network_fees"] += row["network_fees"]
        totals["degradation"] += row["degradation"]
        totals["variable_om"] += row["variable_om"]
        totals["charge"] += row["charge_mwh"]
        totals["discharge"] += row["discharge_mwh"]

    realized_charge = totals["charge"]
    realized_discharge = totals["discharge"]

    # B1: apply the availability derate. Forced outages and scheduled
    # maintenance make a real BESS unavailable a few percent of the time.
    # Assuming outages are uncorrelated with price, expected revenue, operating
    # cost and energy throughput all scale by the availability factor. SoC
    # levels and the per-interval dispatch timeline are the optimizer's physical
    # trajectory and are left unscaled; only the aggregated expected-value
    # summary is derated. A default availability of 100% reproduces the previous
    # figures exactly (zero regression).
    availability_factor = max(0.0, min(1.0, params.availability_pct / 100.0))

    gross_revenue = totals["gross"] * availability_factor
    net_revenue = totals["net"] * availability_factor
    cost_network_fees = totals["network_fees"] * availability_factor
    cost_degradation = totals["degradation"] * availability_factor
    cost_variable_om = totals["variable_om"] * availability_factor
    charge_throughput = realized_charge * availability_factor
    discharge_throughput = realized_discharge * availability_factor
    equivalent_cycles = (
        discharge_throughput / params.energy_mwh if params.energy_mwh else 0.0
    )

    if terminal_relaxed:
        warnings.append("terminal_soc_neutrality_relaxed")

    # B4: "% of perfect foresight" -- the industry-standard confidence metric.
    # Re-solve the identical horizon as a single perfect-foresight window (the
    # theoretical upper bound) and report the realistic receding-horizon result
    # as a fraction of it. The availability derate cancels in the ratio, so it
    # is computed on the derated net figures directly. Gated behind a flag to
    # avoid doubling solve cost on the default path.
    pct_of_perfect_foresight = None
    if compute_perfect_foresight_benchmark and window_hours > 0:
        benchmark = run_bess_backtest_v1(
            params,
            intervals,
            window_hours=0.0,
            lookahead_hours=None,
            compute_perfect_foresight_benchmark=False,
        )
        perfect_net = benchmark["summary"]["net_revenue"]
        if perfect_net is not None and abs(perfect_net) > 1e-9:
            pct_of_perfect_foresight = net_revenue / perfect_net

    return {
        "timeline": timeline,
        "summary": {
            "soc_start_mwh": initial_soc_mwh,
            "soc_end_mwh": timeline[-1]["soc_mwh"] if timeline else initial_soc_mwh,
            "soc_min_mwh": min(item["soc_mwh"] for item in timeline),
            "soc_max_mwh": max(item["soc_mwh"] for item in timeline),
            "charge_throughput_mwh": charge_throughput,
            "discharge_throughput_mwh": discharge_throughput,
            "equivalent_cycles": equivalent_cycles,
            "gross_revenue": gross_revenue,
            "net_revenue": net_revenue,
            "costs": {
                "network_fees": cost_network_fees,
                "degradation": cost_degradation,
                "variable_om": cost_variable_om,
            },
            "warnings": warnings,
            "availability_pct": params.availability_pct,
            "availability_applied": True,
            "pct_of_perfect_foresight": pct_of_perfect_foresight,
            "foresight_window_hours": window_hours,
            "lookahead_hours": lookahead_hours if window_hours > 0 else 0.0,
            "window_count": len(bounds),
        },
    }
