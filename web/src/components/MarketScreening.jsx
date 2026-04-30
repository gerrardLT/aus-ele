import { useEffect, useMemo, useState } from 'react';
import { fetchJson } from '../lib/apiClient';
import DataQualityBadge from './DataQualityBadge';

const COPY = {
  zh: {
    title: '\u5e02\u573a\u7b5b\u9009',
    subtitle: '\u8de8\u5e02\u573a BESS 2h \u542f\u53d1\u5f0f\u6392\u540d',
    noData: '\u5f53\u524d\u6ca1\u6709\u53ef\u7528\u7b5b\u9009\u7ed3\u679c\u3002',
    viableLabel: '\u53ef\u4ea4\u4ed8\u5019\u9009',
    loading: '\u6b63\u5728\u52a0\u8f7d\u7b5b\u9009\u7ed3\u679c...',
    metrics: {
      spread: 'Spread',
      volatility: 'Vol',
      storageFit: 'Fit',
      fcasEss: 'FCAS/ESS',
    },
    headers: {
      rank: 'Rank',
      market: 'Market',
      overall: 'Overall',
      spread: 'Spread',
      volatility: 'Volatility',
      storageFit: 'Storage Fit',
      fcasEss: 'FCAS/ESS',
      gridRisk: 'Grid Risk',
      revenue: 'Revenue',
      quality: 'Quality',
    },
  },
  en: {
    title: 'Market Screening',
    subtitle: 'Cross-market BESS 2h heuristic ranking',
    noData: 'No screening results available.',
    viableLabel: 'Commercial shortlist',
    loading: 'Loading screening...',
    metrics: {
      spread: 'Spread',
      volatility: 'Vol',
      storageFit: 'Fit',
      fcasEss: 'FCAS/ESS',
    },
    headers: {
      rank: 'Rank',
      market: 'Market',
      overall: 'Overall',
      spread: 'Spread',
      volatility: 'Volatility',
      storageFit: 'Storage Fit',
      fcasEss: 'FCAS/ESS',
      gridRisk: 'Grid Risk',
      revenue: 'Revenue',
      quality: 'Quality',
    },
  },
};

function toneClass(score) {
  if (score >= 75) return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (score >= 55) return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-rose-700 bg-rose-50 border-rose-200';
}

function ScoreBar({ score }) {
  const bounded = Math.max(0, Math.min(Number(score || 0), 100));
  return (
    <div className="h-2 w-full rounded bg-[var(--color-surface)]">
      <div className="h-2 rounded bg-[var(--color-text)]" style={{ width: `${Math.max(4, bounded)}%` }} />
    </div>
  );
}

export default function MarketScreening({ year, lang = 'en', apiBase }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!year) return;
    setLoading(true);
    fetchJson(`${apiBase}/market-screening?year=${year}`)
      .then((res) => {
        setPayload(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, apiBase]);

  const items = payload?.items || [];
  const topThree = useMemo(() => items.slice(0, 3), [items]);
  const copy = COPY[lang] || COPY.en;

  if (loading) {
    return <div className="rounded border border-[var(--color-border)] p-6 text-sm text-[var(--color-muted)]">{copy.loading}</div>;
  }

  return (
    <div className="mt-16 pt-12 border-t border-[var(--color-border)]">
      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-serif">{copy.title}</h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">{copy.subtitle}</p>
        </div>
        <div className="text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">{copy.viableLabel}</div>
      </div>

      {!items.length ? (
        <div className="rounded border border-[var(--color-border)] p-6 text-sm text-[var(--color-muted)]">{copy.noData}</div>
      ) : (
        <>
          <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
            {topThree.map((item) => (
              <div key={item.candidate_key} className="rounded border border-[var(--color-border)] p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">#{item.rank}</div>
                    <div className="text-xl font-serif">{item.label}</div>
                    <div className="text-xs text-[var(--color-muted)]">{item.market} | {item.asset_profile}</div>
                  </div>
                  <div className={`rounded border px-2 py-1 text-sm font-mono ${toneClass(item.overall_score)}`}>
                    {item.overall_score}
                  </div>
                </div>
                <div className="mb-3">
                  <ScoreBar score={item.overall_score} />
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <Metric label={copy.metrics.spread} value={item.spread_score} />
                  <Metric label={copy.metrics.volatility} value={item.volatility_score} />
                  <Metric label={copy.metrics.storageFit} value={item.storage_fit_score} />
                  <Metric label={copy.metrics.fcasEss} value={item.fcas_or_ess_opportunity_score} />
                </div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto rounded border border-[var(--color-border)]">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface)]">
                <tr>
                  <HeaderCell>{copy.headers.rank}</HeaderCell>
                  <HeaderCell>{copy.headers.market}</HeaderCell>
                  <HeaderCell>{copy.headers.overall}</HeaderCell>
                  <HeaderCell>{copy.headers.spread}</HeaderCell>
                  <HeaderCell>{copy.headers.volatility}</HeaderCell>
                  <HeaderCell>{copy.headers.storageFit}</HeaderCell>
                  <HeaderCell>{copy.headers.fcasEss}</HeaderCell>
                  <HeaderCell>{copy.headers.gridRisk}</HeaderCell>
                  <HeaderCell>{copy.headers.revenue}</HeaderCell>
                  <HeaderCell>{copy.headers.quality}</HeaderCell>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.candidate_key} className="border-t border-[var(--color-border)]">
                    <Cell>#{item.rank}</Cell>
                    <Cell>
                      <div className="font-medium">{item.label}</div>
                      <div className="text-xs text-[var(--color-muted)]">{item.market}</div>
                    </Cell>
                    <Cell>
                      <div className={`inline-flex rounded border px-2 py-1 font-mono ${toneClass(item.overall_score)}`}>{item.overall_score}</div>
                    </Cell>
                    <Cell>{item.spread_score}</Cell>
                    <Cell>{item.volatility_score}</Cell>
                    <Cell>{item.storage_fit_score}</Cell>
                    <Cell>{item.fcas_or_ess_opportunity_score}</Cell>
                    <Cell>{item.grid_risk_score}</Cell>
                    <Cell>{item.revenue_concentration_score}</Cell>
                    <Cell>
                      <DataQualityBadge metadata={{ data_quality_score: item.data_quality_score, data_grade: item.market === 'WEM' ? 'preview' : 'analytical' }} lang={lang} />
                    </Cell>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function HeaderCell({ children }) {
  return <th className="px-3 py-3 text-left text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">{children}</th>;
}

function Cell({ children }) {
  return <td className="px-3 py-3 align-top">{children}</td>;
}

function Metric({ label, value }) {
  return (
    <div className="rounded bg-[var(--color-surface)] px-2 py-2">
      <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
      <div className="font-mono text-sm">{value}</div>
    </div>
  );
}
