/**
 * ExportPreviewModal — PDF 导出预览弹窗（2026-08-11）
 *
 * 交互：点击「导出 PDF」→ 弹出预览（报告 + 完整推理过程）→ 确认后生成真实
 * PDF 文件下载（html2pdf.js = html2canvas + jsPDF），不再直接跳转浏览器打印。
 *
 * 注意：html2canvas 不支持 oklch() 颜色，导出文档全部使用显式 hex 内联样式，
 * 不依赖主题 CSS 变量（主题 token 为 oklch）。
 */
import { useRef, useState } from 'react';

// A4 @96dpi 宽度
const PAGE_WIDTH = 794;

const C = {
  bg: '#ffffff',
  text: '#1f2937',
  muted: '#6b7280',
  border: '#e5e7eb',
  primary: '#1d4ed8',
  positive: '#15803d',
  negative: '#b91c1c',
  warning: '#b45309',
  surface: '#f9fafb',
};

const STATUS_STYLE = {
  success: { color: C.positive, icon: '✓', label: '成功' },
  timeout: { color: C.warning, icon: '⚠', label: '超时' },
  error: { color: C.negative, icon: '✕', label: '失败' },
  running: { color: C.muted, icon: '●', label: '执行中' },
};

function fmtNum(v) {
  if (typeof v !== 'number') return String(v ?? '—');
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1000) return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(abs < 10 ? 2 : 1);
}

/** 轻量 Markdown 渲染（仅导出用，hex 配色）：### 标题 / 列表 / **加粗** / 段落 */
function PlainMarkdown({ text }) {
  const lines = (text || '').split('\n');
  const els = [];
  let key = 0;
  const inline = (s) => {
    const parts = s.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((p, i) =>
      p.startsWith('**') && p.endsWith('**') ? (
        <strong key={i} style={{ color: C.text }}>{p.slice(2, -2)}</strong>
      ) : (
        <span key={i}>{p}</span>
      ),
    );
  };
  for (const line of lines) {
    const t = line.trim();
    if (!t) {
      els.push(<div key={key++} style={{ height: 6 }} />);
    } else if (t.startsWith('### ')) {
      els.push(<div key={key++} style={{ fontSize: 13, fontWeight: 700, color: C.text, margin: '10px 0 4px' }}>{t.slice(4)}</div>);
    } else if (t.startsWith('## ')) {
      els.push(<div key={key++} style={{ fontSize: 14, fontWeight: 700, color: C.text, margin: '12px 0 5px' }}>{t.slice(3)}</div>);
    } else if (t.startsWith('# ')) {
      els.push(<div key={key++} style={{ fontSize: 15, fontWeight: 700, color: C.text, margin: '12px 0 6px' }}>{t.slice(2)}</div>);
    } else if (t.startsWith('- ') || t.startsWith('• ')) {
      els.push(
        <div key={key++} style={{ fontSize: 11, lineHeight: '18px', color: C.muted, paddingLeft: 12 }}>
          • {inline(t.slice(2))}
        </div>,
      );
    } else {
      els.push(<div key={key++} style={{ fontSize: 11, lineHeight: '18px', color: C.muted }}>{inline(t)}</div>);
    }
  }
  return <div>{els}</div>;
}

function SectionTitle({ children }) {
  return (
    <div
      className="pdf-no-break"
      style={{
        fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: C.primary,
        textTransform: 'uppercase', borderBottom: `1px solid ${C.border}`,
        paddingBottom: 4, margin: '18px 0 8px',
      }}
    >
      {children}
    </div>
  );
}

export default function ExportPreviewModal({ report, answer, trace, kpis, onClose }) {
  const docRef = useRef(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  const meta = report.metadata || {};
  const params = meta.params || {};

  const handleConfirm = async () => {
    setExporting(true);
    setError('');
    try {
      const mod = await import('html2pdf.js');
      const html2pdf = mod.default || mod;
      const ts = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const filename = `agent-report-${report.region || 'analysis'}-${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-${pad(ts.getHours())}${pad(ts.getMinutes())}.pdf`;
      await html2pdf()
        .set({
          margin: [10, 10, 12, 10],
          filename,
          image: { type: 'jpeg', quality: 0.95 },
          html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: C.bg,
            // html2canvas 不支持 oklch()：在克隆文档中把全部主题变量重写为 hex，
            // 否则祖先元素的 var(--color-*) 计算样式会触发解析异常
            onclone: (clonedDoc) => {
              const styleEl = clonedDoc.createElement('style');
              styleEl.textContent = `
                :root, [data-theme="light"], [data-theme="dark"] {
                  --color-primary: #1d4ed8;
                  --color-background: #ffffff;
                  --color-panel: #ffffff;
                  --color-surface: #ffffff;
                  --color-surface-hover: #f3f4f6;
                  --color-text: #1f2937;
                  --color-muted: #6b7280;
                  --color-border: #e5e7eb;
                  --color-error: #b91c1c;
                  --color-inverted: #1f2937;
                  --color-inverted-text: #ffffff;
                  --color-status-success: #15803d;
                  --color-status-timeout: #b45309;
                  --color-status-error: #b91c1c;
                  --color-negative: #b91c1c;
                  --color-positive: #15803d;
                  --glow-opacity: 0;
                  --glow-color: transparent;
                }
                body { background: #ffffff !important; }
              `;
              clonedDoc.head.appendChild(styleEl);
            },
          },
          jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
          pagebreak: { mode: ['css', 'legacy'], avoid: ['.pdf-no-break'] },
        })
        .from(docRef.current)
        .save();
      onClose();
    } catch (e) {
      setError(`导出失败: ${e.message || e}`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => { if (e.target === e.currentTarget && !exporting) onClose(); }}
    >
      <div className="flex h-[90vh] w-full max-w-[880px] flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-3">
          <div>
            <div className="text-sm font-semibold text-[var(--color-text)]">导出预览</div>
            <div className="text-[11px] text-[var(--color-muted)]">包含完整推理过程与结构化报告 · A4 竖版</div>
          </div>
          <button
            onClick={onClose}
            disabled={exporting}
            className="rounded px-2 py-1 text-xs text-[var(--color-muted)] transition-colors hover:text-[var(--color-text)] disabled:opacity-40"
          >
            ✕ 关闭
          </button>
        </div>

        {/* Preview (scrollable) */}
        <div className="flex-1 overflow-auto bg-[var(--color-surface-hover)] p-4">
          <div className="mx-auto shadow-lg" style={{ width: PAGE_WIDTH }}>
            {/* ── 导出文档本体（hex 内联样式，预览与截图共用） ── */}
            <div
              ref={docRef}
              style={{
                width: PAGE_WIDTH, background: C.bg, color: C.text,
                padding: '28px 36px', fontFamily: "'Archivo', 'Noto Sans SC', sans-serif",
              }}
            >
              {/* 文档头 */}
              <div style={{ borderBottom: `2px solid ${C.primary}`, paddingBottom: 10 }}>
                <div style={{ fontSize: 10, letterSpacing: '0.16em', color: C.muted, textTransform: 'uppercase' }}>
                  AEMO Intelligence · 天枢 · AI 决策引擎
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, margin: '6px 0 4px', lineHeight: '26px' }}>
                  {report.query || '分析执行报告'}
                </div>
                <div style={{ fontSize: 10, color: C.muted }}>
                  {[
                    report.market && report.region ? `${report.market} / ${report.region}` : null,
                    report.workflow_type,
                    report.total_duration_ms > 0 ? `耗时 ${(report.total_duration_ms / 1000).toFixed(1)}s` : null,
                    report.confidence_level ? `置信度 ${report.confidence_level}` : null,
                    report.generated_at ? report.generated_at.slice(0, 19).replace('T', ' ') : null,
                  ].filter(Boolean).join('  ·  ')}
                </div>
              </div>

              {/* 关键 KPI */}
              {kpis && kpis.length > 0 && (
                <div className="pdf-no-break">
                  <SectionTitle>关键指标</SectionTitle>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {kpis.map((k, i) => (
                      <div
                        key={i}
                        style={{
                          flex: 1, border: `1px solid ${C.border}`, borderRadius: 6,
                          padding: '8px 10px', background: C.surface,
                        }}
                      >
                        <div style={{ fontSize: 9, letterSpacing: '0.08em', color: C.muted, textTransform: 'uppercase' }}>{k.label}</div>
                        <div style={{ fontSize: 15, fontWeight: 700, marginTop: 2, color: C.text, fontVariantNumeric: 'tabular-nums' }}>
                          {fmtNum(k.value)}
                          {k.unit && <span style={{ fontSize: 9, fontWeight: 400, color: C.muted, marginLeft: 3 }}>{k.unit}</span>}
                        </div>
                        <div style={{ fontSize: 8, color: C.primary, marginTop: 2 }}>来源: {k.source}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 推理过程（完整 answer） */}
              {answer && (
                <div>
                  <SectionTitle>推理过程</SectionTitle>
                  <PlainMarkdown text={answer} />
                </div>
              )}

              {/* 执行摘要 */}
              {report.executive_summary && (
                <div className="pdf-no-break">
                  <SectionTitle>执行摘要</SectionTitle>
                  <div style={{ fontSize: 11, lineHeight: '18px', color: C.text }}>{report.executive_summary}</div>
                </div>
              )}

              {/* 综合建议 */}
              {report.recommendation && (
                <div className="pdf-no-break">
                  <SectionTitle>综合建议</SectionTitle>
                  <div
                    style={{
                      fontSize: 11, lineHeight: '18px', color: C.text,
                      border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.primary}`,
                      borderRadius: 6, padding: '8px 12px', background: C.surface,
                    }}
                  >
                    {report.recommendation}
                  </div>
                </div>
              )}

              {/* 风险标记 */}
              {report.risk_flags && report.risk_flags.length > 0 && (
                <div className="pdf-no-break">
                  <SectionTitle>风险标记</SectionTitle>
                  {report.risk_flags.map((f, i) => (
                    <div key={i} style={{ fontSize: 10, lineHeight: '17px', color: C.negative, padding: '2px 0' }}>
                      ⚠ {f}
                    </div>
                  ))}
                </div>
              )}

              {/* 数据质量 */}
              {report.data_quality_notes && report.data_quality_notes.length > 0 && (
                <div className="pdf-no-break">
                  <SectionTitle>数据质量</SectionTitle>
                  {report.data_quality_notes.map((n, i) => (
                    <div key={i} style={{ fontSize: 10, lineHeight: '17px', color: C.muted, padding: '1px 0' }}>
                      • {n}
                    </div>
                  ))}
                </div>
              )}

              {/* 执行轨迹 */}
              {trace && trace.length > 0 && (
                <div>
                  <SectionTitle>执行轨迹（{trace.length} 次工具调用）</SectionTitle>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
                    <thead>
                      <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                        <th style={{ textAlign: 'left', padding: '4px 6px', color: C.muted, fontWeight: 600 }}>工具</th>
                        <th style={{ textAlign: 'left', padding: '4px 6px', color: C.muted, fontWeight: 600 }}>状态</th>
                        <th style={{ textAlign: 'right', padding: '4px 6px', color: C.muted, fontWeight: 600 }}>耗时</th>
                        <th style={{ textAlign: 'left', padding: '4px 6px', color: C.muted, fontWeight: 600 }}>摘要</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trace.map((t, i) => {
                        const st = STATUS_STYLE[t.status] || STATUS_STYLE.running;
                        return (
                          <tr key={t.callId || i} className="pdf-no-break" style={{ borderBottom: `1px solid ${C.border}` }}>
                            <td style={{ padding: '4px 6px', fontFamily: 'monospace', color: C.text }}>{t.name}</td>
                            <td style={{ padding: '4px 6px', color: st.color, whiteSpace: 'nowrap' }}>{st.icon} {st.label}</td>
                            <td style={{ padding: '4px 6px', textAlign: 'right', color: C.muted, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                              {typeof t.durationMs === 'number' && t.durationMs > 0 ? `${(t.durationMs / 1000).toFixed(1)}s` : '—'}
                            </td>
                            <td style={{ padding: '4px 6px', color: C.muted }}>{t.summary || ''}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* 基准参数 + 免责声明 */}
              <div className="pdf-no-break" style={{ marginTop: 18, borderTop: `1px solid ${C.border}`, paddingTop: 10 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 9, letterSpacing: '0.08em', color: C.muted, textTransform: 'uppercase' }}>基准参数</span>
                  {params.power_mw && (
                    <span style={{ fontSize: 9, color: C.muted, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 4, padding: '2px 6px' }}>
                      {params.power_mw} MW / {params.duration_hours || 4}h
                    </span>
                  )}
                  {params.capex_per_kwh && (
                    <span style={{ fontSize: 9, color: C.muted, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 4, padding: '2px 6px' }}>
                      CAPEX {params.capex_per_kwh}/kWh
                    </span>
                  )}
                  {params.discount_rate && (
                    <span style={{ fontSize: 9, color: C.muted, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 4, padding: '2px 6px' }}>
                      折现率 {(params.discount_rate * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 8, color: C.muted, marginTop: 8, lineHeight: '13px' }}>
                  本报告由天枢 · AI 决策引擎自动生成，为研究参考，不构成投资建议。数据来源与质量以「数据质量」章节为准。
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-[var(--color-border)] px-5 py-3">
          <div className="text-[11px] text-[var(--color-muted)]">
            {error ? <span className="text-[var(--color-error)]">{error}</span> : '确认后生成 A4 PDF 并自动下载'}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              disabled={exporting}
              className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] transition-colors hover:text-[var(--color-text)] disabled:opacity-40"
            >
              取消
            </button>
            <button
              onClick={handleConfirm}
              disabled={exporting}
              className="rounded bg-[var(--color-primary)] px-4 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {exporting ? '生成中...' : '确认导出 PDF'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
