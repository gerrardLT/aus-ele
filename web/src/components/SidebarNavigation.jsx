import { motion, useReducedMotion } from 'framer-motion';

/**
 * SidebarNavigation — 侧边栏导航
 *
 * 结构清晰的三层导航：
 * 1. 市场切换（NEM / WEM）— 当前市场高亮，非当前弱化
 * 2. 阶段导航 — 仅显示当前市场的分析阶段，带编号
 * 3. 其他入口 — 研究工具 + 系统
 */
export default function SidebarNavigation({
  activePage,
  sectionLinks = [],
  activeSection,
  onSectionClick,
  lang = 'zh',
}) {
  const prefersReducedMotion = useReducedMotion();

  const markets = [
    { id: 'aemo', label: 'NEM', sub: lang === 'zh' ? '国家电力市场' : 'National Electricity Market', path: '/' },
    { id: 'wem', label: 'WEM', sub: lang === 'zh' ? '西澳电力市场' : 'Wholesale Electricity Market', path: '/wem' },
  ];

  const otherLinks = [
    { id: 'agent', label: lang === 'zh' ? 'AI 编排分析' : 'AI Agent', path: '/agent' },
    { id: 'finland', label: lang === 'zh' ? 'Finland 市场' : 'Finland', path: '/finland' },
    { id: 'fingrid', label: 'Fingrid', path: '/fingrid' },
    { id: 'developer', label: lang === 'zh' ? '开发者门户' : 'Developer', path: '/developer' },
  ];

  return (
    <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 overflow-y-auto border-r border-white/8 bg-[#13161A] px-4 py-5 text-[#F3F5F7] md:block max-[1100px]:hidden">
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

      {/* ─── 阶段导航（当前市场） ─── */}
      {sectionLinks.length > 0 && (
        <div className="relative mt-4 border-t border-white/8 pt-3">
          <div className="px-1 mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/60">
            {lang === 'zh' ? '分析阶段' : 'STAGES'}
          </div>
          <div className="grid gap-0.5">
            {sectionLinks.map((item, index) => {
              const isActive = activeSection === item.id;
              return (
                <motion.button
                  key={item.id}
                  onClick={() => onSectionClick(item.id)}
                  whileHover={prefersReducedMotion ? undefined : { x: 2 }}
                  className={`relative flex items-center gap-2 rounded-md px-3 py-1.5 text-left text-[13px] transition-all ${
                    isActive
                      ? 'bg-white/8 text-white font-medium'
                      : 'text-white/60 hover:text-white hover:bg-white/4'
                  }`}
                >
                  <span className={`w-4 h-4 flex items-center justify-center rounded text-[10px] font-bold ${
                    isActive ? 'bg-[#8AB7FF] text-[#13161A]' : 'bg-white/10 text-white/60'
                  }`}>
                    {index + 1}
                  </span>
                  <span className="truncate">{item.label}</span>
                </motion.button>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── 其他入口 ─── */}
      <div className="relative mt-4 border-t border-white/8 pt-3">
        <div className="px-1 mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/60">
          {lang === 'zh' ? '其他' : 'OTHER'}
        </div>
        <div className="grid gap-0.5">
          {otherLinks.map((item) => {
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
    </aside>
  );
}
