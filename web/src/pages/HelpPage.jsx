// web/src/pages/HelpPage.jsx
// 帮助与反馈（P2-4，2026-08-14）：FAQ 手风琴 + 反馈表单。路由 /help，公开访问。

import { useState } from 'react';
import { getValidAccessToken, tryRefreshToken } from '../lib/authStore.js';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

const FAQS = {
  zh: [
    ['数据来自哪里？', '市场数据来自 AEMO（Australian Energy Market Operator）等官方公开渠道，定时同步入库。每个输出都标注数据等级（official/derived）与覆盖边界。'],
    ['什么是 derived（派生）口径？', '部分指标由官方公开数据加工而来（如筛选评分、稀缺度），与官方统计可能存在差异。请以输出上的数据等级标注为准。'],
    ['AI 编排分析能问什么？', '市场对比、价格异动归因、储能收益测算、政策影响等基于本系统数据的问题。AI 只使用系统内数据回答，每个结论附规则与数据边界说明。'],
    ['配额是什么？', '每个套餐含 Agent 运行与 API 调用日配额（Starter 50 次/天、Growth 200、Pro 1,000）。当前为软配额：超额只标记不阻断。详见定价页。'],
    ['benchmark 收益为什么和实际不一样？', '收益基准为理想算子口径（完美择时），系统性高于实际资产收益，用于横向对比而非绝对预期。'],
    ['如何邀请同事？', '管理员在账户中心「成员管理」创建邀请，复制邀请链接发送给对方，对方设密码即注册。'],
  ],
  en: [
    ['Where does the data come from?', 'Market data comes from official public sources such as AEMO, synced on schedule. Every output carries a data grade (official/derived) and coverage boundary.'],
    ['What does "derived" mean?', 'Some metrics are computed from official public data (e.g., screening scores, scarcity indices) and may differ from official statistics. Defer to the data-grade annotations.'],
    ['What can I ask the AI analyst?', 'Market comparisons, price-spike attribution, storage revenue estimates, policy impact — all grounded in this system\'s data, with rule and data-boundary annotations.'],
    ['What are quotas?', 'Each plan includes daily Agent-run and API quotas (Starter 50/day, Growth 200, Pro 1,000). Quotas are currently soft: flagged, not blocked. See Pricing.'],
    ['Why do benchmarks differ from actual revenue?', 'Benchmarks use an ideal-operator caliber (perfect timing) and are systematically higher than actual asset revenue — for relative comparison, not absolute expectation.'],
    ['How do I invite colleagues?', 'An admin creates an invite under Account > Members; share the invite link — the invitee sets a password and is registered.'],
  ],
};

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

export default function HelpPage() {
  const lang = readLang();
  const zh = lang === 'zh';
  const faqs = zh ? FAQS.zh : FAQS.en;
  const [openIdx, setOpenIdx] = useState(0);
  const [message, setMessage] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!message.trim()) return;
    setBusy(true); setResult('');
    try {
      const token = (await getValidAccessToken()) || (await tryRefreshToken());
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(`${API_BASE}/v1/feedback`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ email: email || undefined, message: message.trim() }),
      });
      if (res.ok) {
        setResult(zh ? '已收到你的反馈，谢谢！' : 'Feedback received, thank you!');
        setMessage('');
      } else if (res.status === 401) {
        setResult(zh ? '反馈需要登录，请先登录。' : 'Please sign in to submit feedback.');
      } else {
        setResult(zh ? '提交失败，请稍后重试。' : 'Submit failed, please retry.');
      }
    } catch {
      setResult(zh ? '网络错误，请稍后重试' : 'Network error, please retry');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <a href="/" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)] hover:text-[var(--color-text)]">
            ← AEMO Intelligence
          </a>
          <h1 className="text-sm font-semibold text-[var(--color-text)]">{zh ? '帮助中心' : 'Help center'}</h1>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-10">
        <div className="space-y-2">
          {faqs.map(([q, a], i) => (
            <section key={q} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <button
                type="button"
                onClick={() => setOpenIdx(openIdx === i ? -1 : i)}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-[var(--color-text)]"
              >
                <span>{q}</span>
                <span className="text-[var(--color-muted)]">{openIdx === i ? '−' : '+'}</span>
              </button>
              {openIdx === i && (
                <p className="border-t border-[var(--color-border)] px-4 py-3 text-xs leading-relaxed text-[var(--color-muted)]">{a}</p>
              )}
            </section>
          ))}
        </div>

        <form onSubmit={submit} className="mt-8 space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-sm font-semibold text-[var(--color-text)]">{zh ? '意见反馈' : 'Feedback'}</h2>
          <input
            placeholder={zh ? '邮箱（可选）' : 'Email (optional)'}
            value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-text)]"
          />
          <textarea
            required rows={4}
            placeholder={zh ? '告诉我们你的问题或建议…' : 'Tell us your issue or suggestion…'}
            value={message} onChange={(e) => setMessage(e.target.value)}
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-text)]"
          />
          <div className="flex items-center gap-3">
            <button type="submit" disabled={busy}
              className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
              {busy ? (zh ? '提交中…' : 'Sending…') : (zh ? '提交反馈' : 'Submit')}
            </button>
            {result && <span className="text-xs text-[var(--color-muted)]">{result}</span>}
          </div>
        </form>
      </main>
    </div>
  );
}
