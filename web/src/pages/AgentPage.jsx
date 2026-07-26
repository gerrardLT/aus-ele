/**
 * AgentPage — AI 编排分析独立页面（交互对话 + SSE 实时流式）
 *
 * 全宽双栏布局：
 * - 左栏：导航 + 执行历史
 * - 右栏：多轮对话工作台（市场/区域/工作流控制 + 实时 ReAct 轨迹 + 结构化报告）
 *
 * 对话通过 `streamAgentChat` 消费后端 `POST /chat-stream` 的 SSE 事件流：
 * start / status / token / tool_call / tool_result / answer_end / report / error / done
 * 后端无状态：前端持有完整对话历史，每轮把 history 一并回传。
 *
 * 路由：/agent
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  streamAgentChat,
  listWorkflows,
  getAgentHistory,
  getExecutionDetail,
  deleteExecution,
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

const TOOL_STATUS_COLOR = {
  success: 'bg-green-500',
  error: 'bg-red-500',
  timeout: 'bg-red-500',
};

let msgSeq = 0;
const nextId = () => `m${Date.now()}_${msgSeq++}`;

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AgentPage() {
  const [market, setMarket] = useState('NEM');
  const [region, setRegion] = useState('NSW1');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [history, setHistory] = useState([]);
  const [showParams, setShowParams] = useState(false);
  const [bessParams, setBessParams] = useState({
    power_mw: 100,
    duration_hours: 4,
    capex_per_kwh: 400,
    discount_rate: 0.08,
  });
  const [compareList, setCompareList] = useState([]);
  const sessionIdRef = useRef(null);
  if (!sessionIdRef.current) {
    sessionIdRef.current = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `s_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }

  // Abort controller for the in-flight SSE stream (stop button / unmount).
  const abortRef = useRef(null);
  // Id of the assistant message currently being streamed.
  const activeMsgRef = useRef(null);
  const scrollRef = useRef(null);

  // Load workflows & history on mount
  useEffect(() => {
    listWorkflows()
      .then((data) => setWorkflows(data.workflows || []))
      .catch(() => {});
    refreshHistory();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll to the newest content while streaming.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const regions = market === 'NEM' ? REGIONS_NEM : REGIONS_WEM;

  const refreshHistory = useCallback(() => {
    getAgentHistory(10)
      .then((data) => setHistory(data.executions || []))
      .catch(() => {});
  }, []);

  // Patch the currently-streaming assistant message immutably.
  const patchActive = useCallback((patch) => {
    const id = activeMsgRef.current;
    if (!id) return;
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id
          ? typeof patch === 'function'
            ? { ...m, ...patch(m) }
            : { ...m, ...patch }
          : m,
      ),
    );
  }, []);

  const handleEvent = useCallback(
    (event) => {
      switch (event.type) {
        case 'start':
          patchActive({ executionId: event.execution_id });
          break;
        case 'status':
          patchActive({ status_line: event.message });
          break;
        case 'token':
          patchActive((m) => ({ answer: (m.answer || '') + event.delta }));
          break;
        case 'plan':
          patchActive({ plan: event.plan });
          break;
        case 'reflection':
          patchActive((m) => ({
            reflections: [...(m.reflections || []), { step: event.step, verdict: event.verdict, reason: event.reason }],
          }));
          break;
        case 'tool_call':
          patchActive((m) => ({
            totalSteps: event.total || m.totalSteps,
            trace: [
              ...(m.trace || []),
              {
                callId: event.call_id,
                name: event.name,
                step: event.step,
                total: event.total,
                arguments: event.arguments,
                status: 'running',
              },
            ],
          }));
          break;
        case 'tool_result':
          patchActive((m) => ({
            trace: (m.trace || []).map((t) =>
              t.callId && event.call_id
                ? t.callId === event.call_id
                  ? { ...t, ...resultPatch(event) }
                  : t
                : // Some providers omit call_id in results — match latest running of same name.
                  t.name === event.name && t.status === 'running'
                  ? { ...t, ...resultPatch(event) }
                  : t,
            ),
          }));
          break;
        case 'answer_end':
          patchActive({ answerDone: true });
          break;
        case 'report':
          patchActive((m) => ({
            report: event.report,
            // Prefer the streamed answer; fall back to synthesized summary.
            answer: m.answer || event.answer || '',
            reportAnswer: event.answer,
          }));
          break;
        case 'error':
          patchActive((m) => ({
            error: event.message,
            status_line: '',
            answer: m.answer || '',
          }));
          setError(event.message);
          break;
        case 'done':
          patchActive({ status_line: '', streaming: false });
          break;
        default:
          break;
      }
    },
    [patchActive],
  );

  const sendMessage = useCallback(
    async ({ text, workflowId }) => {
      const query = (text || '').trim();
      if (!query || streaming) return;

      setError(null);

      // Build conversation history (finalized turns only) to send to backend.
      const historyPayload = messages
        .filter((m) => (m.role === 'user' || m.role === 'assistant') && (m.content || m.answer))
        .map((m) => ({
          role: m.role,
          content: m.role === 'assistant' ? m.answer || '' : m.content || '',
        }));

      const userMsg = { id: nextId(), role: 'user', content: query };
      const assistantId = nextId();
      const assistantMsg = {
        id: assistantId,
        role: 'assistant',
        answer: '',
        trace: [],
        status_line: '正在连接分析引擎...',
        streaming: true,
      };
      activeMsgRef.current = assistantId;
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput('');
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const params = {
        query,
        history: historyPayload,
        market,
        region: region || undefined,
        workflow_template: workflowId || undefined,
        max_steps: 15,
        params_override: bessParams,
        session_id: sessionIdRef.current,
      };

      try {
        await streamAgentChat(params, {
          onEvent: handleEvent,
          signal: controller.signal,
        });
      } catch (err) {
        if (err.name === 'AbortError') {
          patchActive({ status_line: '已停止', streaming: false, aborted: true });
        } else {
          setError(err.message || '流式对话失败');
          patchActive({ error: err.message || '流式对话失败', status_line: '', streaming: false });
        }
      } finally {
        patchActive({ streaming: false, status_line: '' });
        abortRef.current = null;
        activeMsgRef.current = null;
        setStreaming(false);
        refreshHistory();
      }
    },
    [messages, streaming, market, region, bessParams, handleEvent, patchActive, refreshHistory],
  );

  const handleSend = useCallback(() => {
    sendMessage({ text: input });
  }, [input, sendMessage]);

  const handleStop = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
  }, []);

  const handleReset = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    setMessages([]);
    setError(null);
    setCompareList([]);
  }, []);

  const handleCompare = useCallback((report) => {
    setCompareList((prev) => {
      if (prev.length >= 2) return [prev[1], report];
      return [...prev, report];
    });
  }, []);

  const handleDeleteHistory = useCallback((id) => {
    deleteExecution(id).then(() => refreshHistory()).catch(() => {});
  }, [refreshHistory]);

  const handleLoadHistory = useCallback(
    async (item) => {
      if (streaming) return;
      try {
        const detail = await getExecutionDetail(item.id);
        if (!detail || !detail.report) return;
        const userMsg = { id: nextId(), role: 'user', content: detail.query || item.query };
        const assistantMsg = {
          id: nextId(),
          role: 'assistant',
          answer: detail.report.executive_summary || '',
          trace: (detail.report.stage_results || []).map((s, i) => ({
            callId: `hist_${i}`,
            name: s.tool_name,
            step: i + 1,
            status: s.status,
            durationMs: s.duration_ms,
            summary: s.summary || '',
          })),
          report: detail.report,
          streaming: false,
          answerDone: true,
        };
        setMessages([userMsg, assistantMsg]);
      } catch {
        // silently ignore load failures
      }
    },
    [streaming],
  );

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <AgentLayout
      market={market}
      setMarket={setMarket}
      region={region}
      setRegion={setRegion}
      regions={regions}
      input={input}
      setInput={setInput}
      messages={messages}
      streaming={streaming}
      error={error}
      workflows={workflows}
      history={history}
      scrollRef={scrollRef}
      onSend={handleSend}
      onStop={handleStop}
      onReset={handleReset}
      onKeyDown={handleKeyDown}
      onLoadHistory={handleLoadHistory}
      showParams={showParams}
      setShowParams={setShowParams}
      bessParams={bessParams}
      setBessParams={setBessParams}
      compareList={compareList}
      setCompareList={setCompareList}
      onCompare={handleCompare}
      onSuggest={(text) => setInput(text)}
      onDeleteHistory={handleDeleteHistory}
      onWorkflow={(wf) =>
        sendMessage({ text: input.trim() || `运行 ${wf.name} 工作流`, workflowId: wf.id })
      }
    />
  );
}

// ─── Event helpers ──────────────────────────────────────────────────────────

function resultPatch(event) {
  return {
    status: event.status,
    durationMs: event.duration_ms,
    summary: event.summary,
    keyMetrics: event.key_metrics,
    error: event.error,
    retryCount: event.retry_count || 0,
  };
}

// ─── Layout ───────────────────────────────────────────────────────────────

function AgentLayout({
  market,
  setMarket,
  region,
  setRegion,
  regions,
  input,
  setInput,
  messages,
  streaming,
  error,
  workflows,
  history,
  scrollRef,
  onSend,
  onStop,
  onReset,
  onKeyDown,
  onWorkflow,
  onLoadHistory,
  showParams,
  setShowParams,
  bessParams,
  setBessParams,
  compareList,
  setCompareList,
  onCompare,
  onSuggest,
  onDeleteHistory,
}) {
  return (
    <div className="flex min-h-screen">
      {/* ─── Left Sidebar (navigation + history) ─── */}
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
              <button
                key={item.id}
                onClick={() => onLoadHistory(item)}
                className="group relative w-full rounded-md px-2 py-1.5 text-left text-[11px] text-white/50 transition-colors hover:bg-white/6 hover:text-white/70"
              >
                <div className="flex items-center gap-1.5">
                  <span
                    className="h-1.5 w-1.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: STATUS_MAP[item.status]?.color || '#6B7280' }}
                  />
                  <span className="truncate">{item.query}</span>
                </div>
                <div className="mt-0.5 pl-3 text-[10px] text-white/30">
                  {item.market}/{item.region || '—'} ·{' '}
                  {item.total_duration_ms
                    ? `${(item.total_duration_ms / 1000).toFixed(1)}s`
                    : '—'}
                </div>
                <span
                  role="button"
                  onClick={(e) => { e.stopPropagation(); onDeleteHistory(item.id); }}
                  className="absolute right-1 top-1 hidden h-4 w-4 items-center justify-center rounded text-[10px] text-white/30 hover:bg-white/10 hover:text-white/70 group-hover:flex"
                >
                  ×
                </span>
              </button>
            ))}
          </div>
        </div>
      </aside>

      {/* ─── Main Content: chat workbench ─── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <header className="border-b border-[var(--color-border)] px-8 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-serif text-2xl text-[var(--color-text)]">AI 编排分析</h1>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                自然语言驱动 · 多引擎串联 · 实时推理轨迹 · 多轮追问
              </p>
            </div>
            <div className="flex items-center gap-2">
              {messages.length > 0 && (
                <button
                  onClick={onReset}
                  className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]"
                >
                  新对话
                </button>
              )}
              <a
                href="/"
                className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]"
              >
                ← 返回市场
              </a>
            </div>
          </div>
        </header>

        {/* Control bar: market / region / workflow chips */}
        <div className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] px-8 py-3">
          <div className="flex items-center gap-1">
            {MARKETS.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  setMarket(m.id);
                  setRegion(m.id === 'NEM' ? 'NSW1' : 'WEM');
                }}
                disabled={streaming}
                className={`rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40 ${
                  market === m.id
                    ? 'border-[var(--color-inverted)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                    : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-text)]'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            disabled={streaming}
            className="rounded border border-[var(--color-border)] bg-transparent px-3 py-1.5 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)] disabled:opacity-40"
          >
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>

          {workflows.length > 0 && (
            <div className="flex flex-1 flex-wrap items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.1em] text-[var(--color-muted)]">
                快捷工作流
              </span>
              {workflows.map((wf) => (
                <button
                  key={wf.id}
                  onClick={() => onWorkflow(wf)}
                  disabled={streaming}
                  title={wf.description}
                  className="rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[11px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)] disabled:opacity-40"
                >
                  {wf.name}
                </button>
              ))}
            </div>
          )}

          {/* Params toggle */}
          <button
            onClick={() => setShowParams((v) => !v)}
            disabled={streaming}
            className={`rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40 ${
              showParams
                ? 'border-[var(--color-inverted)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-text)]'
            }`}
          >
            BESS 参数
          </button>
        </div>

        {/* Expandable BESS parameter panel */}
        {showParams && (
          <div className="flex flex-wrap items-center gap-4 border-b border-[var(--color-border)] px-8 py-3">
            {[
              { key: 'power_mw', label: '功率 (MW)', min: 10, max: 500, step: 10 },
              { key: 'duration_hours', label: '时长 (h)', min: 1, max: 8, step: 0.5 },
              { key: 'capex_per_kwh', label: 'CAPEX ($/kWh)', min: 150, max: 700, step: 25 },
              { key: 'discount_rate', label: '折现率', min: 0.04, max: 0.15, step: 0.01, fmt: (v) => `${(v * 100).toFixed(0)}%` },
            ].map(({ key, label, min, max, step, fmt }) => (
              <label key={key} className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
                <span className="w-20 shrink-0">{label}</span>
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={step}
                  value={bessParams[key]}
                  onChange={(e) => setBessParams((p) => ({ ...p, [key]: Number(e.target.value) }))}
                  disabled={streaming}
                  className="w-24 accent-[var(--color-primary)]"
                />
                <span className="w-14 text-right font-mono text-[11px] text-[var(--color-text)]">
                  {fmt ? fmt(bessParams[key]) : bessParams[key]}
                </span>
              </label>
            ))}
          </div>
        )}

        {/* Conversation */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6">
          {/* Comparison panel */}
          {compareList.length > 0 && (
            <ComparisonPanel reports={compareList} onClear={() => setCompareList([])} />
          )}
          {messages.length === 0 ? (
            <EmptyState region={region} />
          ) : (
            <div className="mx-auto flex max-w-[880px] flex-col gap-6">
              {messages.map((m) =>
                m.role === 'user' ? (
                  <UserBubble key={m.id} text={m.content} />
                ) : (
                  <AssistantMessage key={m.id} message={m} onCompare={onCompare} onSuggest={onSuggest} />
                ),
              )}
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="border-t border-[var(--color-border)] px-8 py-4">
          <div className="mx-auto max-w-[880px]">
            {error && (
              <div className="mb-2 rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 px-4 py-2 text-xs text-[var(--color-error)]">
                {error}
              </div>
            )}
            <div className="flex items-end gap-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={`向分析引擎提问或追问...\n例如：对 ${region} 做一次完整投资可行性分析`}
                rows={2}
                className="min-h-[52px] flex-1 resize-none rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text)] placeholder:text-[var(--color-muted)]/50 outline-none transition-colors focus:border-[var(--color-primary)]"
              />
              {streaming ? (
                <button
                  onClick={onStop}
                  className="h-[52px] shrink-0 rounded-lg border border-[var(--color-error)]/40 px-5 text-sm font-semibold text-[var(--color-error)] transition-colors hover:bg-[var(--color-error)]/10"
                >
                  停止
                </button>
              ) : (
                <button
                  onClick={onSend}
                  disabled={!input.trim()}
                  className="h-[52px] shrink-0 rounded-lg bg-[var(--color-inverted)] px-6 text-sm font-semibold text-[var(--color-inverted-text)] transition-opacity disabled:opacity-40"
                >
                  发送
                </button>
              )}
            </div>
            <div className="mt-1 text-[10px] text-[var(--color-muted)]">
              Ctrl+Enter 发送 · 后端无状态，完整对话上下文由前端维护并逐轮回传
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────

function EmptyState({ region }) {
  return (
    <div className="flex h-full min-h-[400px] items-center justify-center">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--color-border)]">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--color-muted)" strokeWidth="1.5">
            <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z" />
            <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z" />
          </svg>
        </div>
        <p className="text-sm text-[var(--color-muted)]">输入分析请求或选择快捷工作流开始对话</p>
        <p className="mt-1 text-xs text-[var(--color-muted)]/60">
          实时推理轨迹与结构化报告将在此逐步展示 · 例如「对 {region} 做投资可行性分析」
        </p>
      </div>
    </div>
  );
}

// ─── Message bubbles ────────────────────────────────────────────────────────

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-[var(--color-inverted)] px-4 py-2.5 text-sm leading-6 text-[var(--color-inverted-text)]">
        {text}
      </div>
    </div>
  );
}

function AssistantMessage({ message, onCompare, onSuggest }) {
  const { answer, trace, status_line, error, report, streaming, answerDone, plan, reflections } = message;
  const hasTrace = trace && trace.length > 0;
  const isDone = !streaming;

  return (
    <div className="flex flex-col gap-3">
      {/* Live status line */}
      {status_line && (
        <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--color-primary)]" />
          {status_line}
        </div>
      )}

      {/* Plan view */}
      {plan && <PlanView plan={plan} />}

      {/* ① Structured report (conclusion) — always visible, top priority */}
      {report && (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <ReportView report={report} onCompare={onCompare} onSuggest={onSuggest} />
        </div>
      )}

      {/* ② Streamed answer / thinking — collapsible after done */}
      {answer && (
        <Collapsible
          title="推理过程"
          defaultOpen={!isDone}
          badge={streaming && !answerDone ? '生成中' : undefined}
        >
          <MarkdownText text={answer} streaming={streaming && !answerDone} />
        </Collapsible>
      )}

      {/* ③ Tool-call trace (steps) — collapsible after done */}
      {hasTrace && (
        <Collapsible
          title={`分析步骤 (${trace.length})`}
          defaultOpen={!isDone}
          badge={trace.some((t) => t.status === 'running') ? '执行中' : undefined}
        >
          <ToolTrace trace={trace} totalSteps={message.totalSteps} />
        </Collapsible>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 px-4 py-2.5 text-xs text-[var(--color-error)]">
          {error}
        </div>
      )}
    </div>
  );
}

// ─── Lightweight markdown renderer (no dependency) ─────────────────────────────

function MarkdownText({ text, streaming }) {
  const lines = (text || '').split('\n');
  const els = [];
  let key = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      els.push(<div key={key++} className="h-2" />);
    } else if (trimmed.startsWith('### ')) {
      els.push(<h4 key={key++} className="mb-1 mt-3 text-[12px] font-semibold text-[var(--color-text)]">{trimmed.slice(4)}</h4>);
    } else if (trimmed.startsWith('## ')) {
      els.push(<h3 key={key++} className="mb-1 mt-3 text-[13px] font-semibold text-[var(--color-text)]">{trimmed.slice(3)}</h3>);
    } else if (trimmed.startsWith('# ')) {
      els.push(<h3 key={key++} className="mb-1.5 mt-3 text-sm font-semibold text-[var(--color-text)]">{trimmed.slice(2)}</h3>);
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
      els.push(<div key={key++} className="pl-3 text-[13px] leading-6 text-[var(--color-muted)] before:mr-1.5 before:content-['•']">{renderInline(trimmed.slice(2))}</div>);
    } else {
      els.push(<p key={key++} className="text-[13px] leading-6 text-[var(--color-muted)]">{renderInline(trimmed)}</p>);
    }
  }

  return (
    <div>
      {els}
      {streaming && <span className="ml-0.5 animate-pulse text-[var(--color-text)]">▍</span>}
    </div>
  );
}

function renderInline(text) {
  // Handle **bold** markers
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-medium text-[var(--color-text)]">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

// ─── Collapsible section (progressive disclosure) ─────────────────────────────

function Collapsible({ title, defaultOpen = false, badge, children }) {
  const [open, setOpen] = useState(defaultOpen);

  // Auto-collapse when streaming ends (defaultOpen flips from true → false).
  const prevDefault = useRef(defaultOpen);
  useEffect(() => {
    if (prevDefault.current && !defaultOpen) {
      setOpen(false);
    }
    prevDefault.current = defaultOpen;
  }, [defaultOpen]);

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className={`shrink-0 text-[var(--color-muted)] transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
        >
          <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
          {title}
        </span>
        {badge && (
          <span className="ml-1 rounded-full bg-[var(--color-primary)]/10 px-2 py-0.5 text-[10px] text-[var(--color-primary)]">
            {badge}
          </span>
        )}
      </button>
      {open && <div className="border-t border-[var(--color-border)] px-4 py-3">{children}</div>}
    </div>
  );
}

// ─── Error recovery suggestions ────────────────────────────────────────────────

function getErrorSuggestion(toolName, errorMsg) {
  const msg = (errorMsg || '').toLowerCase();
  if (msg.includes('no_data') || msg.includes('no projects') || msg.includes('not found'))
    return '该区域数据不足，尝试切换年份或区域';
  if (msg.includes('connection') || msg.includes('timeout'))
    return '数据库连接异常，稍后重试';
  if (msg.includes('capacity') || msg.includes('loader'))
    return '容量数据文件缺失或格式异常';
  if (toolName === 'co_optimized_backtest' && msg.includes('infeasible'))
    return 'MILP 求解不可行，尝试缩短时长或减少 FCAS 服务';
  if (toolName === 'forward_spread_projection')
    return '前瞻引擎依赖煤电退役数据，确认 data/ 目录下文件完整';
  return null;
}

// ─── Tool trace (ReAct live steps) ──────────────────────────────────────────

function ToolTrace({ trace, totalSteps }) {
  const doneCount = trace.filter((t) => t.status !== 'running').length;
  const total = totalSteps || trace.length;

  return (
    <div className="space-y-1.5">
      {/* Progress bar */}
      {total > 1 && (
        <div className="mb-2 flex items-center gap-2">
          <div className="h-1 flex-1 rounded-full bg-[var(--color-border)]">
            <div
              className="h-1 rounded-full bg-[var(--color-primary)] transition-all duration-300"
              style={{ width: `${(doneCount / total) * 100}%` }}
            />
          </div>
          <span className="text-[10px] tabular-nums text-[var(--color-muted)]">
            {doneCount}/{total}
          </span>
        </div>
      )}
      {trace.map((t, i) => (
        <div
          key={t.callId || `${t.name}_${i}`}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
        >
          <div className="flex items-center gap-2">
            {t.status === 'running' ? (
              <span className="h-2 w-2 flex-shrink-0 animate-pulse rounded-full bg-yellow-500" />
            ) : (
              <span
                className={`h-2 w-2 flex-shrink-0 rounded-full ${
                  TOOL_STATUS_COLOR[t.status] || 'bg-yellow-500'
                }`}
              />
            )}
            <span className="font-mono text-[12px] text-[var(--color-text)]">{t.name}</span>
            {typeof t.step === 'number' && (
              <span className="text-[10px] text-[var(--color-muted)]">· 步骤 {t.step}</span>
            )}
            {t.status === 'running' && (
              <span className="text-[10px] text-[var(--color-muted)]">执行中...</span>
            )}
            {typeof t.durationMs === 'number' && t.durationMs > 0 && (
              <span className="ml-auto text-[10px] tabular-nums text-[var(--color-muted)]">
                {t.durationMs.toFixed(0)}ms
                {t.retryCount > 0 && <span className="ml-1 text-[var(--color-primary)]">重试×{t.retryCount}</span>}
              </span>
            )}
          </div>
          {t.summary && (
            <div className="mt-1 pl-4 text-[11px] leading-5 text-[var(--color-muted)]">
              {t.summary}
            </div>
          )}
          {t.error && (
            <div className="mt-1 pl-4 text-[11px] leading-5 text-[var(--color-error)]">
              {t.error}
              {getErrorSuggestion(t.name, t.error) && (
                <span className="ml-1 text-[var(--color-muted)]">
                  → {getErrorSuggestion(t.name, t.error)}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Report View ──────────────────────────────────────────────────────────────

function ReportView({ report, onCompare, onSuggest }) {
  const status = STATUS_MAP[report.status] || STATUS_MAP.running;

  const handleExportPDF = () => {
    window.print();
  };

  return (
    <div className="space-y-6">
      {/* Status bar */}
      <div className="flex items-center gap-3">
        <span
          className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold"
          style={{ borderColor: status.color, color: status.color }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: status.color }} />
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
        <button
          onClick={handleExportPDF}
          className="ml-auto rounded border border-[var(--color-border)] px-2.5 py-1 text-[10px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)] print:hidden"
        >
          导出 PDF
        </button>
      </div>

      {/* Executive Summary */}
      {report.executive_summary && (
        <section>
          <h2 className="mb-2 font-serif text-lg text-[var(--color-text)]">执行摘要</h2>
          <p className="text-sm leading-6 text-[var(--color-muted)]">{report.executive_summary}</p>
        </section>
      )}

      {/* Recommendation */}
      {report.recommendation && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
            综合建议
          </h3>
          <p className="text-sm leading-6 text-[var(--color-text)]">{report.recommendation}</p>
          {report.confidence_level && (
            <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[10px] text-[var(--color-muted)]">
              置信度: {report.confidence_level}
            </div>
          )}
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
              <li key={i} className="text-xs leading-5 text-[var(--color-muted)]">
                • {note}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Footer: base params + suggested follow-ups */}
      <ReportFooter report={report} onCompare={onCompare} onSuggest={onSuggest} />
    </div>
  );
}

function ReportFooter({ report, onCompare, onSuggest }) {
  const params = report.metadata?.params;
  const hasParams = params && (params.power_mw || params.duration_hours);

  const suggestions = [];
  if (hasParams) {
    suggestions.push(`如果 CAPEX 降到 ${Math.round((params.capex_per_kwh || 400) * 0.75)}/kWh，结果会怎样？`);
    suggestions.push('换成 2h 储能时长对比一下？');
  }
  suggestions.push('哪些风险因素最可能压低收益？');

  return (
    <section className="border-t border-[var(--color-border)] pt-4 mt-2">
      {hasParams && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
            基准参数
          </span>
          {params.power_mw && (
            <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[10px] text-[var(--color-muted)]">
              {params.power_mw} MW / {params.duration_hours || 4}h
            </span>
          )}
          {params.capex_per_kwh && (
            <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[10px] text-[var(--color-muted)]">
              CAPEX {params.capex_per_kwh}/kWh
            </span>
          )}
          {params.discount_rate && (
            <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[10px] text-[var(--color-muted)]">
              折现率 {(params.discount_rate * 100).toFixed(0)}%
            </span>
          )}
          {onCompare && (
            <button
              onClick={() => onCompare(report)}
              className="ml-auto rounded border border-[var(--color-border)] px-2 py-0.5 text-[10px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
            >
              + 加入对比
            </button>
          )}
        </div>
      )}
      <div>
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
          可以继续追问
        </span>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => onSuggest && onSuggest(s)}
              className="rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[11px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Plan View ────────────────────────────────────────────────────────────────

function PlanView({ plan }) {
  return (
    <div className="rounded-xl border border-[var(--color-primary)]/20 bg-[var(--color-surface)] px-4 py-3">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-primary)]">
          分析计划
        </span>
        {plan.goal && <span className="text-[11px] text-[var(--color-muted)]">{plan.goal}</span>}
      </div>
      {plan.steps && plan.steps.length > 0 && (
        <ol className="space-y-0.5 pl-4">
          {plan.steps.map((s, i) => (
            <li key={i} className="list-decimal text-[11px] leading-5 text-[var(--color-muted)]">{s}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ─── Comparison Panel ──────────────────────────────────────────────────────────

function ComparisonPanel({ reports, onClear }) {
  if (reports.length === 0) return null;

  return (
    <div className="mb-6 rounded-xl border border-[var(--color-primary)]/30 bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-primary)]">
          对比视图 ({reports.length}/2)
        </span>
        <button
          onClick={onClear}
          className="rounded border border-[var(--color-border)] px-2 py-0.5 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-text)]"
        >
          清除
        </button>
      </div>
      <div className={`grid gap-4 ${reports.length === 2 ? 'grid-cols-2' : 'grid-cols-1'}`}>
        {reports.map((r, i) => {
          const p = r.metadata?.params || {};
          const npv = r.stage_results?.find((s) => s.tool_name === 'investment_analysis');
          return (
            <div key={i} className="rounded-lg border border-[var(--color-border)] p-3">
              <div className="mb-2 text-[11px] font-medium text-[var(--color-text)]">
                {r.region} · {p.power_mw || '?'}MW/{p.duration_hours || '?'}h · CAPEX {p.capex_per_kwh || '?'}
              </div>
              <div className="space-y-1 text-[11px] text-[var(--color-muted)]">
                <div>状态: {STATUS_MAP[r.status]?.label || r.status}</div>
                <div>置信度: {r.confidence_level}</div>
                {r.executive_summary && (
                  <div className="line-clamp-3">{r.executive_summary}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
