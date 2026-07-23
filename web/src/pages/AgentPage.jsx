/**
 * AgentPage — AI 编排分析独立页面
 *
 * 全宽双栏布局：
 * - 左栏：查询输入 + 工作流快捷 + 执行历史
 * - 右栏：分析报告展示
 *
 * 路由：/agent
 */

import { useState, useCallback, useEffect } from 'react';
import {
  runAgent,
  runAgentAsync,
  pollTaskUntilDone,
  listWorkflows,
  getAgentHistory,
} from '../lib/agentApi.js';

// ─── Constants ────────────────────────────────────────────────────────────────

const MARKETS = [
  { id: 'NEM', label: 'NEM', sub: '国家电力市场' },
  { id: 'WEM', label: 'WEM', sub: '西澳电力市场' },
];

const REGIONS_NEM = ['NSW1', 'QLD1', 'SA1', 'TAS1', 'VIC1'];
const REGIONS_WEM = ['WEM'];

const STATUS_MAP = {
  completed: { color: 'var(--color-primary)', label: '完成' },
  partial: { color: '#D97706', label: '部分完成' },
  failed: { color: 'var(--color-error)', label: '失败' },
  running: { color: '#6B7280', label: '执行中' },
};

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AgentPage() {
  const [market, setMarket] = useState('NEM');
  const [region, setRegion] = useState('NSW1');
  const [query, setQuery] = useState('');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState('');
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [history, setHistory] = useState([]);

  // Load workflows & history on mount
  useEffect(() => {
    listWorkflows()
      .then((data) => setWorkflows(data.workflows || []))
      .catch(() => {});
    getAgentHistory(10)
      .then((data) => setHistory(data.executions || []))
      .catch(() => {});
  }, []);

  const regions = market === 'NEM' ? REGIONS_NEM : REGIONS_WEM;

  const refreshHistory = useCallback(() => {
    getAgentHistory(10)
      .then((data) => setHistory(data.executions || []))
      .catch(() => {});
  }, []);

  const executeWorkflow = useCallback(
    async (workflowId, customQuery) => {
      setRunning(true);
      setProgress('正在提交分析请求...');
      setReport(null);
      setError(null);

      const params = {
        query: customQuery || query || `运行 ${workflowId} 工作流`,
        market,
        region: region || undefined,
        workflow_template: workflowId || undefined,
        max_steps: 15,
      };

      try {
        // Phase 1: submit the async task. Only a submission failure (async
        // endpoint unavailable) justifies falling back to the sync endpoint.
        let taskId;
        try {
          const submitRes = await runAgentAsync(params);
          taskId = submitRes.task_id;
        } catch (submitErr) {
          console.warn('Async submit failed, falling back to sync:', submitErr.message);
          setProgress('异步模式不可用，切换同步执行...');
          try {
            const syncResult = await runAgent(params);
            setReport(syncResult.report);
            setProgress('');
            refreshHistory();
          } catch (syncErr) {
            setError(syncErr.message || '执行失败');
            setProgress('');
          }
          return;
        }

        // Phase 2: poll the submitted task. A polling failure/timeout must NOT
        // re-run the workflow — the background task is already executing, so a
        // sync fallback here would duplicate the run. Surface an error instead.
        setProgress('已提交，等待执行...');
        try {
          const result = await pollTaskUntilDone(taskId, {
            intervalMs: 2000,
            timeoutMs: 300000,
            onProgress: (msg) => setProgress(msg),
          });
          setReport(result.report);
          setProgress('');
          refreshHistory();
        } catch (pollErr) {
          console.warn('Polling failed:', pollErr.message);
          setError(pollErr.message || '执行超时，请稍后在执行历史中查看结果');
          setProgress('');
          refreshHistory();
        }
      } finally {
        setRunning(false);
      }
    },
    [query, market, region, refreshHistory],
  );

  const handleRun = useCallback(() => {
    if (!query.trim()) return;
    executeWorkflow(null, query.trim());
  }, [query, executeWorkflow]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        handleRun();
      }
    },
    [handleRun],
  );

  return (
    <div className="flex min-h-screen">
      {/* ─── Left Sidebar (navigation) ─── */}
      <aside className="sticky top-0 hidden h-screen w-[220px] shrink-0 flex-col border-r border-white/8 bg-[#13161A] px-4 py-5 text-[#F3F5F7] md:flex">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top_left,rgba(110,168,255,0.14),transparent_60%)]" />

        {/* Brand */}
        <div className="relative border-b border-white/8 pb-4 mb-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/60">
            AEMO Intelligence
          </div>
          <div className="mt-1 text-xs text-white/60">AI 编排分析引擎</div>
        </div>

        {/* Nav links back */}
        <nav className="relative grid gap-0.5">
          {[
            { label: 'NEM 市场', path: '/' },
            { label: 'WEM 市场', path: '/wem' },
            { label: 'Finland', path: '/finland' },
            { label: '开发者门户', path: '/developer' },
          ].map((link) => (
            <a
              key={link.path}
              href={link.path}
              className="flex items-center rounded-md px-3 py-1.5 text-xs text-white/60 transition-all hover:bg-white/4 hover:text-white/70"
            >
              {link.label}
            </a>
          ))}
        </nav>

        {/* History */}
        <div className="relative mt-6 flex-1 overflow-y-auto border-t border-white/8 pt-4">
          <div className="px-1 mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/60">
            执行历史
          </div>
          {history.length === 0 && (
            <p className="px-1 text-[11px] text-white/30">暂无记录</p>
          )}
          <div className="grid gap-1">
            {history.map((item) => (
              <div
                key={item.id}
                className="rounded-md px-2 py-1.5 text-[11px] text-white/50"
              >
                <div className="flex items-center gap-1.5">
                  <span
                    className="h-1.5 w-1.5 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor:
                        STATUS_MAP[item.status]?.color || '#6B7280',
                    }}
                  />
                  <span className="truncate">{item.query}</span>
                </div>
                <div className="mt-0.5 pl-3 text-[10px] text-white/30">
                  {item.market}/{item.region || '—'} ·{' '}
                  {item.total_duration_ms
                    ? `${(item.total_duration_ms / 1000).toFixed(1)}s`
                    : '—'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ─── Main Content ─── */}
      <div className="min-w-0 flex-1">
        {/* Header */}
        <header className="border-b border-[var(--color-border)] px-8 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-serif text-2xl text-[var(--color-text)]">
                AI 编排分析
              </h1>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                自然语言驱动 · 多引擎串联 · 自动综合决策报告
              </p>
            </div>
            <a
              href="/"
              className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]"
            >
              ← 返回市场
            </a>
          </div>
        </header>

        {/* Two-column body */}
        <div className="grid grid-cols-1 gap-0 lg:grid-cols-[420px_1fr]">
          {/* ─── Left Column: Input & Controls ─── */}
          <div className="border-r border-[var(--color-border)] p-6">
            {/* Market & Region selectors */}
            <div className="mb-5 flex gap-3">
              <div className="flex-1">
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
                  市场
                </label>
                <div className="flex gap-1">
                  {MARKETS.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => {
                        setMarket(m.id);
                        setRegion(m.id === 'NEM' ? 'NSW1' : 'WEM');
                      }}
                      className={`flex-1 rounded border px-3 py-2 text-xs font-medium transition-colors ${
                        market === m.id
                          ? 'border-[var(--color-inverted)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                          : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-text)]'
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex-1">
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
                  区域
                </label>
                <select
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
                >
                  {regions.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Query input */}
            <div className="mb-4">
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
                分析请求
              </label>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`描述你的分析需求...\n例如：对 ${region} 做一次完整投资可行性分析`}
                rows={4}
                disabled={running}
                className="w-full resize-none rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text)] placeholder:text-[var(--color-muted)]/50 outline-none transition-colors focus:border-[var(--color-primary)] disabled:opacity-50"
              />
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[10px] text-[var(--color-muted)]">
                  Ctrl+Enter 快速执行
                </span>
              </div>
            </div>

            {/* Run button */}
            <button
              onClick={handleRun}
              disabled={running || !query.trim()}
              className="mb-6 w-full rounded-lg bg-[var(--color-inverted)] py-3 text-sm font-semibold text-[var(--color-inverted-text)] transition-opacity disabled:opacity-40"
            >
              {running ? '执行中...' : '运行分析'}
            </button>

            {/* Workflow shortcuts */}
            <div className="mb-6">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
                预定义工作流
              </div>
              <div className="grid gap-1.5">
                {workflows.map((wf) => (
                  <button
                    key={wf.id}
                    onClick={() => executeWorkflow(wf.id)}
                    disabled={running}
                    className="group flex items-center justify-between rounded-lg border border-[var(--color-border)] px-4 py-2.5 text-left transition-colors hover:border-[var(--color-text)] disabled:opacity-40"
                  >
                    <div>
                      <div className="text-[13px] font-medium text-[var(--color-text)]">
                        {wf.name}
                      </div>
                      <div className="mt-0.5 text-[11px] text-[var(--color-muted)]">
                        {wf.description}
                      </div>
                    </div>
                    <span className="ml-3 text-[10px] text-[var(--color-muted)] opacity-0 transition-opacity group-hover:opacity-100">
                      {wf.steps?.length || '—'} 步
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Progress indicator */}
            {running && progress && (
              <div className="flex items-center gap-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--color-primary)]" />
                <span className="text-xs text-[var(--color-text)]">
                  {progress}
                </span>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 px-4 py-3 text-xs text-[var(--color-error)]">
                {error}
              </div>
            )}
          </div>

          {/* ─── Right Column: Report ─── */}
          <div className="p-6">
            {!report && !running && (
              <div className="flex h-full min-h-[400px] items-center justify-center">
                <div className="text-center">
                  <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--color-border)]">
                    <svg
                      width="24"
                      height="24"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="var(--color-muted)"
                      strokeWidth="1.5"
                    >
                      <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z" />
                      <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z" />
                    </svg>
                  </div>
                  <p className="text-sm text-[var(--color-muted)]">
                    选择工作流或输入分析请求
                  </p>
                  <p className="mt-1 text-xs text-[var(--color-muted)]/60">
                    报告将在此处展示
                  </p>
                </div>
              </div>
            )}

            {report && <ReportView report={report} />}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Report View ──────────────────────────────────────────────────────────────

function ReportView({ report }) {
  const status = STATUS_MAP[report.status] || STATUS_MAP.running;

  return (
    <div className="space-y-6">
      {/* Status bar */}
      <div className="flex items-center gap-3">
        <span
          className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold"
          style={{ borderColor: status.color, color: status.color }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: status.color }}
          />
          {status.label}
        </span>
        {report.total_duration_ms > 0 && (
          <span className="text-[11px] text-[var(--color-muted)]">
            耗时 {(report.total_duration_ms / 1000).toFixed(1)}s
          </span>
        )}
        {report.workflow_type && (
          <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[10px] text-[var(--color-muted)]">
            {report.workflow_type}
          </span>
        )}
      </div>

      {/* Executive Summary */}
      {report.executive_summary && (
        <section>
          <h2 className="mb-2 font-serif text-lg text-[var(--color-text)]">
            执行摘要
          </h2>
          <p className="text-sm leading-6 text-[var(--color-muted)]">
            {report.executive_summary}
          </p>
        </section>
      )}

      {/* Recommendation */}
      {report.recommendation && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
            综合建议
          </h3>
          <p className="text-sm leading-6 text-[var(--color-text)]">
            {report.recommendation}
          </p>
          {report.confidence_level && (
            <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[10px] text-[var(--color-muted)]">
              置信度: {report.confidence_level}
            </div>
          )}
        </section>
      )}

      {/* Stage Results */}
      {report.stage_results && report.stage_results.length > 0 && (
        <section>
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
            分析阶段 ({report.stage_results.length})
          </h3>
          <div className="space-y-1">
            {report.stage_results.map((stage, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] px-4 py-2.5"
              >
                <span
                  className={`h-2 w-2 rounded-full flex-shrink-0 ${
                    stage.status === 'success'
                      ? 'bg-green-500'
                      : stage.status === 'error'
                        ? 'bg-red-500'
                        : 'bg-yellow-500'
                  }`}
                />
                <span className="flex-1 text-[13px] text-[var(--color-text)]">
                  {stage.tool_name}
                </span>
                {stage.duration_ms > 0 && (
                  <span className="text-[11px] tabular-nums text-[var(--color-muted)]">
                    {stage.duration_ms.toFixed(0)}ms
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Risk Flags */}
      {report.risk_flags && report.risk_flags.length > 0 && (
        <section>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
            风险标记
          </h3>
          <div className="space-y-1.5">
            {report.risk_flags.map((flag, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded border border-[var(--color-error)]/20 bg-[var(--color-error)]/5 px-3 py-2 text-xs text-[var(--color-error)]"
              >
                <span className="mt-0.5">⚠</span>
                <span>{flag}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Data Quality */}
      {report.data_quality_notes && report.data_quality_notes.length > 0 && (
        <section>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
            数据质量
          </h3>
          <ul className="space-y-1">
            {report.data_quality_notes.map((note, i) => (
              <li
                key={i}
                className="text-xs leading-5 text-[var(--color-muted)]"
              >
                • {note}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
