/**
 * PageShell — 布局外壳
 *
 * 包含侧边栏导航 + 页面头部 + 筛选器栏 + 语言切换。
 * 纯布局组件，不包含业务逻辑。
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4
 */

import SidebarNavigation from './SidebarNavigation';
import FilterBar from './FilterBar';
import { useTheme } from '../contexts/ThemeContext';
import { Sun, Moon } from 'lucide-react';

export default function PageShell({
  config,
  lang,
  onLangToggle,
  years,
  children,
}) {
  const activePage = config.id === 'WEM' ? 'wem' : 'aemo';
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="min-h-screen pb-20">
      <div className="mx-auto flex min-h-screen w-full gap-0 max-[1100px]:block">
        <SidebarNavigation
          activePage={activePage}
          lang={lang}
        />

        <div className="min-w-0 flex-1 pl-1 pt-1">
          <main className="grid-container">
            {/* Header */}
            <div className="col-span-12 mt-4 mb-2 flex items-center justify-between">
              <div>
                <h1 className="font-serif text-2xl text-[var(--color-text)]" style={{ letterSpacing: '-0.02em' }}>
                  {config.label}
                </h1>
                <p className="text-xs text-[var(--color-muted)] mt-1">
                  {lang === 'zh' ? '结算间隔' : 'Settlement'}: {config.settlementIntervalMinutes} min · {config.timezoneLabel}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleTheme}
                  className="p-2 border border-[var(--color-border)] rounded-full hover:border-[var(--color-text)] transition-colors"
                  aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                >
                  {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
                </button>
                <button
                  onClick={onLangToggle}
                  className="px-3 py-1.5 text-xs font-bold border border-[var(--color-border)] rounded-full hover:border-[var(--color-text)] transition-colors"
                  aria-label="Toggle language"
                >
                  {lang === 'zh' ? 'EN' : '中文'}
                </button>
              </div>
            </div>

            {/* FilterBar */}
            <div className="col-span-12 mb-6">
              <FilterBar config={config} years={years} lang={lang} />
            </div>

            {/* Main content */}
            <div className="col-span-12 space-y-4">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
