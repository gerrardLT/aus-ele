// web/src/pages/PricingPage.jsx
// 定价页 + 营销落地页（P1-4，2026-08-14）：三套餐 + 功能对比 + 邀请制 CTA。
// 支付后置：无在线支付入口，CTA 指向邀请制说明。
// 配额数值与后端 external_api_v1.py 的 PLAN_DAILY_UNIT_LIMITS / AGENT_RUN_DAILY_LIMITS 对齐。

import { useEffect } from 'react';

const PLANS = [
  {
    id: 'starter',
    zh: { name: 'Starter', tagline: '免费体验，了解市场全貌', cta: '申请邀请' },
    en: { name: 'Starter', tagline: 'Free trial to explore the full market picture', cta: 'Request invite' },
    agentRuns: 50,
    apiUnits: 1000,
    features: {
      zh: ['NEM/WEM 全部分析模块', 'AI 编排分析（50 次/天）', 'API 访问（1,000 units/天）', '成员邀请与协作'],
      en: ['All NEM/WEM analysis modules', 'AI orchestrated analysis (50 runs/day)', 'API access (1,000 units/day)', 'Member invites & collaboration'],
    },
    highlight: false,
  },
  {
    id: 'growth',
    zh: { name: 'Growth', tagline: '团队级分析，更高配额', cta: '联系我们' },
    en: { name: 'Growth', tagline: 'Team-grade analysis with higher quotas', cta: 'Contact us' },
    agentRuns: 200,
    apiUnits: 10000,
    features: {
      zh: ['Starter 全部功能', 'AI 编排分析（200 次/天）', 'API 访问（10,000 units/天）', '优先支持'],
      en: ['Everything in Starter', 'AI orchestrated analysis (200 runs/day)', 'API access (10,000 units/day)', 'Priority support'],
    },
    highlight: true,
  },
  {
    id: 'pro',
    zh: { name: 'Pro', tagline: '专业机构，全量能力', cta: '联系我们' },
    en: { name: 'Pro', tagline: 'Full capabilities for professional teams', cta: 'Contact us' },
    agentRuns: 1000,
    apiUnits: 50000,
    features: {
      zh: ['Growth 全部功能', 'AI 编排分析（1,000 次/天）', 'API 访问（50,000 units/天）', '专属支持与方法论白皮书'],
      en: ['Everything in Growth', 'AI orchestrated analysis (1,000 runs/day)', 'API access (50,000 units/day)', 'Dedicated support & methodology whitepaper'],
    },
    highlight: false,
  },
];

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

export default function PricingPage() {
  const lang = readLang();
  const zh = lang === 'zh';

  // P2-3 Onboarding 信号：查看定价页（2026-08-14）
  useEffect(() => {
    import('../lib/onboarding.js').then((m) => m.markOnboardingStep('pricing')).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <a href="/" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)] hover:text-[var(--color-text)]">
            ← AEMO Intelligence
          </a>
          <a href="/login" className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
            {zh ? '登录' : 'Sign in'}
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-12">
        <div className="mb-10 text-center">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">AEMO Intelligence</div>
          <h1 className="mt-2 font-serif text-3xl text-[var(--color-text)]">
            {zh ? '澳洲 NEM/WEM 储能市场进入与收益判断工作台' : 'Australia NEM/WEM storage market-entry & revenue workbench'}
          </h1>
          <p className="mx-auto mt-3 max-w-2xl text-sm text-[var(--color-muted)]">
            {zh
              ? '市场真相层 → 前瞻机会判断 → 市场进入结论。全部数值可溯源到 AEMO 官方数据，每个结论带规则与数据边界说明。'
              : 'Market truth → forward opportunity → market-entry conclusion. Every number is traceable to official AEMO data, with rule and data-boundary annotations.'}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {PLANS.map((plan) => {
            const t = zh ? plan.zh : plan.en;
            return (
              <section
                key={plan.id}
                className={`rounded-2xl border p-6 ${plan.highlight ? 'border-[var(--color-primary)] bg-[var(--color-surface)]' : 'border-[var(--color-border)] bg-[var(--color-surface)]'}`}
              >
                <div className="flex items-center justify-between">
                  <h2 className="font-serif text-xl text-[var(--color-text)]">{t.name}</h2>
                  {plan.highlight && (
                    <span className="rounded-full bg-[var(--color-primary)]/15 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-primary)]">
                      {zh ? '推荐' : 'Popular'}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-[var(--color-muted)]">{t.tagline}</p>
                <ul className="mt-4 space-y-2">
                  {t.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-xs text-[var(--color-text)]">
                      <span className="mt-0.5 text-[var(--color-status-success)]">✓</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <a
                  href="/login"
                  className={`mt-6 block rounded-lg px-4 py-2.5 text-center text-sm font-semibold transition-opacity hover:opacity-90 ${
                    plan.highlight ? 'bg-[var(--color-primary)] text-white' : 'border border-[var(--color-border)] text-[var(--color-text)]'
                  }`}
                >
                  {t.cta}
                </a>
              </section>
            );
          })}
        </div>

        <div className="mt-12 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h2 className="mb-4 text-sm font-semibold text-[var(--color-text)]">
            {zh ? '功能对比' : 'Feature comparison'}
          </h2>
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
                <th className="px-2 py-2 font-semibold">{zh ? '能力' : 'Capability'}</th>
                <th className="px-2 py-2 font-semibold">Starter</th>
                <th className="px-2 py-2 font-semibold">Growth</th>
                <th className="px-2 py-2 font-semibold">Pro</th>
              </tr>
            </thead>
            <tbody className="text-[var(--color-text)]">
              {(zh
                ? [
                    ['NEM/WEM 全部分析模块', '✓', '✓', '✓'],
                    ['AI 编排分析（次/天）', '50', '200', '1,000'],
                    ['API 访问（units/天）', '1,000', '10,000', '50,000'],
                    ['收益基准对照（benchmark）', '✓', '✓', '✓'],
                    ['成员协作', '✓', '✓', '✓'],
                    ['优先支持', '—', '✓', '✓'],
                    ['方法论白皮书', '—', '—', '✓'],
                  ]
                : [
                    ['All NEM/WEM analysis modules', '✓', '✓', '✓'],
                    ['AI orchestrated analysis (runs/day)', '50', '200', '1,000'],
                    ['API access (units/day)', '1,000', '10,000', '50,000'],
                    ['Revenue benchmark comparison', '✓', '✓', '✓'],
                    ['Member collaboration', '✓', '✓', '✓'],
                    ['Priority support', '—', '✓', '✓'],
                    ['Methodology whitepaper', '—', '—', '✓'],
                  ]
              ).map((row) => (
                <tr key={row[0]} className="border-b border-[var(--color-border)]">
                  {row.map((cell, i) => (
                    <td key={i} className="px-2 py-2">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[10px] text-[var(--color-muted)]">
            {zh
              ? '配额数值与后端 PLAN_DAILY_UNIT_LIMITS / AGENT_RUN_DAILY_LIMITS 对齐；支付功能即将上线，当前为邀请制内测。'
              : 'Quota values align with backend PLAN_DAILY_UNIT_LIMITS / AGENT_RUN_DAILY_LIMITS; payments coming soon, currently invite-only beta.'}
          </p>
        </div>

        <div className="mt-8 text-center text-xs text-[var(--color-muted)]">
          <a href="/legal/disclaimer" className="hover:text-[var(--color-text)]">
            {zh ? '免责声明' : 'Disclaimer'}
          </a>
          <span className="mx-2">·</span>
          <a href="/legal/terms" className="hover:text-[var(--color-text)]">
            {zh ? '服务条款' : 'Terms'}
          </a>
          <span className="mx-2">·</span>
          <a href="/legal/privacy" className="hover:text-[var(--color-text)]">
            {zh ? '隐私政策' : 'Privacy'}
          </a>
        </div>
      </main>
    </div>
  );
}
