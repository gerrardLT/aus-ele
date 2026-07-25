/**
 * AnalystChat — U6: AI 分析师对话面板
 *
 * 浮动面板（右下角 FAB），支持自然语言输入 → Agent 多步分析 → 结构化报告。
 * 调用已有 POST /api/v1/agent/run 端点。
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageCircle, X, Send, Bot, User, Loader2 } from 'lucide-react';
import { useFilters } from '../contexts/FilterContext';
import { getApiBase } from '../lib/apiBase';

const API_BASE = getApiBase();

const SUGGESTIONS = [
  { zh: '比较 SA1 和 QLD1 的投资潜力', en: 'Compare SA1 vs QLD1 investment' },
  { zh: 'SA1 100MW/4h 的 NPV 是多少？', en: 'What is NPV for SA1 100MW/4h?' },
  { zh: '蚕食风险如何？', en: 'What is the cannibalization risk?' },
  { zh: '运行完整投资可行性分析', en: 'Run full investment feasibility' },
];

export default function AnalystChat({ lang = 'zh' }) {
  const { filters } = useFilters();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  async function sendMessage(text) {
    const query = text || input;
    if (!query.trim() || loading) return;

    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setInput('');
    setLoading(true);
    // Add placeholder for streaming response
    setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }]);

    try {
      const res = await fetch(`${API_BASE}/api/v1/agent/chat-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          context: {
            market: filters.region === 'WEM' ? 'WEM' : 'NEM',
            region: filters.region || 'SA1',
            year: filters.year || 2025,
          },
          history: messages.filter(m => !m.streaming).map(m => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      // SSE streaming reader — typewriter effect
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let accumulated = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE frames
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === 'token') {
              accumulated += event.content || '';
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: accumulated, streaming: true };
                return updated;
              });
            } else if (event.type === 'report') {
              // Final structured report — replace accumulated text
              const reportText = event.report?.synthesis || event.report?.summary || accumulated;
              accumulated = reportText;
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: reportText, streaming: false };
                return updated;
              });
            } else if (event.type === 'tool_call') {
              // Show tool activity indicator
              const toolNote = `\n\n> 🔧 ${event.tool || 'tool'}...`;
              accumulated += toolNote;
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: accumulated, streaming: true };
                return updated;
              });
            } else if (event.type === 'error') {
              accumulated += `\n\n⚠️ ${event.message || 'Error'}`;
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: accumulated, streaming: false };
                return updated;
              });
            }
          } catch { /* skip malformed SSE frame */ }
        }
      }

      // Ensure streaming flag is cleared
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.streaming) updated[updated.length - 1] = { ...last, streaming: false };
        return updated;
      });
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: 'assistant',
          content: lang === 'zh' ? `请求失败: ${err.message}` : `Request failed: ${err.message}`,
          streaming: false,
        };
        return updated;
      });
    }
    setLoading(false);
  }

  return (
    <>
      {/* FAB Button */}
      {!open && (
        <motion.button
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex items-center justify-center w-14 h-14 rounded-full bg-[var(--color-primary)] text-white shadow-lg hover:shadow-xl transition-shadow"
          aria-label="Open AI Analyst"
        >
          <MessageCircle size={24} />
        </motion.button>
      )}

      {/* Chat Panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className="fixed bottom-6 right-6 z-50 flex flex-col w-[380px] h-[520px] rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] shadow-2xl overflow-hidden panel-glass"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
              <div className="flex items-center gap-2">
                <Bot size={18} className="text-[var(--color-primary)]" />
                <span className="text-sm font-bold text-[var(--color-text)]">
                  {lang === 'zh' ? 'AI 分析师' : 'AI Analyst'}
                </span>
              </div>
              <button onClick={() => setOpen(false)} className="text-[var(--color-muted)] hover:text-[var(--color-text)]">
                <X size={16} />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <div className="text-center py-8">
                  <p className="text-sm text-[var(--color-muted)] mb-4">
                    {lang === 'zh' ? '问我任何关于 BESS 投资分析的问题' : 'Ask me anything about BESS investment analysis'}
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {SUGGESTIONS.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => sendMessage(s[lang] || s.en)}
                        className="px-3 py-1.5 text-[11px] rounded-full border border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] transition-colors"
                      >
                        {s[lang] || s.en}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => (
                <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && <Bot size={16} className="text-[var(--color-primary)] mt-1 flex-shrink-0" />}
                  <div className={`max-w-[80%] rounded-xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap ${
                    msg.role === 'user'
                      ? 'bg-[var(--color-primary)] text-white'
                      : 'bg-[var(--color-surface)] text-[var(--color-text)] border border-[var(--color-border)]'
                  }`}>
                    {msg.content}
                    {msg.streaming && <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-[var(--color-primary)] animate-pulse align-middle" />}
                  </div>
                  {msg.role === 'user' && <User size={16} className="text-[var(--color-muted)] mt-1 flex-shrink-0" />}
                </div>
              ))}

              {loading && (
                <div className="flex gap-2 items-center text-[var(--color-muted)]">
                  <Loader2 size={14} className="animate-spin" />
                  <span className="text-xs">{lang === 'zh' ? '分析中...' : 'Analyzing...'}</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t border-[var(--color-border)]">
              <div className="flex items-center gap-2">
                <input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && sendMessage()}
                  placeholder={lang === 'zh' ? '输入问题...' : 'Ask a question...'}
                  className="flex-1 px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                />
                <button
                  onClick={() => sendMessage()}
                  disabled={loading || !input.trim()}
                  className="p-2 rounded-lg bg-[var(--color-primary)] text-white disabled:opacity-40 hover:opacity-90 transition-opacity"
                >
                  <Send size={14} />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
