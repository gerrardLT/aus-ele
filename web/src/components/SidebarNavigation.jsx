import { motion, useReducedMotion } from 'framer-motion';
import { readAuth } from '../lib/authStore.js';

/**
 * SidebarNavigation — 侧边栏导航（2026-08-13 重排）
 *
 * 页面级导航，四组：市场 / 智能分析 / 其他市场 / 系统。
 * 阶段切换由页面顶部 Tab 负责（不再在侧边栏重复展示）；
 * Finland 合并为单入口（/finland），页内导航至 Fingrid 原始数据。
 */
export default function SidebarNavigation({
  activePage,
  lang = 'zh',
}) {
  const prefersReducedMotion = useReducedMotion();

  const markets = [
    { id: 'aemo', label: 'NEM', sub: lang === 'zh' ? '国家电力市场' : 'National Electricity Market', path: '/' },
    { id: 'wem', label: 'WEM', sub: lang === 'zh' ? '西澳电力市场' : 'Wholesale Electricity Market', path: '/wem' },
  ];

  // 四组结构：市场 / 智能分析 / 其他市场 / 系统（2026-08-13 用户确认）
  const groups = [
    {
      title: lang === 'zh' ? '智能分析' : 'INTELLIGENCE',
      links: [{ id: 'agent', label: lang === 'zh' ? '天枢 · AI 决策引擎' : 'Tianshu · Decision Engine', path: '/agent' }],
    },
    {
      title: lang === 'zh' ? '其他市场' : 'OTHER MARKETS',
      links: [{ id: 'finland', label: lang === 'zh' ? 'Finland 市场' : 'Finland', path: '/finland' }],
    },
    {
      title: lang === 'zh' ? '系统' : 'SYSTEM',
      links: [
        { id: 'account', label: lang === 'zh' ? '账户中心' : 'Account', path: '/account' },
        { id: 'developer', label: lang === 'zh' ? '开发者门户' : 'Developer', path: '/developer' },
        { id: 'reports', label: lang === 'zh' ? '报告中心' : 'Reports', path: '/reports' },
        { id: 'pricing', label: lang === 'zh' ? '定价与套餐' : 'Pricing', path: '/pricing' },
        { id: 'help', label: lang === 'zh' ? '帮助与反馈' : 'Help', path: '/help' },
        { id: 'tour', label: lang === 'zh' ? '重看新手导览' : 'Replay tour', path: '/?tour=1' },
      ],
    },
  ];

  // 已登录用户信息（页面级导航，每次整页加载时读取，2026-08-13）
  const storedAuth = readAuth();
  const userEmail = storedAuth?.principal?.email;

  return (
    <aside data-tour="sidebar" className="sticky top-0 hidden h-screen w-[248px] shrink-0 overflow-y-auto border-r border-white/8 bg-[#13161A] px-4 py-5 text-[#F3F5F7] md:block max-[1100px]:hidden">
      {/* Decorative gradients */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top_left,rgba(110,168,255,0.14),transparent_60%)]" />

      {/* Brand */}
      <div className="relative border-b border-white/8 pb-4 mb-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/60">
          {lang === 'zh' ? 'AEMO Intelligence' : 'AEMO INTELLIGENCE'}
        </div>
        <div className="mt-1 text-xs text-white/60">
          {lang === 'zh' ? 'BESS 投资决策平台' : 'BESS Investment Platform'}
        </div>
      </div>

      {/* ─── 市场切换 ─── */}
      <div className="relative mb-1">
        <div className="px-1 mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/60">
          {lang === 'zh' ? '市场' : 'MARKET'}
        </div>
        <div className="grid gap-1">
          {markets.map((m) => {
            const isActive = activePage === m.id;
            return (
              <motion.a
                key={m.id}
                href={m.path}
                whileHover={prefersReducedMotion ? undefined : { x: 2 }}
                className={`relative flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-all ${
                  isActive
                    ? 'bg-white/10 text-white font-medium border border-white/12'
                    : 'text-white/60 hover:text-white hover:bg-white/5 border border-transparent'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-[#8AB7FF]' : 'bg-white/20'}`} />
                <span>{m.label}</span>
                <span className="text-[10px] text-white/60 ml-auto">{m.sub}</span>
              </motion.a>
            );
          })}
        </div>
      </div>

      {/* ─── 其他分组（智能分析 / 其他市场 / 系统） ─── */}
      {groups.map((group) => (
        <div key={group.title} className="relative mt-4 border-t border-white/8 pt-3">
          <div className="px-1 mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/60">
            {group.title}
          </div>
          <div className="grid gap-0.5">
            {group.links.map((item) => {
              const isActive = activePage === item.id;
              return (
                <motion.a
                  key={item.id}
                  href={item.path}
                  whileHover={prefersReducedMotion ? undefined : { x: 2 }}
                  className={`flex items-center rounded-md px-3 py-1.5 text-xs transition-all ${
                    isActive
                      ? 'bg-white/8 text-white font-medium'
                      : 'text-white/60 hover:text-white/70 hover:bg-white/4'
                  }`}
                >
                  {item.label}
                </motion.a>
              );
            })}
          </div>
        </div>
      ))}

      {/* 已登录用户块（2026-08-13） */}
      {userEmail && (
        <div className="relative mt-4 border-t border-white/8 pt-3">
          <div className="flex items-center justify-between rounded-md bg-white/4 px-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-[11px] text-white/70">{userEmail}</div>
              <a href="/account" className="text-[10px] text-[#8AB7FF] hover:underline">
                {lang === 'zh' ? '账户中心 →' : 'Account →'}
              </a>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
