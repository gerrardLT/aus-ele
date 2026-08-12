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

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  streamAgentChat,
  listWorkflows,
  getAgentHistory,
  getExecutionDetail,
  deleteExecution,
  clearAllHistory,
} from '../lib/agentApi.js';
import ChartRenderer from '../components/ChartRenderer.jsx';
import ExportPreviewModal from '../components/ExportPreviewModal.jsx';

// ─── Constants ────────────────────────────────────────────────────────────────

const MARKETS = [
  { id: 'NEM', label: 'NEM', sub: '国家电力市场' },
  { id: 'WEM', label: 'WEM', sub: '西澳电力市场' },
];

const REGIONS_NEM = ['NSW1', 'QLD1', 'SA1', 'TAS1', 'VIC1'];
const REGIONS_WEM = ['WEM'];

// 状态三色恒与图标双编码（DESIGN.md：色盲安全，颜色不作为唯一信息通道）
const STATUS_MAP = {
  completed: { color: 'var(--color-status-success)', icon: '✓', label: '完成' },
  partial: { color: 'var(--color-status-timeout)', icon: '⚠', label: '部分完成' },
  failed: { color: 'var(--color-status-error)', icon: '✕', label: '失败' },
  running: { color: 'var(--color-muted)', icon: '●', label: '执行中' },
};

// 工具级执行状态（Dynamic Checklist 六态：含 cached/degraded）
const TOOL_STATUS_META = {
  success: { icon: '✓', color: 'var(--color-status-success)', label: '成功' },
  running: { icon: '●', color: 'var(--color-primary)', label: '执行中' },
  timeout: { icon: '⏱', color: 'var(--color-status-timeout)', label: '超时' },
  error: { icon: '✕', color: 'var(--color-status-error)', label: '失败' },
  cached: { icon: '↺', color: 'var(--color-muted)', label: '缓存' },
};

function StatusIcon({ status, meta = TOOL_STATUS_META }) {
  const m = meta[status] || meta.running;
  return (
    <span
      aria-label={m.label}
      className={`inline-flex shrink-0 items-center justify-center text-[11px] leading-none ${
        status === 'running' ? 'animate-pulse' : ''
      }`}
      style={{ color: m.color, width: 14 }}
    >
      {m.icon}
    </span>
  );
}

// 负值三重编码（DESIGN.md：红 + 负号 + 括号，防暗底误读负号）
function formatSigned(value, fmt = (v) => v.toLocaleString('en-US', { maximumFractionDigits: 0 })) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (n < 0) {
    return (
      <span style={{ color: 'var(--color-negative)' }}>
        ({fmt(Math.abs(n))})
      </span>
    );
  }
  return fmt(n);
}

// 错误归因分离（DESIGN.md：工具故障 ≠ AI 能力，不把外部问题归咎于 agent）
function attributeError(toolName, errorMsg) {
  const msg = (errorMsg || '').toLowerCase();
  if (msg.includes('不存在') || msg.includes('does not exist') || msg.includes('尚未同步'))
    return { text: errorMsg, external: true, hint: '外部数据未就绪，与 AI 能力无关' };
  if (msg.includes('timeout') || msg.includes('超时'))
    return { text: errorMsg, external: true, hint: '计算超出时间预算（可重试或降低参数规模）' };
  if (msg.includes('connection') || msg.includes('502') || msg.includes('503'))
    return { text: errorMsg, external: true, hint: '外部服务不可达，稍后重试' };
  return { text: errorMsg, external: false, hint: null };
}

let msgSeq = 0;
const nextId = () => `m${Date.now()}_${msgSeq++}`;

// 分析模式（工具子集暴露 PoC 灰度，2026-08-07）：
// full=全量动作空间（默认，行为不变）；routed=意图路由（后端自动分类，
// 无法归类回落全量）；其余=显式阶段子集（无路由风险）。
const TOOL_MODES = [
  { id: 'full', label: '全量工具空间' },
  { id: 'routed', label: '智能路由（灰度）' },
  { id: 'stage1_screening', label: '市场筛选子集' },
  { id: 'stage2_revenue', label: '收入分析子集' },
  { id: 'stage4_outlook', label: '风险前瞻子集' },
  { id: 'stage6_financial', label: '财务建模子集' },
  { id: 'multi_region_decision', label: '多区域对比子集' },
  { id: 'data_exploration', label: '数据探索子集' },
];

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AgentPage() {
  const [market, setMarket] = useState('NEM');
  const [region, setRegion] = useState('NSW1');
  const [toolMode, setToolMode] = useState('full');
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

  // 区域合并市场语义（2026-08-11 精简）：WEM 作为区域选项，市场由区域推导，
  // 移除独立的 NEM/WEM 开关（原双控件互为冗余）
  const regions = [...REGIONS_NEM, ...REGIONS_WEM];

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
            // Capture chart data from tool results
            charts: event.chart ? [...(m.charts || []), event.chart] : m.charts,
            // Capture download link from export_data
            downloadLink: event.download_path ? event.download_path : m.downloadLink,
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
        // 工具暴露模式：routed=开启意图路由；显式子集直传 profile；full=缺省全量
        ...(toolMode === 'routed'
          ? { enable_tool_routing: true }
          : toolMode !== 'full'
            ? { tool_profile: toolMode }
            : {}),
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
    [messages, streaming, market, region, bessParams, toolMode, handleEvent, patchActive, refreshHistory],
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
    // 新对话 = 新会话（多轮持久化分组依赖，2026-08-11）
    sessionIdRef.current = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `s_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }, []);

  const handleCompare = useCallback((report) => {
    setCompareList((prev) => {
      if (prev.length >= 2) return [prev[1], report];
      return [...prev, report];
    });
  }, []);

  const handleDeleteHistory = useCallback((ids) => {
    // 乐观移除：立即从列表消失，不让后端补满窗口造成"删不掉"错觉（2026-08-11 修复）；
    // 支持会话分组整组删除（ids 为数组）；失败时回滚并提示。
    const idList = Array.isArray(ids) ? ids : [ids];
    setHistory((prev) => prev.filter((h) => !idList.includes(h.id)));
    Promise.all(idList.map((id) => deleteExecution(id))).catch((e) => {
      setError(`删除历史失败: ${e.message || e}`);
      refreshHistory();
    });
  }, [refreshHistory]);

  const handleClearHistory = useCallback(() => {
    // 清空全部（2026-08-11）：二次确认 + 乐观清空 + 失败回滚
    if (!window.confirm('确定清空全部会话历史？此操作不可恢复。')) return;
    setHistory([]);
    clearAllHistory().catch((e) => {
      setError(`清空历史失败: ${e.message || e}`);
      refreshHistory();
    });
  }, [refreshHistory]);

  const handleLoadHistory = useCallback(
    async (item) => {
      if (streaming) return;
      try {
        const detail = await getExecutionDetail(item.id);
        if (!detail || !detail.report) return;
        // 多轮会话回载（2026-08-11）：history 为当轮之前的完整对话上下文，
        // 逐轮还原 user/assistant 消息，再拼接当轮问答。
        const msgs = [];
        for (const turn of detail.history || []) {
          if (turn.role === 'user') {
            msgs.push({ id: nextId(), role: 'user', content: turn.content || '' });
          } else {
            msgs.push({
              id: nextId(), role: 'assistant', answer: turn.content || '',
              streaming: false, answerDone: true,
            });
          }
        }
        msgs.push({ id: nextId(), role: 'user', content: detail.query || item.query });
        msgs.push({
          id: nextId(),
          role: 'assistant',
          // 完整推理文本优先（answer_text 持久化，2026-08-11）；旧记录回退摘要
          answer: detail.answer || detail.report.executive_summary || '',
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
        });
        setMessages(msgs);
        // 追问续接该会话（而非当前页面会话）
        if (detail.session_id) sessionIdRef.current = detail.session_id;
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

  // 会话分组（2026-08-11）：按 session_id 合并多轮记录为一条会话
  // （history 按时间倒序，组内 [0] 为最新轮、末位为首轮；无 session 旧记录各自成组）
  const historyGroups = useMemo(() => {
    const map = new Map();
    for (const item of history) {
      const key = item.session_id || `single_${item.id}`;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    }
    return [...map.values()];
  }, [history]);

  return (
    <AgentLayout
      market={market}
      setMarket={setMarket}
      region={region}
      setRegion={setRegion}
      toolMode={toolMode}
      setToolMode={setToolMode}
      regions={regions}
      input={input}
      setInput={setInput}
      messages={messages}
      streaming={streaming}
      error={error}
      workflows={workflows}
      history={historyGroups}
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
      onClearHistory={handleClearHistory}
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
  toolMode,
  setToolMode,
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
  onClearHistory,
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
          <div className="mb-2 flex items-center justify-between px-1">
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/60">
              执行历史
            </span>
            {history.length > 0 && (
              <button
                onClick={onClearHistory}
                title="清空全部会话历史"
                className="rounded px-1.5 py-0.5 text-[10px] text-white/30 transition-colors hover:bg-white/10 hover:text-white/70"
              >
                清空
              </button>
            )}
          </div>
          {history.length === 0 && (
            <p className="px-1 text-[11px] text-white/30">暂无记录</p>
          )}
          {/* 会话分组视图（2026-08-11）：每组=一次多轮会话，展示首轮问题+轮数；
              点击回载最新轮（含完整对话上下文），× 整组删除 */}
          <div className="grid gap-1">
            {history.map((group) => {
              const latest = group[0];
              const first = group[group.length - 1];
              return (
                <button
                  key={latest.id}
                  onClick={() => onLoadHistory(latest)}
                  className="group relative w-full rounded-md px-2 py-1.5 text-left text-[11px] text-white/50 transition-colors hover:bg-white/6 hover:text-white/70"
                >
                  <div className="flex items-start gap-1.5">
                    <span className="mt-0.5 inline-flex w-3 shrink-0 justify-center text-[9px]" style={{ color: STATUS_MAP[latest.status]?.color || '#6B7280' }}>
                      {STATUS_MAP[latest.status]?.icon || '●'}
                    </span>
                    {/* 两行截断（原单行 truncate 导致用户看不到完整标题，2026-08-11） */}
                    <span className="line-clamp-2 break-words">{first.query}</span>
                  </div>
                  <div className="mt-0.5 pl-3 font-mono text-[10px] tabular-nums text-white/30">
                    {latest.market}/{latest.region || '—'}
                    {group.length > 1 && ` · ${group.length}轮`} ·{' '}
                    {latest.total_duration_ms
                      ? `${(latest.total_duration_ms / 1000).toFixed(1)}s`
                      : '—'}
                  </div>
                  {/* 删除按钮：常显且提高对比度（原 opacity 过低用户找不到，2026-08-11） */}
                  <span
                    role="button"
                    title="删除此会话"
                    onClick={(e) => { e.stopPropagation(); onDeleteHistory(group.map((g) => g.id)); }}
                    className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded text-[12px] text-white/60 transition-colors hover:bg-white/15 hover:text-white"
                  >
                    ×
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </aside>

      {/* ─── Main Content: chat workbench ─── */}
      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top bar: 标题 + 区域 + 工作流 + 操作，合并为单行（2026-08-11 精简） */}
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] px-6 py-2.5">
          <h1 className="font-serif text-base font-semibold text-[var(--color-text)]">AI 编排分析</h1>
          <span className="h-4 w-px bg-[var(--color-border)]" />
          <select
            value={region}
            onChange={(e) => {
              const v = e.target.value;
              setRegion(v);
              setMarket(v === 'WEM' ? 'WEM' : 'NEM');
            }}
            disabled={streaming}
            title="分析区域（选 WEM 自动切换西澳市场语义）"
            className="rounded border border-[var(--color-border)] bg-transparent px-2.5 py-1 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)] disabled:opacity-40"
          >
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>

          {workflows.length > 0 && (
            <div className="flex flex-1 flex-wrap items-center gap-1.5">
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

          <button
            onClick={() => setShowParams((v) => !v)}
            disabled={streaming}
            className={`rounded border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-40 ${
              showParams
                ? 'border-[var(--color-inverted)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-text)]'
            }`}
          >
            BESS 参数
          </button>
          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <button
                onClick={onReset}
                className="rounded border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-muted)] transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]"
              >
                新对话
              </button>
            )}
            <a
              href="/"
              className="rounded border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-muted)] transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]"
            >
              ← 返回市场
            </a>
          </div>
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

        {/* Composer：固定首屏底部，发送按钮内嵌输入框右下角（2026-08-11） */}
        <div className="border-t border-[var(--color-border)] px-8 py-3">
          <div className="mx-auto max-w-[880px]">
            {error && (
              <div className="mb-2 rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 px-4 py-2 text-xs text-[var(--color-error)]">
                {error}
              </div>
            )}
            <div className="relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={`向分析引擎提问或追问... 例如：对 ${region} 做一次完整投资可行性分析（Ctrl+Enter 发送）`}
                rows={2}
                className="min-h-[52px] w-full resize-none rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] py-3 pl-4 pr-12 text-sm text-[var(--color-text)] placeholder:text-[var(--color-muted)]/50 outline-none transition-colors focus:border-[var(--color-primary)]"
              />
              {streaming ? (
                <button
                  onClick={onStop}
                  title="停止"
                  className="absolute bottom-2.5 right-2.5 flex h-7 w-7 items-center justify-center rounded-md border border-[var(--color-error)]/40 text-[10px] text-[var(--color-error)] transition-colors hover:bg-[var(--color-error)]/10"
                >
                  ■
                </button>
              ) : (
                <button
                  onClick={onSend}
                  disabled={!input.trim()}
                  title="发送（Ctrl+Enter）"
                  className="absolute bottom-2.5 right-2.5 flex h-7 w-7 items-center justify-center rounded-md bg-[var(--color-inverted)] text-[var(--color-inverted-text)] transition-opacity hover:opacity-90 disabled:opacity-40"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 19V5" />
                    <path d="m5 12 7-7 7 7" />
                  </svg>
                </button>
              )}
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
  const { answer, trace, status_line, error, report, streaming, answerDone, plan, charts, downloadLink } = message;
  const degraded = report && report.metadata && report.metadata.llm_degraded;
  const hasEvidence = (trace && trace.length > 0) || report || (charts && charts.length > 0) || downloadLink;
  // 结论级 KPI：屏幕唯一展示位在左栏（报告内仅打印可见，去重，2026-08-10）
  const kpis = report ? extractKpis(report) : [];

  return (
    <div className="flex flex-col gap-3">
      {/* Live status line */}
      {status_line && (
        <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--color-primary)]" />
          {status_line}
        </div>
      )}

      {/* 降级横幅（DESIGN.md Screen 5 Pattern B：细条琥珀色，不阻断工作区） */}
      {degraded && <DegradedBanner reason={report.metadata.llm_degraded_reason} />}

      {/* Plan view */}
      {plan && <PlanView plan={plan} />}

      {/* 双栏：左=结论+推理，右=轨迹/报告（窄屏自动堆叠） */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(380px,460px)]">
        <div className="flex min-w-0 flex-col gap-3">
          {/* 左栏窄，2 列布局避免卡片文字截断（2026-08-11 用户反馈） */}
          {kpis.length > 0 && (
            <div className="grid grid-cols-2 gap-2">
              {kpis.map((k, i) => (
                <KpiCard key={i} {...k} />
              ))}
            </div>
          )}
          {answer && (
            <Collapsible
              title="推理过程"
              // 默认展开且流结束后不自动折叠（用户反馈 2026-08-09）；
              // 手动折叠仍可用（Collapsible 仅在 defaultOpen 变化时自动收起）。
              defaultOpen
              badge={streaming && !answerDone ? '生成中' : undefined}
            >
              <MarkdownText text={answer} streaming={streaming && !answerDone} />
            </Collapsible>
          )}
          {error && (
            <div className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 px-4 py-2.5 text-xs text-[var(--color-error)]">
              {error}
            </div>
          )}
        </div>

        {hasEvidence && (
          <EvidencePanel message={message} onCompare={onCompare} onSuggest={onSuggest} />
        )}
      </div>
    </div>
  );
}

// ─── Degraded banner (LLM 不可用 → 模板模式透明化) ────────────────────

function DegradedBanner({ reason }) {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border px-4 py-2.5 text-xs"
      style={{
        borderColor: 'color-mix(in srgb, var(--color-status-timeout) 45%, transparent)',
        background: 'color-mix(in srgb, var(--color-status-timeout) 8%, transparent)',
      }}
    >
      <span style={{ color: 'var(--color-status-timeout)' }}>⚠</span>
      <div>
        <div className="font-medium" style={{ color: 'var(--color-status-timeout)' }}>
          LLM 服务不可用，已降级为确定性模板模式
        </div>
        {reason && <div className="mt-0.5 text-[var(--color-muted)]">{reason}</div>}
      </div>
    </div>
  );
}

// ─── Evidence panel（动态 Tab：轨迹/[图表]/报告；工具清单唯一展示位，2026-08-10 去重重构）───

function EvidencePanel({ message, onCompare, onSuggest }) {
  const { trace, report, charts, totalSteps, downloadLink } = message;
  const [tab, setTab] = useState('trace');

  // 报告生成后自动切换到报告 tab
  useEffect(() => {
    if (report) setTab('report');
  }, [report]);

  // 动态 Tab：图表仅在存在时展示；证据已并入轨迹（去重）
  const tabs = [
    { id: 'trace', label: '轨迹', count: (trace && trace.length) || 0 },
    ...(charts && charts.length > 0 ? [{ id: 'charts', label: '图表', count: charts.length }] : []),
    { id: 'report', label: '报告', count: report ? 1 : 0 },
  ];

  return (
    <div className="flex min-w-0 flex-col self-start rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)]">
      <div className="flex items-center gap-1 border-b border-[var(--color-border)] px-2 pt-2">
        {tabs.map((t) => {
          const disabled = t.count === 0;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              disabled={disabled}
              className={`rounded-t px-2.5 py-1.5 text-[11px] font-medium transition-colors disabled:opacity-30 ${
                active
                  ? 'border border-b-0 border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]'
                  : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
              }`}
            >
              {t.label}
              {t.id !== 'report' && t.count > 0 && (
                <span className="ml-1 font-mono tabular-nums text-[10px]">({t.count})</span>
              )}
            </button>
          );
        })}
      </div>
      <div className="max-h-[600px] overflow-y-auto p-3">
        {tab === 'trace' && (
          <ToolTrace trace={trace || []} totalSteps={totalSteps} downloadLink={downloadLink} />
        )}
        {tab === 'charts' && (
          <div className="flex flex-col gap-3">
            {(charts || []).map((c, i) => (
              <ChartRenderer key={i} chart={c} />
            ))}
          </div>
        )}
        {tab === 'report' && report && (
          <div className="agent-report-print rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <ReportView report={report} answer={message.answer} trace={trace} onCompare={onCompare} onSuggest={onSuggest} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Evidence list 已并入 ToolTrace（2026-08-10 去重重构，工具清单唯一展示位）───

// keyMetrics 展平：递归提取标量叶子（最多 max 个），snake_case → 空格分词
function flattenKeyMetrics(obj, max = 6, prefix = '') {
  const out = [];
  if (!obj || typeof obj !== 'object') return out;
  for (const [k, v] of Object.entries(obj)) {
    if (out.length >= max) break;
    const key = prefix ? `${prefix}.${k}` : k;
    if (v != null && typeof v === 'object' && !Array.isArray(v)) {
      out.push(...flattenKeyMetrics(v, max - out.length, key));
    } else if (typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean') {
      out.push({ k: key.replace(/_/g, ' '), v });
    }
  }
  return out;
}

function fmtMetricValue(v) {
  if (typeof v === 'number') {
    const abs = Math.abs(v);
    if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (abs >= 1000) return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
    if (Number.isInteger(v)) return String(v);
    return v.toFixed(abs < 10 ? 2 : 1);
  }
  return String(v);
}

function ToolTrace({ trace, totalSteps, downloadLink }) {
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
      {trace.map((t, i) => {
        const metrics = flattenKeyMetrics(t.keyMetrics);
        const attr = t.error ? attributeError(t.name, t.error) : null;
        const hasArgs = t.arguments && Object.keys(t.arguments).length > 0;
        return (
          <div
            key={t.callId || `${t.name}_${i}`}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
          >
            <div className="flex items-center gap-2">
              <StatusIcon status={t.status} />
              <span className="font-mono text-[12px] text-[var(--color-text)]">{t.name}</span>
              {typeof t.step === 'number' && (
                <span className="text-[10px] text-[var(--color-muted)]">· 步骤 {t.step}</span>
              )}
              {t.status === 'running' && (
                <span className="text-[10px] text-[var(--color-muted)]">执行中...</span>
              )}
              {typeof t.durationMs === 'number' && t.durationMs > 0 && (
                <span className="ml-auto font-mono text-[10px] tabular-nums text-[var(--color-muted)]">
                  {(t.durationMs / 1000).toFixed(1)}s
                  {t.retryCount > 0 && <span className="ml-1 text-[var(--color-primary)]">重试×{t.retryCount}</span>}
                </span>
              )}
            </div>
            {/* 调用参数（审计透明化，原证据 Tab 能力） */}
            {hasArgs && (
              <div className="mt-1 truncate pl-6 font-mono text-[10px] text-[var(--color-muted)]" title={JSON.stringify(t.arguments)}>
                args: {JSON.stringify(t.arguments)}
              </div>
            )}
            {/* 关键指标（富化：工具真实数据，解决“内容太少”） */}
            {metrics.length > 0 && (
              <div className="mt-1.5 ml-6 grid grid-cols-2 gap-x-3 gap-y-1 rounded-md bg-[var(--color-panel)] px-2.5 py-1.5">
                {metrics.map((m) => (
                  <div key={m.k} className="flex items-baseline justify-between gap-2 text-[10px]">
                    <span className="truncate text-[var(--color-muted)]">{m.k}</span>
                    <span
                      className="shrink-0 font-semibold tabular-nums text-[var(--color-text)]"
                      style={{ fontFamily: 'var(--font-mono-data)' }}
                    >
                      {fmtMetricValue(m.v)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {t.summary && (
              <div className="mt-1 pl-6 text-[11px] leading-5 text-[var(--color-muted)]">
                {t.summary}
              </div>
            )}
            {t.error && (
              <div className="mt-1 pl-6 text-[11px] leading-5" style={{ color: 'var(--color-status-error)' }}>
                {attr ? attr.text : t.error}
                {attr && attr.hint && <span className="ml-1 text-[var(--color-muted)]">· {attr.hint}</span>}
                {getErrorSuggestion(t.name, t.error) && (
                  <span className="ml-1 text-[var(--color-muted)]">→ {getErrorSuggestion(t.name, t.error)}</span>
                )}
              </div>
            )}
          </div>
        );
      })}
      {downloadLink && (
        <a
          href={downloadLink}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-[11px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
        >
          ↓ 下载数据文件
        </a>
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

// ─── Report View ──────────────────────────────────────────────────────────────

// KPI 提取：仅取关键结论级指标（DESIGN.md：禁止逐数字全量徽章）
function extractKpis(report) {
  const kpis = [];
  for (const s of report.stage_results || []) {
    const km = s.key_metrics || {};
    if (s.tool_name === 'investment_analysis' && km.results) {
      const r = km.results;
      // NPV 用紧凑格式（≥1M 显示为 x.xM），避免长数字在窄卡片内被截断（2026-08-11）
      if (r.npv_aud != null)
        kpis.push({
          label: 'NPV', value: r.npv_aud, unit: 'AUD', source: s.tool_name,
          fmt: (v) => (Math.abs(v) >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v.toLocaleString('en-US', { maximumFractionDigits: 0 })),
        });
      if (r.irr_pct != null) kpis.push({ label: 'IRR', value: r.irr_pct, unit: '%', fmt: (v) => v.toFixed(1), source: s.tool_name });
      if (r.payback_years != null) kpis.push({ label: '回收期', value: r.payback_years, unit: '年', fmt: (v) => v.toFixed(1), source: s.tool_name });
    }
    if (s.tool_name === 'price_trend_analysis' && km.stats) {
      if (km.stats.avg_price != null) kpis.push({ label: '均价', value: km.stats.avg_price, unit: 'AUD/MWh', fmt: (v) => v.toFixed(1), source: s.tool_name });
      if (km.stats.negative_ratio_pct != null) kpis.push({ label: '负价比例', value: km.stats.negative_ratio_pct, unit: '%', fmt: (v) => v.toFixed(1), source: s.tool_name });
    }
    if (s.tool_name === 'bess_revenue_benchmark' && km.summary && km.summary.latest_index_k_aud_per_mw_year != null) {
      kpis.push({
        label: `基准收益${km.summary.latest_month ? ' ' + km.summary.latest_month : ''}`,
        value: km.summary.latest_index_k_aud_per_mw_year,
        unit: 'kAUD/MW/年',
        fmt: (v) => v.toFixed(1),
        source: s.tool_name,
      });
    }
    if (s.tool_name === 'market_screening' && Array.isArray(km.items) && km.items[0]) {
      const top = km.items[0];
      if (top.overall_score != null) kpis.push({ label: '最优区域评分', value: top.overall_score, unit: `(${top.label || ''})`, fmt: (v) => v.toFixed(1), source: s.tool_name });
    }
  }
  return kpis.slice(0, 4);
}

function KpiCard({ label, value, unit, fmt, source }) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5">
      <div className="truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]" title={label}>
        {label}
      </div>
      {/* 数值+单位允许换行，长内容不再溢出截断（2026-08-11） */}
      <div
        className="mt-1 flex flex-wrap items-baseline gap-x-1 text-lg font-semibold tabular-nums text-[var(--color-text)]"
        style={{ fontFamily: 'var(--font-mono-data)' }}
      >
        <span>{formatSigned(value, fmt)}</span>
        {unit && <span className="text-[10px] font-normal text-[var(--color-muted)]">{unit}</span>}
      </div>
      {/* 溯源徽章：诚实语义——该数值出现在来源工具的结果中（非因果验证承诺） */}
      <span
        className="mt-1.5 block max-w-full truncate rounded bg-[var(--color-surface-hover)] px-1.5 py-0.5 text-[9px] text-[var(--color-primary)]"
        title={`该数值出现在 ${source} 的工具结果中`}
      >
        来源: {source}
      </span>
    </div>
  );
}

// 部分成功信息已由轨迹 Tab 完整承载（2026-08-10 去重），PartialSuccessStrip 移除。

function ReportView({ report, answer, trace, onCompare, onSuggest }) {
  const status = STATUS_MAP[report.status] || STATUS_MAP.running;
  const kpis = extractKpis(report);
  const meta = report.metadata || {};
  const usage = meta.llm_usage;
  // PDF 导出（2026-08-11 改造）：预览弹窗 → 确认 → html2pdf 生成下载，
  // 不再直接 window.print 跳转浏览器打印页
  const [exportOpen, setExportOpen] = useState(false);

  return (
    <div className="space-y-5">
      {/* Status bar: icon+色双编码徽章 + 模式/成本 chip */}
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold"
          style={{ borderColor: status.color, color: status.color }}
        >
          <span>{status.icon}</span>
          {status.label}
        </span>
        {report.total_duration_ms > 0 && (
          <span className="font-mono text-[11px] tabular-nums text-[var(--color-muted)]">
            耗时 {(report.total_duration_ms / 1000).toFixed(1)}s
          </span>
        )}
        {report.workflow_type && (
          <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[10px] text-[var(--color-muted)]">
            {report.workflow_type}
          </span>
        )}
        {meta.tool_profile && (
          <span className="rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[10px] text-[var(--color-muted)]">
            工具集: {meta.tool_profile}{meta.tool_profile_source ? ` (${meta.tool_profile_source})` : ''}
          </span>
        )}
        {usage && usage.total_tokens > 0 && (
          <span className="font-mono rounded bg-[var(--color-surface-hover)] px-2 py-0.5 text-[10px] tabular-nums text-[var(--color-muted)]">
            {usage.total_tokens.toLocaleString('en-US')} tokens
          </span>
        )}
        <button
          onClick={() => setExportOpen(true)}
          className="ml-auto rounded border border-[var(--color-border)] px-2.5 py-1 text-[10px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)] print:hidden"
        >
          导出 PDF
        </button>
      </div>
      {exportOpen && (
        <ExportPreviewModal
          report={report}
          answer={answer}
          trace={trace}
          kpis={kpis}
          onClose={() => setExportOpen(false)}
        />
      )}

      {/* KPI 卡仅打印可见（屏幕上的唯一展示位在左栏结论区，去重；PDF 导出保持完整） */}
      {kpis.length > 0 && (
        <div className="hidden grid-cols-2 gap-2 print:grid">
          {kpis.map((k, i) => (
            <KpiCard key={i} {...k} />
          ))}
        </div>
      )}

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
          const inv = (r.stage_results || []).find((s) => s.tool_name === 'investment_analysis');
          const km = inv?.key_metrics?.results || {};
          return (
            <div key={i} className="rounded-lg border border-[var(--color-border)] p-3">
              <div className="mb-2 text-[11px] font-medium text-[var(--color-text)]">
                {r.region} · {p.power_mw || '?'}MW/{p.duration_hours || '?'}h · CAPEX {p.capex_per_kwh || '?'}
              </div>
              {/* 关键结论指标（2026-08-11 补全：对比的核心是这些数字） */}
              {(km.npv_aud != null || km.irr_pct != null || km.payback_years != null) && (
                <div className="mb-2 grid grid-cols-3 gap-2">
                  {km.npv_aud != null && (
                    <div>
                      <div className="text-[9px] uppercase tracking-wider text-[var(--color-muted)]">NPV</div>
                      <div
                        className="text-[12px] font-semibold tabular-nums"
                        style={{ fontFamily: 'var(--font-mono-data)', color: km.npv_aud >= 0 ? 'var(--color-positive)' : 'var(--color-negative)' }}
                      >
                        {formatSigned(km.npv_aud, (v) => Math.abs(v) >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v.toFixed(0))}
                      </div>
                    </div>
                  )}
                  {km.irr_pct != null && (
                    <div>
                      <div className="text-[9px] uppercase tracking-wider text-[var(--color-muted)]">IRR</div>
                      <div className="text-[12px] font-semibold tabular-nums text-[var(--color-text)]" style={{ fontFamily: 'var(--font-mono-data)' }}>
                        {km.irr_pct.toFixed(1)}%
                      </div>
                    </div>
                  )}
                  {km.payback_years != null && (
                    <div>
                      <div className="text-[9px] uppercase tracking-wider text-[var(--color-muted)]">回收期</div>
                      <div className="text-[12px] font-semibold tabular-nums text-[var(--color-text)]" style={{ fontFamily: 'var(--font-mono-data)' }}>
                        {km.payback_years.toFixed(1)}年
                      </div>
                    </div>
                  )}
                </div>
              )}
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
