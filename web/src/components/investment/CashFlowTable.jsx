/**
 * CashFlowTable — 年度现金流表格（可折叠，默认显示前 5 年）
 */

import { useState } from 'react';
import { fmt } from '../../lib/formatters';

const DEFAULT_VISIBLE_YEARS = 5;

const LABELS = {
  zh: {
    collapse: '收起',
    showAll: (count) => `展开全部 (${count} 年)`,
  },
  en: {
    collapse: 'Collapse',
    showAll: (count) => `Show all (${count} years)`,
  },
};

export default function CashFlowTable({ cashFlows, copy, lang = 'zh' }) {
  const [expanded, setExpanded] = useState(false);
  const t = LABELS[lang] || LABELS.zh;

  if (!cashFlows || cashFlows.length === 0) return null;

  const visibleRows = expanded ? cashFlows : cashFlows.slice(0, DEFAULT_VISIBLE_YEARS);
  const hasMore = cashFlows.length > DEFAULT_VISIBLE_YEARS;

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
      <h4 className="bg-[var(--color-surface)] p-4 text-sm font-bold uppercase tracking-wider">
        {copy.annualCashFlows}
      </h4>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
              <th className="p-2 text-left">{copy.year}</th>
              <th className="p-2 text-right">{copy.tableHeaders.arbitrage}</th>
              <th className="p-2 text-right">{copy.tableHeaders.fcas}</th>
              <th className="p-2 text-right">{copy.tableHeaders.capacity}</th>
              <th className="p-2 text-right">{copy.revenue}</th>
              <th className="p-2 text-right">{copy.opex}</th>
              <th className="p-2 text-right">{copy.net}</th>
              <th className="p-2 text-right">{copy.cumulative}</th>
              <th className="p-2 text-right">{copy.degradationFactor}</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.year} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]">
                <td className="p-2 font-bold">{copy.yearPrefix}{row.year}</td>
                <td className="p-2 text-right">{fmt(row.revenue_arbitrage)}</td>
                <td className="p-2 text-right">{fmt(row.revenue_fcas)}</td>
                <td className="p-2 text-right">{fmt(row.revenue_capacity)}</td>
                <td className="p-2 text-right text-[var(--color-primary)]">{fmt(row.revenue)}</td>
                <td className="p-2 text-right text-[var(--color-negative)]">{fmt(row.opex)}</td>
                <td className="p-2 text-right font-bold" style={{ color: row.net_cash_flow >= 0 ? 'var(--color-positive)' : 'var(--color-negative)' }}>
                  {fmt(row.net_cash_flow)}
                </td>
                <td className="p-2 text-right" style={{ color: row.cumulative >= 0 ? 'var(--color-positive)' : 'var(--color-negative)' }}>
                  {fmt(row.cumulative)}
                </td>
                <td className="p-2 text-right text-[var(--color-muted)]">
                  {row.degradation_factor != null ? `${(row.degradation_factor * 100).toFixed(1)}%` : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-center">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs font-semibold text-[var(--color-primary)] hover:underline"
          >
            {expanded
              ? t.collapse
              : t.showAll(cashFlows.length)}
          </button>
        </div>
      )}
    </div>
  );
}
