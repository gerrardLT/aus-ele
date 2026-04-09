import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ComposedChart, Area, ReferenceLine, Cell
} from 'recharts';
import TermTooltip from './Tooltip';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8085/api';

const PRESET_DEFAULTS = {
  // Storage specification
  power_mw: 100,
  duration_hours: 4,
  round_trip_efficiency: 0.87,
  degradation_rate: 0.025,
  // Cost (AUD)
  capex_per_kwh: 350,
  fixed_om_per_mw_year: 12000,
  variable_om_per_mwh: 2.5,
  grid_connection_cost: 5000000,
  land_lease_per_year: 200000,
  // Finance
  discount_rate: 0.08,
  project_life_years: 20,
  // Revenue
  revenue_capture_rate: 0.65,
  fcas_revenue_per_mw_year: 15000,
  capacity_payment_per_mw_year: 0,
  backtest_years: [2024, 2025],
};

const PARAM_META = {
  power_mw:        { label: '额定功率', labelEn: 'Power Rating', unit: 'MW', min: 1, max: 1000, step: 10, group: 'storage' },
  duration_hours:  { label: '储能时长', labelEn: 'Duration', unit: 'h', min: 1, max: 12, step: 1, group: 'storage' },
  round_trip_efficiency: { label: '往返效率', labelEn: 'RTE', unit: '%', min: 0.7, max: 0.97, step: 0.01, group: 'storage', pct: true },
  degradation_rate: { label: '年衰减率', labelEn: 'Degradation', unit: '%/yr', min: 0.005, max: 0.05, step: 0.005, group: 'storage', pct: true },
  capex_per_kwh:   { label: 'CAPEX', labelEn: 'CAPEX/kWh', unit: '$/kWh', min: 150, max: 800, step: 10, group: 'cost' },
  fixed_om_per_mw_year: { label: '固定运维', labelEn: 'Fixed O&M', unit: '$/MW/yr', min: 0, max: 30000, step: 1000, group: 'cost' },
  variable_om_per_mwh: { label: '可变运维', labelEn: 'Var O&M', unit: '$/MWh', min: 0, max: 10, step: 0.5, group: 'cost' },
  grid_connection_cost: { label: '并网费用', labelEn: 'Grid Connect', unit: '$', min: 0, max: 20000000, step: 500000, group: 'cost' },
  land_lease_per_year: { label: '土地租赁', labelEn: 'Land Lease', unit: '$/yr', min: 0, max: 1000000, step: 50000, group: 'cost' },
  discount_rate:   { label: '贴现率', labelEn: 'Discount Rate', unit: '%', min: 0.03, max: 0.20, step: 0.01, group: 'finance', pct: true },
  project_life_years: { label: '项目期限', labelEn: 'Project Life', unit: '年', min: 10, max: 30, step: 1, group: 'finance' },
  revenue_capture_rate: { label: '收入捕获率', labelEn: 'Capture Rate', unit: '%', min: 0.3, max: 1.0, step: 0.05, group: 'finance', pct: true },
  fcas_revenue_per_mw_year: { label: 'FCAS 收入', labelEn: 'FCAS Rev', unit: '$/MW/yr', min: 0, max: 80000, step: 5000, group: 'finance' },
  capacity_payment_per_mw_year: { label: '容量补贴', labelEn: 'Cap Payment', unit: '$/MW/yr', min: 0, max: 600000, step: 10000, group: 'finance' },
};

const GROUPS = {
  storage: { label: '储能规格', icon: '▪' },
  cost: { label: '成本参数', icon: '▪' },
  finance: { label: '财务参数', icon: '▪' },
};

function fmt(val, prefix = '$') {
  if (val === null || val === undefined) return '—';
  const abs = Math.abs(val);
  if (abs >= 1e9) return `${prefix}${(val / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${prefix}${(val / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${prefix}${(val / 1e3).toFixed(0)}K`;
  return `${prefix}${val.toLocaleString()}`;
}

export default function InvestmentAnalysis({ region, year, t }) {
  const [params, setParams] = useState({ ...PRESET_DEFAULTS });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedGroup, setExpandedGroup] = useState('storage');

  const updateParam = useCallback((key, value) => {
    setParams(prev => ({ ...prev, [key]: value }));
  }, []);

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = { ...params, region };
      const res = await fetch(`${API_BASE}/investment-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  }, [params, region]);

  // Auto-run on mount
  useEffect(() => {
    runAnalysis();
  }, [region]);

  const cashFlows = result?.cash_flows?.filter(cf => cf.year > 0) || [];
  const metrics = result?.metrics || {};
  const baseline = result?.baseline_revenue || {};
  const backtest = result?.backtest || {};

  return (
    <div className="col-span-12 mt-16 pt-12 border-t border-[var(--color-border)]">
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-3xl font-serif">投资分析 / Investment Analysis</h2>
        <div className="text-[var(--color-muted)] text-sm tracking-widest uppercase font-bold">
          BESS CASH FLOW MODEL
        </div>
      </div>

      <div className="grid grid-cols-12 gap-8">
        {/* Left: Parameter Panel */}
        <div className="col-span-12 lg:col-span-4">
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
            <div className="p-4 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
              <h3 className="font-bold text-sm tracking-wider uppercase">参数设置 / Parameters</h3>
            </div>

            {Object.entries(GROUPS).map(([groupKey, groupInfo]) => (
              <div key={groupKey} className="border-b border-[var(--color-border)] last:border-b-0">
                <button
                  onClick={() => setExpandedGroup(expandedGroup === groupKey ? null : groupKey)}
                  className="w-full p-3 flex items-center justify-between hover:bg-[var(--color-surface-hover)] transition-colors"
                >
                  <span className="text-sm font-medium">{groupInfo.icon} {groupInfo.label}</span>
                  <span className="text-xs text-[var(--color-muted)]">
                    {expandedGroup === groupKey ? '▼' : '▶'}
                  </span>
                </button>

                {expandedGroup === groupKey && (
                  <div className="px-4 pb-4 space-y-3">
                    {Object.entries(PARAM_META)
                      .filter(([, meta]) => meta.group === groupKey)
                      .map(([key, meta]) => (
                        <div key={key}>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-[var(--color-muted)]">{meta.label}</span>
                            <span className="font-mono font-bold">
                              {meta.pct
                                ? `${(params[key] * 100).toFixed(1)}${meta.unit}`
                                : `${params[key].toLocaleString()} ${meta.unit}`}
                            </span>
                          </div>
                          <input
                            type="range"
                            min={meta.min}
                            max={meta.max}
                            step={meta.step}
                            value={params[key]}
                            onChange={e => updateParam(key, parseFloat(e.target.value))}
                            className="w-full h-1.5 accent-[var(--color-text)] cursor-pointer"
                          />
                        </div>
                      ))}
                  </div>
                )}
              </div>
            ))}

            {/* Run Button */}
            <div className="p-4 bg-[var(--color-surface)]">
              <button
                onClick={runAnalysis}
                disabled={loading}
                className="w-full py-3 bg-[var(--color-inverted)] text-[var(--color-inverted-text)] font-bold text-sm tracking-wider uppercase hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {loading ? '计算中...' : '运行分析 / RUN ANALYSIS'}
              </button>
              <div className="mt-2 text-xs text-center text-[var(--color-muted)]">
                总投资: {fmt((params.capex_per_kwh * params.power_mw * params.duration_hours * 1000) + params.grid_connection_cost)}
                {' | '}容量: {params.power_mw}MW / {params.power_mw * params.duration_hours}MWh
              </div>
            </div>
          </div>
        </div>

        {/* Right: Results */}
        <div className="col-span-12 lg:col-span-8">
          {error && (
            <div className="p-4 border border-red-300 bg-red-50 text-red-700 rounded mb-4">
              {error}
            </div>
          )}

          {result && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-8"
            >
              {/* KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  {
                    label: 'NPV',
                    tooltip: '净现值 (Net Present Value) — 项目在整个生命周期内所有现金流的折现总和。NPV > 0 表示项目创造价值。',
                    value: fmt(metrics.npv),
                    sub: `贴现率 ${(params.discount_rate * 100).toFixed(0)}%`,
                    color: metrics.npv > 0 ? '#22c55e' : '#ef4444',
                  },
                  {
                    label: 'IRR',
                    tooltip: '内部收益率 (Internal Rate of Return) — 使 NPV 为零的折现率。IRR 高于贴现率说明项目有吸引力。',
                    value: metrics.irr !== null ? `${metrics.irr}%` : '—',
                    sub: metrics.irr > params.discount_rate * 100 ? '✓ 超过贴现率' : '‼ 低于贴现率',
                    color: metrics.irr && metrics.irr > params.discount_rate * 100 ? '#22c55e' : '#f59e0b',
                  },
                  {
                    label: '回收期',
                    tooltip: '静态回收期 (Payback Period) — 累计净现金流由负转正所需的年数。越短风险越低。',
                    value: metrics.payback_years ? `${metrics.payback_years} 年` : '> 项目期',
                    sub: `项目期 ${params.project_life_years} 年`,
                    color: metrics.payback_years && metrics.payback_years <= params.project_life_years * 0.5 ? '#22c55e' : '#f59e0b',
                  },
                  {
                    label: '年均营收/MW',
                    tooltip: '每 MW 装机容量每年的平均收入，包含套利收入和 FCAS 辅助服务收入。',
                    value: fmt(baseline.per_mw),
                    sub: `套利 ${fmt(baseline.arbitrage)}`,
                    color: '#0047FF',
                  },
                ].map((kpi, i) => (
                  <div key={i} className="border border-[var(--color-border)] p-4 rounded-lg">
                    <div className="text-xs text-[var(--color-muted)] uppercase tracking-wider mb-1">
                      <TermTooltip term={kpi.label} explanation={kpi.tooltip}>{kpi.label}</TermTooltip>
                    </div>
                    <div className="text-2xl font-bold font-mono" style={{ color: kpi.color }}>{kpi.value}</div>
                    <div className="text-xs text-[var(--color-muted)] mt-1">{kpi.sub}</div>
                  </div>
                ))}
              </div>

              {/* Backtest Results */}
              {Object.keys(backtest).length > 0 && (
                <div className="border border-[var(--color-border)] rounded-lg p-4">
                  <h4 className="text-sm font-bold mb-3 uppercase tracking-wider">历史回测 / BACKTEST RESULTS</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    {Object.entries(backtest).map(([yr, data]) => (
                      <div key={yr} className="bg-[var(--color-surface)] p-3 rounded">
                        <div className="font-bold">{yr}</div>
                        <div className="text-[var(--color-muted)] text-xs">
                          理论: {fmt(data.per_mw)}/MW/yr
                        </div>
                        <div className="text-xs">{data.trading_days} 交易日</div>
                      </div>
                    ))}
                    <div className="bg-[var(--color-surface)] p-3 rounded border-l-2 border-[var(--color-primary)]">
                      <div className="font-bold">实际基准</div>
                      <div className="text-[var(--color-muted)] text-xs">
                        × {(params.revenue_capture_rate * 100).toFixed(0)}% 捕获率
                      </div>
                      <div className="text-xs font-bold" style={{ color: 'var(--color-primary)' }}>
                        = {fmt(baseline.per_mw)}/MW/yr
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Revenue Breakdown Bar */}
              <div className="border border-[var(--color-border)] rounded-lg p-4">
                <h4 className="text-sm font-bold mb-3 uppercase tracking-wider">年收入构成 / REVENUE BREAKDOWN (Year 1)</h4>
                <div className="h-10 flex rounded overflow-hidden text-xs font-bold">
                  {baseline.arbitrage > 0 && (
                    <div
                      className="flex items-center justify-center text-white"
                      style={{
                        width: `${(baseline.arbitrage / baseline.total) * 100}%`,
                        backgroundColor: 'var(--color-primary)',
                        minWidth: baseline.arbitrage > 0 ? '60px' : '0',
                      }}
                    >
                      套利 {fmt(baseline.arbitrage)}
                    </div>
                  )}
                  {baseline.fcas > 0 && (
                    <div
                      className="flex items-center justify-center"
                      style={{
                        width: `${(baseline.fcas / baseline.total) * 100}%`,
                        backgroundColor: '#111827',
                        color: '#E5E7EB',
                        minWidth: baseline.fcas > 0 ? '60px' : '0',
                      }}
                    >
                      FCAS {fmt(baseline.fcas)}
                    </div>
                  )}
                  {baseline.capacity > 0 && (
                    <div
                      className="flex items-center justify-center"
                      style={{
                        width: `${(baseline.capacity / baseline.total) * 100}%`,
                        backgroundColor: '#f59e0b',
                        minWidth: baseline.capacity > 0 ? '60px' : '0',
                      }}
                    >
                      容量 {fmt(baseline.capacity)}
                    </div>
                  )}
                </div>
                <div className="text-xs text-[var(--color-muted)] mt-2 text-right">
                  总计: {fmt(baseline.total)} / 年
                </div>
              </div>

              {/* Cash Flow Chart */}
              {cashFlows.length > 0 && (
                <div className="border border-[var(--color-border)] rounded-lg p-4">
                  <h4 className="text-sm font-bold mb-4 uppercase tracking-wider">现金流曲线 / CASH FLOW PROJECTION</h4>
                  <ResponsiveContainer width="100%" height={400}>
                    <ComposedChart data={cashFlows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                      <XAxis
                        dataKey="year"
                        label={{ value: '年份', position: 'bottom', offset: -5 }}
                        tick={{ fontSize: 12 }}
                      />
                      <YAxis
                        tickFormatter={v => fmt(v)}
                        tick={{ fontSize: 11 }}
                      />
                      <Tooltip
                        formatter={(val, name) => [fmt(val), name]}
                        contentStyle={{
                          backgroundColor: 'var(--color-bg)',
                          border: '1px solid var(--color-border)',
                          fontSize: 12,
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="revenue" name="营收" fill="var(--color-primary)" opacity={0.7} />
                      <Bar dataKey="opex" name="运营成本" fill="#ef4444" opacity={0.5} />
                      <Line
                        type="monotone"
                        dataKey="cumulative"
                        name="累计现金流"
                        stroke="#22c55e"
                        strokeWidth={2.5}
                        dot={false}
                      />
                      <ReferenceLine y={0} stroke="var(--color-muted)" strokeDasharray="4 4" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Cash Flow Table */}
              {cashFlows.length > 0 && (
                <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
                  <h4 className="text-sm font-bold p-4 uppercase tracking-wider bg-[var(--color-surface)]">
                    逐年现金流 / ANNUAL CASH FLOWS
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono">
                      <thead>
                        <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                          <th className="p-2 text-left">年份</th>
                          <th className="p-2 text-right">营收</th>
                          <th className="p-2 text-right">运维</th>
                          <th className="p-2 text-right">净现金流</th>
                          <th className="p-2 text-right">累计</th>
                          <th className="p-2 text-right">衰减</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cashFlows.map(cf => (
                          <tr
                            key={cf.year}
                            className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]"
                          >
                            <td className="p-2 font-bold">Y{cf.year}</td>
                            <td className="p-2 text-right text-[var(--color-primary)]">{fmt(cf.revenue)}</td>
                            <td className="p-2 text-right text-[#ef4444]">{fmt(cf.opex)}</td>
                            <td className="p-2 text-right font-bold" style={{
                              color: cf.net_cash_flow >= 0 ? '#22c55e' : '#ef4444'
                            }}>
                              {fmt(cf.net_cash_flow)}
                            </td>
                            <td className="p-2 text-right" style={{
                              color: cf.cumulative >= 0 ? '#22c55e' : '#ef4444'
                            }}>
                              {fmt(cf.cumulative)}
                            </td>
                            <td className="p-2 text-right text-[var(--color-muted)]">
                              {(cf.degradation_factor * 100).toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Disclaimer */}
              <div className="text-xs text-[var(--color-muted)] italic border-t border-[var(--color-border)] pt-4">
                免责声明: 本分析基于历史价格回测，使用完美预见差价 × {(params.revenue_capture_rate * 100).toFixed(0)}% 捕获率作为基准。
                实际收入受市场条件、调度策略、竞争环境等因素影响可能有较大偏差。
                本工具仅供投资参考，不构成投资建议。
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
