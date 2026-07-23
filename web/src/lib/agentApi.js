// web/src/lib/agentApi.js
// AI Agent API client for workflow orchestration

import { getApiBase } from './apiBase.js';

const API_BASE = getApiBase();
const AGENT_BASE = `${API_BASE}/v1/agent`;

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
    headers: { 'Content-Type': 'application/json' },
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
    headers: { 'Content-Type': 'application/json' },
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
  const response = await fetch(`${AGENT_BASE}/history?limit=${limit}`);
  if (!response.ok) throw new Error(`Failed to get history: ${response.status}`);
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
