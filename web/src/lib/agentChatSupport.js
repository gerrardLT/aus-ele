/**
 * agentChatSupport — AgentPage 对话纯逻辑（可单测，无 React 依赖）
 *
 * 从 pages/AgentPage.jsx 抽出（P0 2026-08-24）：
 * 页面文件只导出组件（react-refresh 守门），纯函数放 lib 供 vitest 直接引用。
 */

// 重试裁剪：成对移除失败 assistant 及其前一条 user。
// historyPayload 从 messages 全量重建，只删 assistant 会让该 user turn
// 在 history 尾部 + query 中双发污染多轮上下文；部分流式回答随失败消息丢弃。
export function stripFailedTurn(messages, failedAssistantId) {
  const idx = messages.findIndex((m) => m.id === failedAssistantId);
  if (idx < 0) return messages;
  const out = messages.slice();
  out.splice(idx, 1);
  if (idx > 0 && out[idx - 1] && out[idx - 1].role === 'user') out.splice(idx - 1, 1);
  return out;
}
