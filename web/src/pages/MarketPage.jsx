/**
 * MarketPage — 统一市场页面编排器（Tab 切换模式）
 *
 * 根据 market prop 加载对应配置，使用顶部 Tab 栏切换阶段。
 * 只渲染当前激活 Tab 对应的阶段模块，提升加载速度和用户体验。
 * NEM 渲染 7 个 Tab，WEM 渲染 5 个 Tab。
 *
 * Requirements: 1.2, 1.3, 11.3
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import PageShell from '../components/PageShell';
import DynamicStage from '../components/funnel/DynamicStage';
import { getMarketConfig, buildSectionLinks, DEFAULT_BESS_PARAMS } from '../lib/marketConfig';
import { useFilters } from '../contexts/FilterContext';
import { useStageSummaries } from '../hooks/useStageSummaries';
import AnomalyBadge from '../components/AnomalyBadge';
import AnalystChat from '../components/AnalystChat';
import { fetchJson } from '../lib/apiClient';
import { getApiBase } from '../lib/apiBase';

const API_BASE = getApiBase();

/**
 * @param {{ market: 'NEM'|'WEM' }} props
 */
export default function MarketPage({ market }) {
  const config = getMarketConfig(market);
  const { filters, setFilter } = useFilters();

  // Language state (persisted to localStorage)
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
  });

  // Active tab index (persisted per market)
  const [activeTabIndex, setActiveTabIndex] = useState(() => {
    try {
      const saved = localStorage.getItem(`tab_${market}`);
      return saved ? Math.min(parseInt(saved, 10), config.stages.length - 1) : 0;
    } catch { return 0; }
  });

  // Available years from API
  const [years, setYears] = useState([]);

  // Set initial region from config on mount
  useEffect(() => {
    setFilter('region', config.defaultRegion);
  }, [config.defaultRegion, setFilter]);

  // Fetch available years
  useEffect(() => {
    fetchJson(`${API_BASE}/years`)
      .then(data => {
        if (data.years?.length > 0) {
          setYears(data.years);
          setFilter('year', data.years[0]);
        }
      })
      .catch(err => console.error('Failed to fetch years:', err));
  }, [setFilter]);

  // Persist language
  useEffect(() => {
    try { localStorage.setItem('app_lang', lang); } catch { /* ignore */ }
  }, [lang]);

  // Persist active tab
  useEffect(() => {
    try { localStorage.setItem(`tab_${market}`, String(activeTabIndex)); } catch { /* ignore */ }
  }, [activeTabIndex, market]);

  // Reset tab when market changes
  useEffect(() => {
    setActiveTabIndex(0);
  }, [market]);

  // Section links for sidebar (still useful for context)
  const sectionLinks = buildSectionLinks(lang, config.id);

  // Tab click handler
  const handleTabClick = useCallback((index) => {
    setActiveTabIndex(index);
  }, []);

  // Sidebar section click → switch to that tab
  const handleSectionClick = useCallback((stageId) => {
    const index = config.stages.findIndex(s => s.id === stageId);
    if (index >= 0) setActiveTabIndex(index);
  }, [config.stages]);

  // Language toggle
  const handleLangToggle = useCallback(() => {
    setLang(prev => prev === 'zh' ? 'en' : 'zh');
  }, []);

  // S6/F4: track visited tabs for status badges
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([0]));
  useEffect(() => {
    setVisitedTabs(prev => new Set([...prev, activeTabIndex]));
  }, [activeTabIndex]);

  // S6/F6: prefetch next stage dataDependencies when idle
  const prefetchDone = useRef(new Set());
  useEffect(() => {
    const nextIndex = activeTabIndex + 1;
    if (nextIndex >= config.stages.length) return;
    const nextStage = config.stages[nextIndex];
    const deps = nextStage.modules.flatMap(m => m.dataDependencies || []);
    if (!deps.length || prefetchDone.current.has(nextStage.id)) return;

    const doPrefetch = () => {
      prefetchDone.current.add(nextStage.id);
      deps.forEach(url => {
        const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;
        fetch(fullUrl, { method: 'HEAD', cache: 'force-cache' }).catch(() => {});
      });
    };

    if ('requestIdleCallback' in window) {
      const id = requestIdleCallback(doPrefetch, { timeout: 3000 });
      return () => cancelIdleCallback(id);
    } else {
      const id = setTimeout(doPrefetch, 2000);
      return () => clearTimeout(id);
    }
  }, [activeTabIndex, config.stages]);

  // S6/F2: fetch stage summaries once at page level (not per-tab)
  const summaryMarket = filters.region === 'WEM' ? 'WEM' : 'NEM';
  const { summaries, loading: summaryLoading } = useStageSummaries(
    summaryMarket, filters.region, filters.year, DEFAULT_BESS_PARAMS
  );

  // Current active stage
  const activeStage = config.stages[activeTabIndex];
  const activeSection = activeStage?.id || '';

  return (
    <PageShell
      config={config}
      sectionLinks={sectionLinks}
      activeSection={activeSection}
      onSectionClick={handleSectionClick}
      lang={lang}
      onLangToggle={handleLangToggle}
      years={years}
    >
      {/* S6/F3: Persistent context bar + U4: Anomaly badge */}
      <div className="flex items-center gap-3 mb-2 px-1 text-xs text-[var(--color-muted)]">
        <span className="inline-flex items-center gap-1 rounded bg-[var(--color-border)] px-2 py-0.5 font-medium">
          📍 {filters.region}
        </span>
        <span className="inline-flex items-center gap-1 rounded bg-[var(--color-border)] px-2 py-0.5 font-medium">
          📅 {filters.year || '—'}
        </span>
        {filters.dayType && (
          <span className="inline-flex items-center gap-1 rounded bg-[var(--color-border)] px-2 py-0.5 font-medium">
            📊 {filters.dayType}
          </span>
        )}
        <div className="ml-auto">
          <AnomalyBadge lang={lang} onNavigate={(stageId) => {
            const idx = config.stages.findIndex(s => s.id === stageId);
            if (idx >= 0) setActiveTabIndex(idx);
          }} />
        </div>
      </div>

      {/* Tab Navigation Bar */}
      <div className="sticky top-0 z-20 -mx-1 mb-3 overflow-x-auto border-b border-[var(--color-border)] bg-[var(--color-bg)]/95 backdrop-blur-sm">
        <div className="flex min-w-max gap-0" role="tablist" aria-label={lang === 'zh' ? '分析阶段' : 'Analysis Stages'}>
          {config.stages.map((stage, index) => {
            const isActive = index === activeTabIndex;
            const title = stage.title[lang] || stage.title.zh;
            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => handleTabClick(index)}
                className={`
                  relative flex items-center gap-2 px-4 min-h-[44px] text-sm font-sans whitespace-nowrap transition-colors
                  ${isActive
                    ? 'text-[var(--color-text)] font-bold'
                    : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                  }
                `}
                aria-selected={isActive}
                role="tab"
              >
                {/* Stage number badge with S6/F4 status dot */}
                <span className={`
                  inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold flex-shrink-0
                  ${isActive
                    ? 'bg-[var(--color-primary)] text-white'
                    : visitedTabs.has(index)
                      ? 'bg-green-100 text-green-700 border border-green-300'
                      : 'bg-[var(--color-border)] text-[var(--color-muted)]'
                  }
                `}>
                  {visitedTabs.has(index) && !isActive ? '✓' : index + 1}
                </span>
                <span>{title}</span>
                {/* Active indicator line */}
                {isActive && (
                  <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-[var(--color-primary)] rounded-full" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Stage Content — only render the selected tab */}
      {activeStage && (
        <DynamicStage
          key={activeStage.id}
          stageDefinition={activeStage}
          stageNumber={activeTabIndex + 1}
          config={config}
          lang={lang}
          onVisible={() => {}}
          conclusionData={summaries[activeStage.id] || null}
          isSummaryLoading={summaryLoading[activeStage.id] ?? false}
        />
      )}

      {/* Navigation hints */}
      <div className="mt-4 flex items-center justify-between border-t border-[var(--color-border)] pt-3">
        {activeTabIndex > 0 && (
          <button
            type="button"
            onClick={() => setActiveTabIndex(activeTabIndex - 1)}
            className="flex items-center gap-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            <span>←</span>
            <span>{config.stages[activeTabIndex - 1]?.title[lang]}</span>
          </button>
        )}
        <div className="flex-1" />
        {activeTabIndex < config.stages.length - 1 && (
          <button
            type="button"
            onClick={() => setActiveTabIndex(activeTabIndex + 1)}
            className="flex items-center gap-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            <span>{config.stages[activeTabIndex + 1]?.title[lang]}</span>
            <span>→</span>
          </button>
        )}
      </div>

      {/* U6: AI Analyst Chat FAB */}
      <AnalystChat lang={lang} />

    </PageShell>
  );
}
