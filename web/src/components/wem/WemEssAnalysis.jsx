import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchJson } from '../../lib/apiClient';

const AGGREGATIONS = ['daily', 'weekly', 'monthly'];

// 暗蓝档提亮：#0047FF/#2563eb 在暗色背景上对比度不足（2026-08-10）
const ESS_COLORS = {
  regulation_raise: '#2563eb',
  regulation_lower: '#3b82f6',
  contingency_raise: '#22C55E',
  contingency_lower: '#60a5fa',
  rocof: '#8b5cf6',
};

const ESS_LABELS = {
  zh: {
    regulation_raise: '调频上调',
    regulation_lower: '调频下调',
    contingency_raise: '应急上调',
    contingency_lower: '应急下调',
    rocof: '频率变化率 (RoCoF)',
  },
  en: {
    regulation_raise: 'Regulation Raise',
    regulation_lower: 'Regulation Lower',
    contingency_raise: 'Contingency Raise',
    contingency_lower: 'Contingency Lower',
    rocof: 'RoCoF',
  },
};

function buildParams(year, region, aggregation, capacityMw, quarter, dayType) {
  const params = new URLSearchParams({
    year: String(year),
    region,
    aggregation,
    capacity_mw: String(capacityMw),
  });
  if (quarter && quarter !== 'ALL') params.set('quarter', quarter);
  if (dayType && dayType !== 'ALL') params.set('day_type', dayType);
  return params;
}

export default function WemEssAnalysis({
  year,
  region = 'WEM',
  lang = 'zh',
  quarter,
  dayType,
  apiBase,
}) {
  const [aggregation, setAggregation] = useState('monthly');
  const [capacityMw, setCapacityMw] = useState(100);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const essLabels = ESS_LABELS[lang] || ESS_LABELS.zh;

  const aggLabels = {
    daily: lang === 'zh' ? '每日' : 'Daily',
    weekly: lang === 'zh' ? '每周' : 'Weekly',
    monthly: lang === 'zh' ? '每月' : 'Monthly',
  };

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);
    setError(null);

    const params = buildParams(year, region, aggregation, capacityMw, quarter, dayType);
    fetchJson(`${apiBase}/fcas-analysis?${params.toString()}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err?.message || 'Unknown error');
        setLoading(false);
      });
  }, [year, region, aggregation, capacityMw, quarter, dayType, apiBase]);

  const fmt = (value) =>
    value !== null && value !== undefined ? `$${Number(value).toFixed(1)}` : '-';
  const fmtK = (value) =>
    value !== null && value !== undefined ? `$${Number(value).toFixed(0)}k` : '-';

  const serviceBreakdown = useMemo(() => data?.service_breakdown || [], [data]);

  const breakdownData = useMemo(
    () =>
      serviceBreakdown.map((service) => ({
        service: essLabels[service.key] || service.service,
        key: service.key,
        group: service.group,
        avg_price: service.avg_price,
        max_price: service.max_price,
        est_revenue_k: service.est_revenue_k,
        net_incremental_revenue_k: service.net_incremental_revenue_k,
      })),
    [serviceBreakdown, essLabels],
  );

  const tsData = useMemo(() => {
    if (!data?.data) return [];
    const raiseKeys = serviceBreakdown
      .filter((s) => s.group === 'raise')
      .map((s) => s.key);
    const lowerKeys = serviceBreakdown
      .filter((s) => s.group === 'lower')
      .map((s) => s.key);

    return data.data.map((row) => ({
      period: row.period,
      total_ess: row.total_fcas_avg || 0,
      raise_total: raiseKeys.reduce((sum, key) => sum + (row[key] || 0), 0),
      lower_total: lowerKeys.reduce((sum, key) => sum + (row[key] || 0), 0),
    }));
  }, [data, serviceBreakdown]);

  const hourlyData = useMemo(() => data?.hourly || [], [data]);

  // Constraint binding analysis
  const bindingData = useMemo(() => {
    if (!serviceBreakdown.length) return [];
    return serviceBreakdown.map((service) => ({
      service: essLabels[service.key] || service.service,
      key: service.key,
      soc_binding: ((service.soc_binding_interval_ratio || 0) * 100).toFixed(0),
      power_binding: ((service.power_binding_interval_ratio || 0) * 100).toFixed(0),
    }));
  }, [serviceBreakdown, essLabels]);

  // Error state
  if (error && !data) {
    return (
      <div className="p-4 border border-[var(--color-status-error)]/40 bg-[var(--color-status-error)]/8 text-[var(--color-status-error)] rounded">
        <p className="font-semibold mb-1">
          {lang === 'zh' ? '无法加载 ESS 数据' : 'Failed to load ESS data'}
        </p>
        <p className="text-sm">
          {lang === 'zh'
            ? `原因：${error}。建议检查后端服务是否运行，或稍后重试。`
            : `Reason: ${error}. Please check the backend service or try again later.`}
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
    >
      {/* Controls: aggregation + capacity */}
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
            {lang === 'zh' ? '聚合粒度' : 'AGGREGATION'}
          </span>
          <div className="flex gap-2 flex-wrap">
            {AGGREGATIONS.map((value) => (
              <button
                key={value}
                onClick={() => setAggregation(value)}
                className={`px-4 py-1.5 text-sm font-sans transition-colors rounded-full border ${
                  aggregation === value
                    ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-inverted)]'
                    : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-text)]'
                }`}
              >
                {aggLabels[value]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
            {lang === 'zh' ? '电池容量 (MW)' : 'BATTERY CAPACITY (MW)'}
          </span>
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={capacityMw}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                setCapacityMw(Number.isNaN(v) || v <= 0 ? 100 : v);
              }}
              className="w-24 px-3 py-1.5 text-sm font-mono border border-[var(--color-border)] bg-transparent text-[var(--color-text)] rounded focus:outline-none focus:border-[var(--color-text)]"
              min="1"
              step="10"
            />
            <span className="text-xs text-[var(--color-muted)]">MW</span>
          </div>
        </div>
      </div>

      {/* Loading */}
      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {lang === 'zh' ? '正在加载 ESS 辅助服务数据...' : 'Loading ESS data...'}
        </div>
      ) : data?.has_fcas_data === false ? (
        <div className="h-48 flex flex-col items-center justify-center text-[var(--color-muted)] font-serif gap-3">
          <div className="text-lg">
            {lang === 'zh' ? 'ESS 数据尚未加载' : 'No ESS data available'}
          </div>
          <div className="text-sm font-sans max-w-md text-center">
            {data?.message || (lang === 'zh' ? '当前年份/区域暂无 ESS 数据。' : 'No ESS data for this year/region.')}
          </div>
        </div>
      ) : data?.data?.length > 0 ? (
        <>
          {/* KPI Summary Cards */}
          {data.summary && (
            <div className="mb-7 grid grid-cols-2 gap-3 md:grid-cols-4">
              <SummaryCard
                label={lang === 'zh' ? 'ESS 总均价' : 'Avg ESS Price'}
                value={fmt(data.summary.total_avg_fcas_price)}
                sub="/MWh"
              />
              <SummaryCard
                label={lang === 'zh' ? '估算年收入' : 'Est. Revenue'}
                value={fmtK(data.summary.total_est_revenue_k)}
                accent
              />
              <SummaryCard
                label={lang === 'zh' ? '可行服务数' : 'Viable Services'}
                value={data.summary.viable_service_count ?? 0}
              />
              <SummaryCard
                label={lang === 'zh' ? '电池容量' : 'Capacity'}
                value={`${data.summary.capacity_mw || capacityMw} MW`}
              />
            </div>
          )}

          {/* Charts: Service Breakdown + Hourly */}
          <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* Service breakdown bar chart */}
            <div>
              <h3 className="text-lg font-serif mb-4">
                {lang === 'zh' ? '各服务收入分布' : 'Revenue by Service'}
              </h3>
              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={breakdownData} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                    <YAxis type="category" dataKey="service" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} width={110} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 12,
                      }}
                      formatter={(value, name) => {
                        if (name === 'net_incremental_revenue_k') return [`$${value}k`, lang === 'zh' ? '净增量收入' : 'Net Incremental'];
                        if (name === 'est_revenue_k') return [`$${value}k`, lang === 'zh' ? '估算收入' : 'Est. Revenue'];
                        return [`$${value}/MWh`, lang === 'zh' ? '均价' : 'Avg Price'];
                      }}
                    />
                    <Bar dataKey="net_incremental_revenue_k" name={lang === 'zh' ? '净增量收入' : 'Net Incremental Revenue'} radius={[0, 4, 4, 0]}>
                      {breakdownData.map((entry) => (
                        <Cell key={entry.key} fill={ESS_COLORS[entry.key] || '#666'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Hourly distribution */}
            <div>
              <h3 className="text-lg font-serif mb-4">
                {lang === 'zh' ? 'ESS 小时分布' : 'Hourly ESS Distribution'}
              </h3>
              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hourlyData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'var(--color-muted)' }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 12,
                      }}
                      formatter={(value) => [`$${value}/MWh`, lang === 'zh' ? 'ESS 总计' : 'Total ESS']}
                      labelFormatter={(label) => `${lang === 'zh' ? '时段' : 'Hour'}: ${label}:00`}
                    />
                    <Bar dataKey="avg_total_fcas" name={lang === 'zh' ? 'ESS 均价' : 'Avg ESS'} fill="#0047FF" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Price trend chart */}
          <div className="mb-8">
            <h3 className="text-lg font-serif mb-4">
              {lang === 'zh' ? 'ESS 价格走势 — 升频 vs 降频' : 'ESS Price Trend — Raise vs Lower'}
            </h3>
            <div className="h-[360px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={tsData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 12,
                    }}
                    formatter={(value) => [`$${Number(value).toFixed(1)}/MWh`, '']}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="raise_total" name={lang === 'zh' ? '升频合计' : 'Raise Total'} stroke="#0047FF" fill="#0047FF" fillOpacity={0.12} strokeWidth={2} />
                  <Area type="monotone" dataKey="lower_total" name={lang === 'zh' ? '降频合计' : 'Lower Total'} stroke="#EF4444" fill="#EF4444" fillOpacity={0.12} strokeWidth={2} />
                  <Line type="monotone" dataKey="total_ess" name={lang === 'zh' ? 'ESS 总计' : 'Total ESS'} stroke="#22C55E" strokeWidth={2.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Constraint binding frequency */}
          {bindingData.length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-serif mb-4">
                {lang === 'zh' ? '约束绑定频率分析' : 'Constraint Binding Frequency'}
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm font-sans border-collapse">
                  <thead>
                    <tr className="border-b-2 border-[var(--color-text)]">
                      <th className="text-left py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                        {lang === 'zh' ? '服务类型' : 'Service'}
                      </th>
                      <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                        {lang === 'zh' ? '均价' : 'Avg Price'}
                      </th>
                      <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                        {lang === 'zh' ? '峰值' : 'Max Price'}
                      </th>
                      <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                        {lang === 'zh' ? 'SOC 约束' : 'SOC Binding'}
                      </th>
                      <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                        {lang === 'zh' ? '功率约束' : 'Power Binding'}
                      </th>
                      <th className="text-right py-3 px-2 text-xs tracking-widest uppercase font-bold text-[var(--color-muted)]">
                        {lang === 'zh' ? '可行性' : 'Viability'}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {serviceBreakdown.map((service) => (
                      <tr key={service.key} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                        <td className="py-2.5 px-2 flex items-center gap-2">
                          <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: ESS_COLORS[service.key] || '#666' }} />
                          <span className="font-mono text-xs">{essLabels[service.key] || service.service}</span>
                        </td>
                        <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(service.avg_price)}/MWh</td>
                        <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(service.max_price)}/MWh</td>
                        <td className="text-right py-2.5 px-2 font-mono text-xs">
                          {((service.soc_binding_interval_ratio || 0) * 100).toFixed(0)}%
                        </td>
                        <td className="text-right py-2.5 px-2 font-mono text-xs">
                          {((service.power_binding_interval_ratio || 0) * 100).toFixed(0)}%
                        </td>
                        <td className="text-right py-2.5 px-2 font-mono text-xs font-bold">
                          {service.incremental_revenue_positive
                            ? (lang === 'zh' ? '✓ 可行' : '✓ Viable')
                            : (lang === 'zh' ? '✗ 不可行' : '✗ Not viable')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {lang === 'zh' ? '暂无数据' : 'No data available'}
        </div>
      )}
    </motion.div>
  );
}

function SummaryCard({ label, value, sub, accent = false }) {
  return (
    <div className={`border ${accent ? 'border-[var(--color-text)] bg-[var(--color-inverted)]' : 'border-[var(--color-border)]'} p-4 rounded-lg`}>
      <div className={`text-xs tracking-widest uppercase mb-2 ${
        accent ? 'text-[var(--color-inverted-text)] opacity-70' : 'text-[var(--color-muted)]'
      }`}>
        {label}
      </div>
      <div className={`text-2xl font-mono font-bold ${accent ? 'text-[var(--color-inverted-text)]' : ''}`}>
        {value}
        {sub && <span className="text-xs font-normal ml-1 opacity-60">{sub}</span>}
      </div>
    </div>
  );
}
