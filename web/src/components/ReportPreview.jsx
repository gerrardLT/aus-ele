import { useEffect, useState } from 'react';
import { fetchJson } from '../lib/apiClient';

const REPORT_TYPES = ['monthly_market_report', 'investment_memo_draft'];

export default function ReportPreview({ year, region, month = 'ALL', apiBase, t }) {
  const [reportType, setReportType] = useState('monthly_market_report');
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);
    const params = new URLSearchParams({ report_type: reportType, year: String(year), region });
    if (month && month !== 'ALL') params.set('month', month);
    fetchJson(`${apiBase}/reports/generate?${params.toString()}`)
      .then((res) => {
        setPayload(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [apiBase, month, region, reportType, year]);

  return (
    <div className="mt-16 pt-12 border-t border-[var(--color-border)]">
      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-serif">{t.title}</h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">{t.subtitle}</p>
        </div>
        <div className="flex gap-2">
          {REPORT_TYPES.map((key) => (
            <button
              key={key}
              onClick={() => setReportType(key)}
              className={`rounded-full border px-4 py-2 text-sm ${reportType === key ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]' : 'border-[var(--color-border)]'}`}
            >
              {t.reportTypes?.[key] || key}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="rounded border border-[var(--color-border)] p-6 text-sm text-[var(--color-muted)]">{t.loading}</div>
      ) : payload ? (
        <div className="rounded border border-[var(--color-border)] p-6">
          <div className="mb-4">
            <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">{payload.report_type}</div>
            <h3 className="text-2xl font-serif">{payload.title}</h3>
          </div>
          <div className="space-y-4">
            {payload.sections?.map((section) => (
              <div key={section.section_key} className="rounded border border-[var(--color-border)] p-4">
                <div className="mb-2 text-sm font-semibold">{section.title}</div>
                <pre className="whitespace-pre-wrap break-words text-xs text-[var(--color-muted)]">
                  {typeof section.summary === 'string' ? section.summary : JSON.stringify(section.summary, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
