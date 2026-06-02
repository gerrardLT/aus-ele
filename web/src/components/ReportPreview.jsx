/**
 * ReportPreview — 报告预览组件
 * - Markdown 风格渲染
 * - "导出 PDF" 按钮（window.print() + @media print）
 * - "复制到剪贴板" 按钮
 * - 报告 sections 用卡片样式渲染，带折叠功能
 */

import { useEffect, useState } from 'react';
import { fetchJson } from '../lib/apiClient';

const REPORT_TYPES = ['monthly_market_report', 'investment_memo_draft'];

const LABELS = {
  zh: {
    title: '报告预览',
    subtitle: '投资备忘录与市场分析报告',
    loading: '加载中...',
    reportTypes: {
      monthly_market_report: '月度市场报告',
      investment_memo_draft: '投资备忘录草稿',
    },
    copy: '复制',
    copied: '已复制',
    exportPdf: '导出 PDF',
  },
  en: {
    title: 'Report Preview',
    subtitle: 'Investment memo and market analysis reports',
    loading: 'Loading...',
    reportTypes: {
      monthly_market_report: 'Monthly Market Report',
      investment_memo_draft: 'Investment Memo Draft',
    },
    copy: 'Copy',
    copied: 'Copied',
    exportPdf: 'Export PDF',
  },
};

function SectionCard({ section, defaultExpanded = true }) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const renderContent = (summary) => {
    if (typeof summary === 'string') {
      return summary.split('\n').map((line, i) => {
        if (line.startsWith('- ') || line.startsWith('* ')) {
          return (
            <li key={i} className="ml-4 list-disc text-sm leading-6 text-[var(--color-text)]">
              {line.replace(/^[-*]\s/, '')}
            </li>
          );
        }
        if (line.startsWith('# ')) {
          return <h4 key={i} className="mt-3 mb-1 text-base font-bold">{line.replace(/^#+\s/, '')}</h4>;
        }
        if (line.startsWith('## ')) {
          return <h5 key={i} className="mt-2 mb-1 text-sm font-semibold">{line.replace(/^#+\s/, '')}</h5>;
        }
        if (line.trim() === '') {
          return <div key={i} className="h-2" />;
        }
        return (
          <p key={i} className="text-sm leading-6 text-[var(--color-text)]">
            {line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
              .split(/(<strong>.*?<\/strong>)/)
              .map((part, j) => {
                if (part.startsWith('<strong>')) {
                  return <strong key={j}>{part.replace(/<\/?strong>/g, '')}</strong>;
                }
                return <span key={j}>{part}</span>;
              })}
          </p>
        );
      });
    }
    return (
      <pre className="whitespace-pre-wrap break-words text-xs text-[var(--color-muted)]">
        {JSON.stringify(summary, null, 2)}
      </pre>
    );
  };

  return (
    <div className="rounded-lg border border-[var(--color-border)] overflow-hidden print:border-none">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between bg-[var(--color-surface)] p-4 text-left hover:bg-[var(--color-surface-hover)] transition-colors"
      >
        <span className="text-sm font-semibold">{section.title}</span>
        <span className="text-xs text-[var(--color-muted)]">{expanded ? '\u25BE' : '\u25B8'}</span>
      </button>
      {expanded && (
        <div className="p-4 space-y-1 print:block">
          {renderContent(section.summary)}
        </div>
      )}
    </div>
  );
}

export default function ReportPreview({ year, region, month = 'ALL', apiBase, t: externalT, lang = 'zh' }) {
  const t = { ...(LABELS[lang] || LABELS.zh), ...(externalT || {}) };
  const [reportType, setReportType] = useState('monthly_market_report');
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);
    const params = new URLSearchParams({ report_type: reportType, year: String(year), region });
    if (month && month !== 'ALL') params.set('month', month);
    fetchJson(`${apiBase}/reports/generate?${params.toString()}`)
      .then((res) => { setPayload(res); setLoading(false); })
      .catch(() => setLoading(false));
  }, [apiBase, month, region, reportType, year]);

  const handleExportPdf = () => {
    window.print();
  };

  const handleCopyToClipboard = async () => {
    if (!payload) return;
    const text = [
      payload.title,
      '',
      ...(payload.sections || []).map((s) => {
        const content = typeof s.summary === 'string' ? s.summary : JSON.stringify(s.summary, null, 2);
        return `## ${s.title}\n\n${content}`;
      }),
    ].join('\n\n');

    try {
      await navigator.clipboard.writeText(text);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  };

  return (
    <div className="mt-12 pt-8 border-t border-[var(--color-border)] print:mt-0 print:pt-0 print:border-none">
      <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-baseline md:justify-between print:hidden">
        <div>
          <h2 className="text-2xl font-serif md:text-[1.75rem]">{t.title}</h2>
          <p className="mt-1 text-xs leading-5 text-[var(--color-muted)] md:overflow-hidden md:text-ellipsis md:whitespace-nowrap">{t.subtitle}</p>
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
        <div className="rounded border border-[var(--color-border)] p-5 print:border-none print:p-0">
          <div className="mb-4 flex items-start justify-between">
            <div>
              <div className="text-xs uppercase tracking-widest text-[var(--color-muted)] print:hidden">{payload.report_type}</div>
              <h3 className="text-2xl font-serif">{payload.title}</h3>
            </div>
            <div className="flex gap-2 print:hidden">
              <button
                onClick={handleCopyToClipboard}
                className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold hover:bg-[var(--color-surface)] transition-colors"
              >
                {copySuccess ? `\u2713 ${t.copied}` : `\uD83D\uDCCB ${t.copy}`}
              </button>
              <button
                onClick={handleExportPdf}
                className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold hover:bg-[var(--color-surface)] transition-colors"
              >
                {`\uD83D\uDCC4 ${t.exportPdf}`}
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {payload.sections?.map((section, index) => (
              <SectionCard key={section.section_key} section={section} defaultExpanded={index < 3} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
