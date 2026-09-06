// web/src/pages/PricingPage.jsx
// 定价页 + 营销落地页（P1-4，2026-08-14；R2.5 CTA 修复，2026-09-06）：三套餐 + 功能对比。
// 支付后置：无在线支付入口，但 CTA 不再指向 /login（理由见 resolveCta）。
// 配额数值与后端 external_api_v1.py 的 PLAN_DAILY_UNIT_LIMITS / AGENT_RUN_DAILY_LIMITS 对齐。

import { brandEyebrow, contactHref } from '../lib/brand.js';
import { useEffect } from 'react';

// R2.5：ctaKind 决定出口 —— signup 走自助注册（R1.1 已上线），contact 走「找到人」。
const PLANS = [
  {
    id: 'starter',
    ctaKind: 'signup',
    zh: { name: 'Starter', tagline: '免费体验，了解市场全貌' },
    en: { name: 'Starter', tagline: 'Free trial to explore the full market picture' },
    agentRuns: 50,
    apiUnits: 1000,
    features: {
      zh: ['NEM/WEM 全部分析模块', 'AI 决策引擎（50 次/天）', 'API 访问（1,000 units/天）', '成员邀请与协作'],
      en: ['All NEM/WEM analysis modules', 'AI Decision Engine (50 runs/day)', 'API access (1,000 units/day)', 'Member invites & collaboration'],
    },
    highlight: false,
  },
  {
    id: 'growth',
    ctaKind: 'contact',
    zh: { name: 'Growth', tagline: '团队级分析，更高配额' },
    en: { name: 'Growth', tagline: 'Team-grade analysis with higher quotas' },
    agentRuns: 200,
    apiUnits: 10000,
    features: {
      zh: ['Starter 全部功能', 'AI 决策引擎（200 次/天）', 'API 访问（10,000 units/天）', '优先支持'],
      en: ['Everything in Starter', 'AI Decision Engine (200 runs/day)', 'API access (10,000 units/day)', 'Priority support'],
    },
    highlight: true,
  },
  {
    id: 'pro',
    ctaKind: 'contact',
    zh: { name: 'Pro', tagline: '专业机构，全量能力' },
    en: { name: 'Pro', tagline: 'Full capabilities for professional teams' },
    agentRuns: 1000,
    apiUnits: 50000,
    features: {
      zh: ['Growth 全部功能', 'AI 决策引擎（1,000 次/天）', 'API 访问（50,000 units/天）', '专属支持与方法论白皮书'],
      en: ['Everything in Growth', 'AI Decision Engine (1,000 runs/day)', 'API access (50,000 units/day)', 'Dedicated support & methodology whitepaper'],
    },
    highlight: false,
  },
];

// 页脚法务链接清单（R2.4 新增的三份文件也要能从转化页到达）。
const LEGAL_LINKS = [
  ['/legal/disclaimer', '免责声明', 'Disclaimer'],
  ['/legal/terms', '服务条款', 'Terms'],
  ['/legal/privacy', '隐私政策', 'Privacy'],
  ['/legal/dpa', '数据处理附录', 'DPA'],
  ['/legal/aup', '可接受使用', 'AUP'],
  ['/legal/cookies', 'Cookie 与本地存储', 'Cookies'],
];

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

/**
 * R2.5 CTA 断链修复。
 *
 * 三张卡片的 CTA 原本全部指向 `/login`：一个已经在看套餐的人被送到登录页，登录失败又回到
 * 套餐页 —— 环里没有任何出口。而免费档的按钮当时用的是一句旧措辞（要用户去走人工申请），
 * 自助注册（R1.1）上线后它成了一句假话：点它既注册不了也申请不到东西。
 *
 * 现在的出口规则：免费档 → /register（真能开通）；付费档 → 没有在线支付，唯一诚实的出口是
 * 「找到人」，配置了支持邮箱走 mailto，否则走站内反馈页 —— 两条都指向真实存在的承接方。
 */
function resolveCta(plan, zh, env) {
  if (plan.ctaKind === 'signup') {
    return { href: '/register', label: zh ? '免费注册' : 'Create free account' };
  }
  return { href: contactHref(env, '/help'), label: zh ? '联系我们' : 'Contact us' };
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
            ← {brandEyebrow(zh)}
          </a>
          <a href="/login" className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
            {zh ? '登录' : 'Sign in'}
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-12">
        <div className="mb-10 text-center">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{brandEyebrow(zh)}</div>
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
            // P0 修复（2026-08-24 WQS 审计）：features 定义在 plan 顶层（plan.features.zh/en），
            // 原代码误用 t.features 导致任何语言下白屏崩溃。
            const features = plan.features[zh ? 'zh' : 'en'] || [];
            const cta = resolveCta(plan, zh, import.meta.env);
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
                  {features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-xs text-[var(--color-text)]">
                      <span className="mt-0.5 text-[var(--color-status-success)]">✓</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <a
                  href={cta.href}
                  className={`mt-6 block rounded-lg px-4 py-2.5 text-center text-sm font-semibold transition-opacity hover:opacity-90 ${
                    plan.highlight ? 'bg-[var(--color-primary)] text-white' : 'border border-[var(--color-border)] text-[var(--color-text)]'
                  }`}
                >
                  {cta.label}
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
                    ['AI 决策引擎（次/天）', '50', '200', '1,000'],
                    ['API 访问（units/天）', '1,000', '10,000', '50,000'],
                    ['收益基准对照（benchmark）', '✓', '✓', '✓'],
                    ['成员协作', '✓', '✓', '✓'],
                    ['优先支持', '—', '✓', '✓'],
                    ['方法论白皮书', '—', '—', '✓'],
                  ]
                : [
                    ['All NEM/WEM analysis modules', '✓', '✓', '✓'],
                    ['AI Decision Engine (runs/day)', '50', '200', '1,000'],
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
              ? '配额数值与后端 PLAN_DAILY_UNIT_LIMITS / AGENT_RUN_DAILY_LIMITS 对齐；支付功能尚未上线，公测期为免费自助注册，超额当前为标记不阻断。自动化调用与数据再分发的约束见'
              : 'Quota values align with backend PLAN_DAILY_UNIT_LIMITS / AGENT_RUN_DAILY_LIMITS. Payments are not live: the public beta is free and self-registered, and over-quota usage is currently flagged rather than blocked. Automated-call and redistribution limits follow the '}
            <a href="/legal/aup" className="underline hover:text-[var(--color-text)]">
              {zh ? '可接受使用政策' : 'Acceptable Use Policy'}
            </a>
            {zh ? '。' : '.'}
          </p>
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-[var(--color-muted)]">
          {LEGAL_LINKS.map(([href, zhLabel, enLabel]) => (
            <a key={href} href={href} className="hover:text-[var(--color-text)]">
              {zh ? zhLabel : enLabel}
            </a>
          ))}
        </div>
      </main>
    </div>
  );
}
