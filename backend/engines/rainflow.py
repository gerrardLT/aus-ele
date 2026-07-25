"""Rainflow cycle counting (ASTM E1049-85) for battery degradation.

Battery cycle-life degradation depends not on how *often* the battery cycles
but on the *depth* of each charge/discharge cycle (DoD). Counting equivalent
full cycles from raw throughput ignores this. The rainflow algorithm — the
standard method in fatigue analysis and the accepted approach for battery
degradation (Shi et al. 2017; DTU cycle-calendar models) — decomposes an
arbitrary State-of-Charge trajectory into a set of (depth, count) cycles.

This module provides:
- ``count_cycles``: the ASTM E1049 rainflow decomposition of a signal.
- ``dod_severity_from_soc``: converts a SoC trajectory into an equivalent
  full-cycle count and a DoD-severity multiplier used by the degradation model.
"""

from __future__ import annotations

from typing import List, Tuple


def _turning_points(series: List[float]) -> List[float]:
    """Reduce a signal to its turning points (local extrema).

    Consecutive equal values are collapsed; interior points that are not
    reversals are dropped. Endpoints are always retained.
    """
    if not series:
        return []
    pts = [series[0]]
    for value in series[1:]:
        if value != pts[-1]:
            pts.append(value)
    if len(pts) < 3:
        return pts
    reduced = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev_d = pts[i] - pts[i - 1]
        next_d = pts[i + 1] - pts[i]
        # Keep only reversals (sign change in slope).
        if (prev_d > 0) != (next_d > 0):
            reduced.append(pts[i])
    reduced.append(pts[-1])
    return reduced


def count_cycles(series: List[float]) -> List[Tuple[float, float]]:
    """Rainflow-count a signal into ``(range, count)`` pairs.

    Implements the ASTM E1049-85 four-point / stack algorithm. ``count`` is
    ``1.0`` for a full cycle and ``0.5`` for a half (residual) cycle. ``range``
    is the peak-to-trough amplitude in the same units as the input.
    """
    points = _turning_points([float(v) for v in series])
    if len(points) < 2:
        return []

    cycles: List[Tuple[float, float]] = []
    stack: List[float] = []

    for point in points:
        stack.append(point)
        while len(stack) >= 3:
            x = abs(stack[-1] - stack[-2])
            y = abs(stack[-2] - stack[-3])
            if x < y:
                break
            if len(stack) == 3:
                # Range Y is a half cycle; discard the oldest point.
                cycles.append((y, 0.5))
                stack.pop(0)
            else:
                # Range Y is a full cycle; remove the two middle points.
                cycles.append((y, 1.0))
                del stack[-2]
                del stack[-2]

    # Remaining ranges in the stack are half cycles.
    for i in range(len(stack) - 1):
        cycles.append((abs(stack[i + 1] - stack[i]), 0.5))

    return cycles


def dod_severity_from_soc(
    soc_series: List[float],
    capacity_mwh: float,
    non_linear_factor: float = 1.2,
) -> Tuple[float, float]:
    """Derive equivalent full cycles and a DoD-severity multiplier from SoC.

    Args:
        soc_series: State-of-charge trajectory in MWh.
        capacity_mwh: Usable energy capacity (MWh) used to normalise DoD.
        non_linear_factor: Wöhler-style exponent ``b`` (>1) capturing that
            deeper cycles degrade more per unit of throughput.

    Returns:
        ``(equivalent_full_cycles, dod_severity)`` where:
        - ``equivalent_full_cycles`` = Σ(count·DoD) — throughput in full cycles.
        - ``dod_severity`` = Σ(count·DoD^b) / Σ(count·DoD), normalised so a
          trajectory of only full-depth cycles yields ``1.0``. Shallow-cycle
          trajectories yield ``<1.0``; a mix skewed to deep cycles ``>= 1.0``.
    """
    if capacity_mwh <= 0 or len(soc_series) < 2:
        return 0.0, 1.0

    cycles = count_cycles(soc_series)
    if not cycles:
        return 0.0, 1.0

    b = max(1.0, float(non_linear_factor))
    throughput = 0.0  # Σ count · DoD
    weighted = 0.0    # Σ count · DoD^b
    for rng, count in cycles:
        dod = min(1.0, rng / capacity_mwh)
        if dod <= 0:
            continue
        throughput += count * dod
        weighted += count * (dod ** b)

    if throughput <= 0:
        return 0.0, 1.0

    dod_severity = weighted / throughput
    return throughput, dod_severity
