import { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Bar,
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  buildInvestmentRequestKey,
  formatPercentageValue,
  getInvestmentCopy,
  shouldAutoRunInvestment,
} from '../lib/investmentAnalysis';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';

const PRESET_DEFAULTS = {
  power_mw: 100,
  duration_hours: 4,
  round_trip_efficiency: 0.87,
  degradation_rate: 0.025,
  capex_per_kwh: 350,
  fixed_om_per_mw_year: 12000,
  variable_om_per_mwh: 2.5,
  grid_connection_cost: 5000000,
  land_lease_per_year: 200000,
  discount_rate: 0.08,
  project_life_years: 20,
  revenue_capture_rate: 0.65,
  fcas_revenue_per_mw_year: 15000,
  fcas_revenue_mode: 'auto',
  capacity_payment_per_mw_year: 0,
  backtest_years: [2024, 2025],
  monte_carlo_enabled: false,
  forecast_inefficiency: 0.15,
  fcas_activation_probability: 0.15,
  cost_of_debt: 0.06,
  target_dscr: 1.30,
  debt_tenor_years: 15,
};

const FIELD_GROUPS = [
  {
    titleKey: 'storage',
    fields: [
      { key: 'power_mw', labelKey: 'power_mw', step: 10, min: 1, suffix: 'MW' },
      { key: 'duration_hours', labelKey: 'duration_hours', step: 1, min: 1, suffix: 'h' },
      { key: 'degradation_rate', labelKey: 'degradation_rate', step: 0.005, min: 0, suffix: '%/yr', pct: true },
      { key: 'revenue_capture_rate', labelKey: 'revenue_capture_rate', step: 0.05, min: 0, max: 1, suffix: '%', pct: true },
    ],
  },
  {
    titleKey: 'cost',
    fields: [
      { key: 'capex_per_kwh', labelKey: 'capex_per_kwh', step: 10, min: 0, suffix: '$/kWh' },
      { key: 'fixed_om_per_mw_year', labelKey: 'fixed_om_per_mw_year', step: 1000, min: 0, suffix: '$/MW/yr' },
      { key: 'variable_om_per_mwh', labelKey: 'variable_om_per_mwh', step: 0.5, min: 0, suffix: '$/MWh' },
      { key: 'grid_connection_cost', labelKey: 'grid_connection_cost', step: 500000, min: 0, suffix: '$' },
      { key: 'land_lease_per_year', labelKey: 'land_lease_per_year', step: 50000, min: 0, suffix: '$/yr' },
    ],
  },
  {
    titleKey: 'finance',
    fields: [
      { key: 'discount_rate', labelKey: 'discount_rate', step: 0.01, min: 0, max: 1, suffix: '%', pct: true },
      { key: 'project_life_years', labelKey: 'project_life_years', step: 1, min: 1, suffix: 'yr' },
      { key: 'fcas_revenue_per_mw_year', labelKey: 'fcas_revenue_per_mw_year', step: 5000, min: 0, suffix: '$/MW/yr' },
      { key: 'capacity_payment_per_mw_year', labelKey: 'capacity_payment_per_mw_year', step: 10000, min: 0, suffix: '$/MW/yr' },
      { key: 'forecast_inefficiency', labelKey: 'forecast_inefficiency', step: 0.05, min: 0, max: 1, suffix: '%', pct: true, label: 'Forecast Loss' },
      { key: 'fcas_activation_probability', labelKey: 'fcas_activation_probability', step: 0.05, min: 0, max: 1, suffix: '%', pct: true, label: 'FCAS Activation' },
    ],
  },
  {
    titleKey: 'Project Finance',
    fields: [
      { key: 'cost_of_debt', labelKey: 'cost_of_debt', step: 0.01, min: 0, max: 1, suffix: '%', pct: true, label: 'Cost of Debt' },
      { key: 'target_dscr', labelKey: 'target_dscr', step: 0.05, min: 1, max: 3, suffix: 'x', label: 'Target DSCR' },
      { key: 'debt_tenor_years', labelKey: 'debt_tenor_years', step: 1, min: 1, suffix: 'yr', label: 'Debt Tenor' },
    ],
  },
];

function fmt(value, prefix = '$') {
  if (value === null || value === undefined) return '-';
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${prefix}${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${prefix}${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${prefix}${(value / 1e3).toFixed(0)}K`;
  return `${prefix}${Number(value).toLocaleString()}`;
}

function getDefaultMode(region) {
  return region === 'WEM' ? 'manual' : 'auto';
}

export default function InvestmentAnalysis({ region, year, lang = 'en', t, scopeNote }) {
  const sectionRef = useRef(null);
  const requestControllerRef = useRef(null);
  const requestSeqRef = useRef(0);
  const [params, setParams] = useState({
    ...PRESET_DEFAULTS,
    fcas_revenue_mode: getDefaultMode(region),
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isVisible, setIsVisible] = useState(false);
  const [loadedKey, setLoadedKey] = useState(null);
  const requestKey = buildInvestmentRequestKey(region);
  const copy = useMemo(() => getInvestmentCopy(lang, t), [lang, t]);

  useEffect(() => {
    const node = sectionRef.current;
    if (!node) return undefined;

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry.isIntersecting);
      },
      {
        threshold: 0.15,
        rootMargin: '0px 0px -10% 0px',
      },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setParams((prev) => ({
      ...prev,
      fcas_revenue_mode: getDefaultMode(region),
    }));
    setResult(null);
    setError(null);
    setLoadedKey(null);
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    setLoading(false);
  }, [region]);

  useEffect(() => (
    () => {
      requestControllerRef.current?.abort();
    }
  ), []);

  async function runAnalysis(nextParams = params) {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    requestSeqRef.current += 1;
    const seq = requestSeqRef.current;
    const requestKeyForRun = buildInvestmentRequestKey(region);

    setLoading(true);
    setError(null);

    try {
      const body = {
        region,
        battery: {
          power_mw: nextParams.power_mw,
          duration_hours: nextParams.duration_hours,
          round_trip_efficiency: nextParams.round_trip_efficiency,
        },
        financial: {
          capex_per_kwh: nextParams.capex_per_kwh,
          fixed_om_per_mw_year: nextParams.fixed_om_per_mw_year,
          variable_om_per_mwh: nextParams.variable_om_per_mwh,
          grid_connection_cost: nextParams.grid_connection_cost,
          land_lease_per_year: nextParams.land_lease_per_year,
          discount_rate: nextParams.discount_rate,
          project_life_years: nextParams.project_life_years,
          capacity_payment_per_mw_year: nextParams.capacity_payment_per_mw_year,
        },
        revenue_capture_rate: nextParams.revenue_capture_rate,
        fcas_revenue_per_mw_year: nextParams.fcas_revenue_per_mw_year,
        fcas_revenue_mode: nextParams.fcas_revenue_mode,
        monte_carlo: {
          enabled: nextParams.monte_carlo_enabled,
          iterations: 100
        }
      };

      const response = await fetch(`${API_BASE}/investment-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || data.detail || 'Request failed');
      }

      setResult(data);
      setLoadedKey(requestKeyForRun);
    } catch (err) {
      if (err.name === 'AbortError') {
        return;
      }
      setError(err.message);
    } finally {
      if (requestSeqRef.current === seq) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    if (!shouldAutoRunInvestment({
      isVisible,
      isLoading: loading,
      requestKey,
      loadedKey,
    })) {
      return;
    }

    runAnalysis({
      ...params,
      fcas_revenue_mode: getDefaultMode(region),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVisible, requestKey, loadedKey, loading]);

  const cashFlows = result?.scenarios?.[0]?.cash_flows?.filter((row) => row.year > 0) || [];
  const metrics = result?.base_metrics || {};
  const mc = result?.monte_carlo;

  const capexPreview = useMemo(() => (
    (params.capex_per_kwh * params.power_mw * params.duration_hours * 1000) + params.grid_connection_cost
  ), [params]);

  const updateNumericParam = (key, value) => {
    const nextValue = value === '' ? '' : Number(value);
    setParams((prev) => ({
      ...prev,
      [key]: Number.isNaN(nextValue) ? prev[key] : nextValue,
    }));
  };

  const assumptionChips = [
    { label: copy.kpis.fcasMode || 'FCAS Mode', value: params.fcas_revenue_mode },
    { label: copy.kpis.uiYear || 'Year', value: year || '-' },
  ];
  const lazyLoadNote = isVisible ? (copy.lazyVisible || 'Loading...') : (copy.lazyHidden || 'Hidden');

  return (
    <div ref={sectionRef} className="col-span-12 mt-16 border-t border-[var(--color-border)] pt-12">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h2 className="text-3xl font-serif">{copy.title}</h2>
          <p className="font-sans text-sm text-[var(--color-muted)]">
            {copy.subtitle}
          </p>
        </div>
        <div className="text-sm font-bold uppercase tracking-widest text-[var(--color-muted)]">
          {copy.eyebrow}
        </div>
      </div>

      {scopeNote && (
        <div className="mb-8 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">
          {scopeNote}
        </div>
      )}

      {!result && !loading && (
        <div className="mb-8 rounded border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">
          {lazyLoadNote}
        </div>
      )}

      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 space-y-6 lg:col-span-4">
          <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
            <div className="border-b border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <h3 className="text-sm font-bold uppercase tracking-wider">{copy.parameters}</h3>
            </div>

            <div className="space-y-6 p-4">
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">
                  {copy.fcasRevenueMode || 'FCAS Revenue Mode'}
                </label>
                <select
                  value={params.fcas_revenue_mode}
                  onChange={(e) => setParams((prev) => ({ ...prev, fcas_revenue_mode: e.target.value }))}
                  className="w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm"
                >
                  <option value="auto">{copy.modeAuto || 'Auto'}</option>
                  <option value="manual">{copy.modeManual || 'Manual'}</option>
                </select>
              </div>

              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-[var(--color-muted)] flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={params.monte_carlo_enabled}
                    onChange={(e) => setParams((prev) => ({ ...prev, monte_carlo_enabled: e.target.checked }))}
                    className="rounded border-[var(--color-border)] text-[var(--color-primary)] focus:ring-[var(--color-primary)]"
                  />
                  Run Monte Carlo Simulation (P10/P50/P90)
                </label>
              </div>

              {FIELD_GROUPS.map((group) => (
                <div key={group.titleKey}>
                  <div className="mb-3 text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">
                    {copy.groups[group.titleKey]}
                  </div>
                  <div className="space-y-3">
                    {group.fields.map((field) => {
                      const disabled = field.key === 'fcas_revenue_per_mw_year' && params.fcas_revenue_mode !== 'manual';
                      const value = params[field.key];
                      return (
                        <label key={field.key} className={`block ${disabled ? 'opacity-50' : ''}`}>
                          <div className="mb-1 flex items-center justify-between text-xs">
                            <span className="text-[var(--color-muted)]">{copy.fields[field.labelKey]}</span>
                            <span className="font-mono font-bold">
                              {field.pct ? `${(value * 100).toFixed(2)}${field.suffix}` : `${Number(value).toLocaleString()} ${field.suffix}`}
                            </span>
                          </div>
                          <input
                            type="number"
                            min={field.min}
                            max={field.max}
                            step={field.step}
                            value={value}
                            disabled={disabled}
                            onChange={(e) => updateNumericParam(field.key, e.target.value)}
                            className="w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm font-mono disabled:cursor-not-allowed"
                          />
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <button
                onClick={() => runAnalysis()}
                disabled={loading}
                className="w-full bg-[var(--color-inverted)] py-3 text-sm font-bold uppercase tracking-wider text-[var(--color-inverted-text)] transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {loading ? copy.running : copy.runAnalysis}
              </button>
              <div className="mt-2 text-center text-xs text-[var(--color-muted)]">
                {copy.capexSummary} {fmt(capexPreview)} | {copy.sizeSummary} {params.power_mw}MW / {params.power_mw * params.duration_hours}MWh
              </div>
            </div>
          </div>
        </div>

        <div className="col-span-12 lg:col-span-8">
          {error && (
            <div className="mb-4 rounded border border-red-300 bg-red-50 p-4 text-red-700">
              {error}
            </div>
          )}

          {result && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
                <KpiCard label={copy.kpis.npv || 'NPV'} value={fmt(metrics.npv)} tone={metrics.npv > 0 ? 'good' : 'bad'} sub={`Discount ${(params.discount_rate * 100).toFixed(1)}%`} />
                <KpiCard label={copy.kpis.irr || 'IRR'} value={formatPercentageValue(metrics.irr)} tone={metrics.irr > params.discount_rate * 100 ? 'good' : 'warn'} sub="Unlevered" />
                <KpiCard label="Debt Cap" value={fmt(metrics.debt_capacity)} tone="brand" sub={`Avg DSCR ${metrics.dscr_avg ? metrics.dscr_avg.toFixed(2) : '-'}x`} />
                <KpiCard label="Levered IRR" value={formatPercentageValue(metrics.levered_irr !== null && metrics.levered_irr !== undefined ? metrics.levered_irr * 100 : null)} tone="good" sub="Equity Return" />
                <KpiCard label={copy.kpis.payback || 'Payback'} value={metrics.payback_years ? `${metrics.payback_years} yrs` : 'Over Life'} tone={metrics.payback_years ? 'good' : 'warn'} sub={`Life ${params.project_life_years} yrs`} />
                <KpiCard label="ROI" value={formatPercentageValue(metrics.roi_pct)} tone="brand" sub="Total Return" />
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
                {assumptionChips.map((chip) => (
                  <div key={chip.label} className="rounded border border-[var(--color-border)] p-3">
                    <div className="mb-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{chip.label}</div>
                    <div className="break-words text-sm font-bold font-mono">{chip.value}</div>
                  </div>
                ))}
              </div>

              {result.assumptions?.length > 0 && (
                <div className="rounded-lg border border-[var(--color-border)] p-4">
                  <h4 className="mb-3 text-sm font-bold uppercase tracking-wider">{copy.assumptions}</h4>
                  <div className="space-y-2 text-sm text-[var(--color-muted)]">
                    {result.assumptions.map((item, index) => (
                      <div key={index}>- {item}</div>
                    ))}
                  </div>
                </div>
              )}

              {mc && (
                <div className="rounded-lg border border-[var(--color-border)] p-4 bg-[var(--color-surface)]">
                  <h4 className="mb-3 text-sm font-bold uppercase tracking-wider text-[var(--color-primary)]">Monte Carlo Probability Outcomes (NPV)</h4>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <SummaryBlock label="P90 (Downside / Conservative)" value={fmt(mc.npv_p90)} />
                    <SummaryBlock label="P50 (Base Case / Expected)" value={fmt(mc.npv_p50)} />
                    <SummaryBlock label="P10 (Upside / Optimistic)" value={fmt(mc.npv_p10)} />
                  </div>
                </div>
              )}

              {cashFlows.length > 0 && (
                <div className="rounded-lg border border-[var(--color-border)] p-4">
                  <h4 className="mb-4 text-sm font-bold uppercase tracking-wider">{copy.cashFlowProjection}</h4>
                  <ResponsiveContainer width="100%" height={400}>
                    <ComposedChart data={cashFlows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                      <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                      <YAxis tickFormatter={(value) => fmt(value)} tick={{ fontSize: 11 }} />
                      <Tooltip
                        formatter={(value, name) => [fmt(value), name]}
                        contentStyle={{
                          backgroundColor: 'var(--color-bg)',
                          border: '1px solid var(--color-border)',
                          fontSize: 12,
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="revenue" name={copy.revenue} fill="var(--color-primary)" opacity={0.7} />
                      <Bar dataKey="opex" name={copy.opex} fill="#ef4444" opacity={0.5} />
                      <Line type="monotone" dataKey="cumulative" name={copy.cumulative} stroke="#22c55e" strokeWidth={2.5} dot={false} />
                      <ReferenceLine y={0} stroke="var(--color-muted)" strokeDasharray="4 4" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {cashFlows.length > 0 && (
                <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
                  <h4 className="bg-[var(--color-surface)] p-4 text-sm font-bold uppercase tracking-wider">
                    {copy.annualCashFlows}
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono">
                      <thead>
                        <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                          <th className="p-2 text-left">{copy.year}</th>
                          <th className="p-2 text-right">{copy.revenue}</th>
                          <th className="p-2 text-right">{copy.opex}</th>
                          <th className="p-2 text-right">{copy.net}</th>
                          <th className="p-2 text-right">{copy.cumulative}</th>
                          <th className="p-2 text-right">{copy.degradationFactor}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cashFlows.map((row) => (
                          <tr key={row.year} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]">
                            <td className="p-2 font-bold">Y{row.year}</td>
                            <td className="p-2 text-right text-[var(--color-primary)]">{fmt(row.revenue)}</td>
                            <td className="p-2 text-right text-[#ef4444]">{fmt(row.opex)}</td>
                            <td className="p-2 text-right font-bold" style={{ color: row.net_cash_flow >= 0 ? '#22c55e' : '#ef4444' }}>
                              {fmt(row.net_cash_flow)}
                            </td>
                            <td className="p-2 text-right" style={{ color: row.cumulative >= 0 ? '#22c55e' : '#ef4444' }}>
                              {fmt(row.cumulative)}
                            </td>
                            <td className="p-2 text-right text-[var(--color-muted)]">
                              {(row.degradation_factor * 100).toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ label, value, sub, tone }) {
  const colors = {
    good: '#22c55e',
    bad: '#ef4444',
    warn: '#f59e0b',
    brand: '#0047FF',
  };

  return (
    <div className="rounded-lg border border-[var(--color-border)] p-4">
      <div className="mb-1 text-xs uppercase tracking-wider text-[var(--color-muted)]">{label}</div>
      <div className="text-2xl font-bold font-mono" style={{ color: colors[tone] || 'inherit' }}>{value}</div>
      <div className="mt-1 text-xs text-[var(--color-muted)]">{sub}</div>
    </div>
  );
}

function SummaryBlock({ label, value }) {
  return (
    <div className="rounded border border-[var(--color-border)] p-4">
      <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
      <div className="text-xl font-bold font-mono">{value}</div>
    </div>
  );
}
