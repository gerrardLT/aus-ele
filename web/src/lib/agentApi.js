// web/src/lib/agentApi.js
// AI Agent API client for workflow orchestration

import { getApiBase } from './apiBase.js';

const API_BASE = getApiBase();
const AGENT_BASE = `${API_BASE}/v1/agent`;

// ─── Web 会话引导（后端 P0 加固后 agent 端点要求 JWT Bearer） ────────────────
// 前端启动后向 /auth/web-session 引导一个短期令牌并缓存。
// 后端门控（2026-08-09）：同站点 Origin/Referer 自动放行（dev 代理/生产
// 直连均满足）；VITE_BOOTSTRAP_SECRET 仅在配置时作为显式共享密钥附加，
// 用于无 Origin 的调用方，未配置不影响 web UI 取令牌。
let _token = null;
let _tokenExp = 0;

async function ensureAuthToken() {
  const now = Math.floor(Date.now() / 1000);
  if (_token && _tokenExp > now + 30) return _token;
  try {
    const headers = { 'Content-Type': 'application/json' };
    const bootstrapSecret = import.meta.env.VITE_BOOTSTRAP_SECRET;
    if (bootstrapSecret) headers['X-Bootstrap-Secret'] = bootstrapSecret;
    const res = await fetch(`${API_BASE}/v1/auth/web-session`, {
      method: 'POST',
      headers,
    });
    if (!res.ok) return null;
    const d = await res.json();
    _token = d.token || null;
    _tokenExp = now + (d.expires_in || 3600);
    return _token;
  } catch {
    return null;
  }
}

async function authHeaders(extra = {}) {
  const t = await ensureAuthToken();
  return t ? { ...extra, Authorization: `Bearer ${t}` } : extra;
}

/**
 * Run an agent workflow synchronously.
 * @param {Object} params
 * @param {string} params.query - Natural language request
 * @param {string} [params.market='NEM'] - Market type (NEM|WEM)
 * @param {string} [params.region] - Region code
 * @param {number} [params.year] - Analysis year
 * @param {string} [params.workflow_template] - Force a specific template
 * @param {Object} [params.params_override] - Override default params
 * @param {number} [params.max_steps=15] - Max execution steps
 * @returns {Promise<Object>} AgentRunResponse
 */
export async function runAgent(params) {
  const response = await fetch(`${AGENT_BASE}/run`, {
    method: 'POST',
    headers: await authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Agent run failed: ${response.status}`);
  }
  return response.json();
}

/**
 * Submit an agent workflow for async execution.
 * @param {Object} params - Same as runAgent
 * @returns {Promise<{task_id: string, status: string}>}
 */
export async function runAgentAsync(params) {
  const response = await fetch(`${AGENT_BASE}/run-async`, {
    method: 'POST',
    headers: await authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Agent async run failed: ${response.status}`);
  }
  return response.json();
}

/**
 * Poll async task status.
 * @param {string} taskId
 * @returns {Promise<{task_id: string, status: string, report?: Object, progress?: string}>}
 */
export async function getTaskStatus(taskId, signal) {
  const response = await fetch(`${AGENT_BASE}/task/${taskId}`, { signal });
  if (!response.ok) {
    throw new Error(`Task query failed: ${response.status}`);
  }
  return response.json();
}

/**
 * List available agent tools.
 * @returns {Promise<{tools: Array, total: number}>}
 */
export async function listAgentTools() {
  const response = await fetch(`${AGENT_BASE}/tools`);
  if (!response.ok) throw new Error(`Failed to list tools: ${response.status}`);
  return response.json();
}

/**
 * List available workflow templates.
 * @returns {Promise<{workflows: Array, total: number}>}
 */
export async function listWorkflows() {
  const response = await fetch(`${AGENT_BASE}/workflows`);
  if (!response.ok) throw new Error(`Failed to list workflows: ${response.status}`);
  return response.json();
}

/**
 * Get execution history.
 * @param {number} [limit=20]
 * @returns {Promise<{executions: Array, total: number}>}
 */
export async function getAgentHistory(limit = 20) {
  const response = await fetch(`${AGENT_BASE}/history?limit=${limit}`, {
    headers: await authHeaders(),
  });
  if (!response.ok) throw new Error(`Failed to get history: ${response.status}`);
  return response.json();
}

/**
 * Get full execution detail by ID (includes parsed report).
 * @param {string} executionId
 * @returns {Promise<Object>} Execution record with report field
 */
export async function getExecutionDetail(executionId) {
  const response = await fetch(`${AGENT_BASE}/history/${executionId}`);
  if (!response.ok) throw new Error(`Failed to get execution: ${response.status}`);
  return response.json();
}

/**
 * Delete an execution record by ID.
 * @param {string} executionId
 * @returns {Promise<{deleted: boolean}>}
 */
export async function deleteExecution(executionId) {
  const response = await fetch(`${AGENT_BASE}/history/${executionId}`, {
    method: 'DELETE',
    headers: await authHeaders(),
  });
  if (!response.ok) throw new Error(`Failed to delete execution: ${response.status}`);
  return response.json();
}

/**
 * Clear ALL execution records (2026-08-11). UI 侧需二次确认。
 * @returns {Promise<{deleted: boolean, count: number}>}
 */
export async function clearAllHistory() {
  const response = await fetch(`${AGENT_BASE}/history`, {
    method: 'DELETE',
    headers: await authHeaders(),
  });
  if (!response.ok) throw new Error(`Failed to clear history: ${response.status}`);
  return response.json();
}

/**
 * Poll an async task until completion.
 * @param {string} taskId
 * @param {Object} [options]
 * @param {number} [options.intervalMs=2000] - Poll interval
 * @param {number} [options.timeoutMs=300000] - Max wait time
 * @param {Function} [options.onProgress] - Progress callback
 * @param {AbortSignal} [options.signal] - Abort signal to cancel polling (e.g. on unmount)
 * @returns {Promise<Object>} Final report
 */
export async function pollTaskUntilDone(taskId, options = {}) {
  const { intervalMs = 2000, timeoutMs = 300000, onProgress, signal } = options;
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    if (signal?.aborted) {
      throw new DOMException('Polling aborted', 'AbortError');
    }
    const status = await getTaskStatus(taskId, signal);
    if (onProgress && status.progress) {
      onProgress(status.progress);
    }
    if (status.status === 'completed' || status.status === 'partial' || status.status === 'failed') {
      return status;
    }
    await new Promise((resolve, reject) => {
      const timer = setTimeout(resolve, intervalMs);
      if (signal) {
        signal.addEventListener(
          'abort',
          () => {
            clearTimeout(timer);
            reject(new DOMException('Polling aborted', 'AbortError'));
          },
          { once: true },
        );
      }
    });
  }
  throw new Error('Agent task timed out');
}

/**
 * Stream a multi-turn agent chat via SSE (真·流式).
 *
 * Consumes the backend `POST /chat-stream` endpoint, parsing `data: {json}\n\n`
 * frames and invoking `onEvent` for each parsed event. Event `type` values:
 * start | status | token | tool_call | tool_result | answer_end | report | error | done
 *
 * @param {Object} params
 * @param {string} params.query - Current user turn
 * @param {Array<{role:string, content:string}>} [params.history] - Prior turns
 * @param {string} [params.market='NEM']
 * @param {string} [params.region]
 * @param {number} [params.year]
 * @param {string} [params.workflow_template]
 * @param {Object} [params.params_override]
 * @param {number} [params.max_steps]
 * @param {Object} options
 * @param {(event:Object)=>void} options.onEvent - Called for each SSE event
 * @param {AbortSignal} [options.signal] - Abort to cancel the stream (e.g. unmount)
 */
export async function streamAgentChat(params, { onEvent, signal } = {}) {
  const response = await fetch(`${AGENT_BASE}/chat-stream`, {
    method: 'POST',
    headers: await authHeaders({
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    }),
    body: JSON.stringify(params),
    signal,
  });

  if (!response.ok || !response.body) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Agent chat stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      let sepIndex;
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawFrame = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);

        // A frame may contain multiple `data:` lines; concatenate their payloads.
        const dataLines = rawFrame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).replace(/^ /, ''));
        if (dataLines.length === 0) continue;
        const payload = dataLines.join('\n');
        try {
          const event = JSON.parse(payload);
          onEvent?.(event);
        } catch {
          // Ignore malformed frames (e.g. keep-alive comments).
        }
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* noop */
    }
  }
}
