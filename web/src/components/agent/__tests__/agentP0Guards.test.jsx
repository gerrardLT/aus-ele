/**
 * AgentPage P0 修复守门测试（2026-08-24）
 *
 * 对应 docs/design/Agent页面设计拆解与优化方案.md P0 清单：
 * 1. stripFailedTurn — 重试成对裁剪（防 user turn 在 history+query 双发）
 * 2. EvidencePanel — 报告到达不抢用户手动选中的 tab（未手动选过仍自动切）
 * 3. AgentPage — 清空对话后审计时间线仍可见且可撤销（页级唯一实例）
 * 4. AgentPage — Enter 发送 / Shift+Enter 换行；错误消息附重试且不双发历史
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { stripFailedTurn } from '../../../lib/agentChatSupport.js';

// agentApi 全量 mock：AgentPage 挂载即调用 listWorkflows/getAgentHistory
vi.mock('../../../lib/agentApi.js', () => ({
  streamAgentChat: vi.fn(),
  listWorkflows: vi.fn(() => Promise.resolve({ workflows: [] })),
  getAgentHistory: vi.fn(() => Promise.resolve({ executions: [] })),
  getExecutionDetail: vi.fn(() => Promise.resolve(null)),
  deleteExecution: vi.fn(() => Promise.resolve()),
  clearAllHistory: vi.fn(() => Promise.resolve()),
}));

import AgentPage, { EvidencePanel } from '../../../pages/AgentPage.jsx';
import { streamAgentChat } from '../../../lib/agentApi.js';

// 一次"成功"的 SSE 流：start → done
const okStream = vi.fn((params, { onEvent }) => {
  onEvent({ type: 'start', execution_id: 'e1' });
  onEvent({ type: 'done' });
  return Promise.resolve();
});

beforeEach(() => {
  vi.clearAllMocks();
  streamAgentChat.mockImplementation(okStream);
  localStorage.clear();
});

// ─── stripFailedTurn（重试裁剪纯逻辑） ───────────────────────────────────────

describe('stripFailedTurn', () => {
  it('成对移除失败 assistant 及其前一条 user（防 history+query 双发）', () => {
    const msgs = [
      { id: 'u1', role: 'user', content: '第一轮' },
      { id: 'a1', role: 'assistant', answer: 'ok' },
      { id: 'u2', role: 'user', content: '第二轮' },
      { id: 'a2', role: 'assistant', error: 'boom' },
    ];
    const out = stripFailedTurn(msgs, 'a2');
    expect(out.map((m) => m.id)).toEqual(['u1', 'a1']);
  });

  it('前一条不是 user 时只移除失败 assistant', () => {
    const msgs = [{ id: 'a1', role: 'assistant', error: 'boom' }];
    expect(stripFailedTurn(msgs, 'a1').map((m) => m.id)).toEqual([]);
  });

  it('不改变原数组（不可变）', () => {
    const msgs = [
      { id: 'u1', role: 'user', content: 'x' },
      { id: 'a1', role: 'assistant', error: 'boom' },
    ];
    const out = stripFailedTurn(msgs, 'a1');
    expect(msgs).toHaveLength(2);
    expect(out).not.toBe(msgs);
  });

  it('找不到失败消息时原样返回', () => {
    const msgs = [{ id: 'u1', role: 'user', content: 'x' }];
    expect(stripFailedTurn(msgs, 'nope')).toBe(msgs);
  });
});

// ─── EvidencePanel：报告不抢 tab ─────────────────────────────────────────────

const traceMsg = {
  trace: [{ callId: 'c1', name: 'investment_analysis', status: 'success' }],
  report: null,
};
const doneReport = { status: 'completed', executive_summary: '结论摘要文本' };

describe('EvidencePanel 报告到达不抢 tab', () => {
  it('用户手动选过 tab 后，报告到达保持用户 tab 并显示 ● 就绪指示', () => {
    const { rerender } = render(<EvidencePanel message={traceMsg} />);
    fireEvent.click(screen.getByText('轨迹')); // 手动选择 → userTouched

    rerender(<EvidencePanel message={{ ...traceMsg, report: doneReport }} />);

    // 仍在轨迹 tab：工具名可见，报告内容不可见
    expect(screen.getByText('investment_analysis')).toBeTruthy();
    expect(screen.queryByText('结论摘要文本')).toBeNull();
    // 报告 tab 上有就绪指示（渲染在 disabled→enabled 的 tab 上）
    expect(screen.getByText('●')).toBeTruthy();
  });

  it('用户未手动选过 tab 时，报告到达仍自动切到报告（保持原行为）', () => {
    const { rerender } = render(<EvidencePanel message={traceMsg} />);
    rerender(<EvidencePanel message={{ ...traceMsg, report: doneReport }} />);
    expect(screen.getByText('结论摘要文本')).toBeTruthy();
  });
});

// ─── AgentPage：Enter 发送 + 清空对话后审计可撤销 + 重试不双发 ──────────────

const typeAndSend = (text) => {
  const box = screen.getByPlaceholderText(/投资可行性分析/);
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: 'Enter' });
};

describe('AgentPage P0 行为', () => {
  it('Enter 直接发送；Shift+Enter 不发送', async () => {
    render(<AgentPage />);
    const box = screen.getByPlaceholderText(/投资可行性分析/);

    fireEvent.change(box, { target: { value: '换行测试' } });
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true });
    expect(streamAgentChat).not.toHaveBeenCalled();

    typeAndSend('测试问题');
    await waitFor(() => expect(streamAgentChat).toHaveBeenCalledTimes(1));
    expect(screen.getByText('测试问题')).toBeTruthy();
  });

  it('清空对话后审计时间线仍可见，撤销可恢复消息', async () => {
    render(<AgentPage />);
    typeAndSend('测试问题');
    await waitFor(() => expect(screen.getByText('测试问题')).toBeTruthy());

    fireEvent.click(screen.getByText('新对话'));
    // 对话已空 → 空态文案出现；但页级审计仍在（原缺陷：随消息一起消失）
    expect(screen.getByText(/输入分析请求或选择快捷工作流/)).toBeTruthy();
    expect(screen.getByText('清空对话')).toBeTruthy();
    expect(screen.getByText('撤销')).toBeTruthy();

    fireEvent.click(screen.getByText('撤销'));
    await waitFor(() => expect(screen.getByText('测试问题')).toBeTruthy());
  });

  it('失败消息显示重试；重试成对移除失败轮次，不双发 user turn', async () => {
    // 首次流失败，第二次成功
    streamAgentChat
      .mockImplementationOnce((params, { onEvent }) => {
        onEvent({ type: 'start', execution_id: 'e1' });
        return Promise.reject(new Error('connection reset'));
      })
      .mockImplementationOnce(okStream);

    render(<AgentPage />);
    typeAndSend('测试问题');

    await waitFor(() => expect(screen.getByRole('button', { name: /重试/ })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));

    await waitFor(() => expect(streamAgentChat).toHaveBeenCalledTimes(2));
    // 第二次请求：history 为空（失败对已裁剪），query 为原问题 → 无双发
    const secondParams = streamAgentChat.mock.calls[1][0];
    expect(secondParams.query).toBe('测试问题');
    expect(secondParams.history).toEqual([]);
    // 页面上只有一条「测试问题」用户消息（成对移除后重发）
    expect(screen.getAllByText('测试问题')).toHaveLength(1);
  });
});
