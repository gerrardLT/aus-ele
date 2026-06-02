/**
 * CashFlowChart — Recharts ComposedChart（收入柱状图 + 累计线图）
 */

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
import { fmt } from '../../lib/formatters';

const LABELS = {
  zh: { p3Cumulative: 'P3 累计现金流' },
  en: { p3Cumulative: 'P3 Cumulative' },
};

export default function CashFlowChart({ chartData, copy, lang = 'zh', hasDecisionAdjusted }) {
  if (!chartData || chartData.length === 0) return null;

  const t = LABELS[lang] || LABELS.zh;

  return (
    <div className="rounded-lg border border-[var(--color-border)] p-4">
      <h4 className="mb-4 text-sm font-bold uppercase tracking-wider">{copy.cashFlowProjection}</h4>
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={chartData}>
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
          {hasDecisionAdjusted && (
            <Line
              type="monotone"
              dataKey="adjusted_cumulative"
              name={t.p3Cumulative}
              stroke="#f59e0b"
              strokeWidth={2.5}
              strokeDasharray="6 4"
              dot={false}
            />
          )}
          <ReferenceLine y={0} stroke="var(--color-muted)" strokeDasharray="4 4" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
