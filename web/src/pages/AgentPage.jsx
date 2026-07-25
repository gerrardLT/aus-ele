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
        case 'tool_call':
          patchActive((m) => ({
            trace: [
              ...(m.trace || []),
              {
                callId: event.call_id,
                name: event.name,
                step: event.step,
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
    [messages, streaming, market, region, handleEvent, patchActive, refreshHistory],
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
  }, []);

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
                className="w-full rounded-md px-2 py-1.5 text-left text-[11px] text-white/50 transition-colors hover:bg-white/6 hover:text-white/70"
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
        </div>

        {/* Conversation */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6">
          {messages.length === 0 ? (
            <EmptyState region={region} />
          ) : (
            <div className="mx-auto flex max-w-[880px] flex-col gap-6">
              {messages.map((m) =>
                m.role === 'user' ? (
                  <UserBubble key={m.id} text={m.content} />
                ) : (
                  <AssistantMessage key={m.id} message={m} />
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

function AssistantMessage({ message }) {
  const { answer, trace, status_line, error, report, streaming, answerDone } = message;
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

      {/* ① Structured report (conclusion) — always visible, top priority */}
      {report && (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <ReportView report={report} />
        </div>
      )}

      {/* ② Streamed answer / thinking — collapsible after done */}
      {answer && (
        <Collapsible
          title="推理过程"
          defaultOpen={!isDone}
          badge={streaming && !answerDone ? '生成中' : undefined}
        >
          <div className="whitespace-pre-wrap text-sm leading-6 text-[var(--color-text)]">
            {answer}
            {streaming && !answerDone && <span className="ml-0.5 animate-pulse">▍</span>}
          </div>
        </Collapsible>
      )}

      {/* ③ Tool-call trace (steps) — collapsible after done */}
      {hasTrace && (
        <Collapsible
          title={`分析步骤 (${trace.length})`}
          defaultOpen={!isDone}
          badge={trace.some((t) => t.status === 'running') ? '执行中' : undefined}
        >
          <ToolTrace trace={trace} />
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

// ─── Tool trace (ReAct live steps) ──────────────────────────────────────────

function ToolTrace({ trace }) {
  return (
    <div className="space-y-1.5">
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
            </div>
          )}
        </div>
      ))}
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
                <span className="flex-1 text-[13px] text-[var(--color-text)]">{stage.tool_name}</span>
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
              <li key={i} className="text-xs leading-5 text-[var(--color-muted)]">
                • {note}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
