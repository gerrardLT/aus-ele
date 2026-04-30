import { Suspense, lazy, useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { ArrowRight, Activity, Database, ChevronUp, List } from 'lucide-react';
import PriceChart from './components/PriceChart';
import SummaryStats from './components/SummaryStats';
import { fetchJson } from './lib/apiClient';
import { translations } from './translations';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';
const HourlyDistributionChart = lazy(() => import('./components/HourlyDistributionChart'));
const PeakAnalysis = lazy(() => import('./components/PeakAnalysis'));
const FcasAnalysis = lazy(() => import('./components/FcasAnalysis'));
const BessSimulator = lazy(() => import('./components/BessSimulator'));
const RevenueStacking = lazy(() => import('./components/RevenueStacking'));
const ChargingWindow = lazy(() => import('./components/ChargingWindow'));
const CycleCost = lazy(() => import('./components/CycleCost'));
const InvestmentAnalysis = lazy(() => import('./components/InvestmentAnalysis'));
const GridForecast = lazy(() => import('./components/GridForecast'));

"use client";

function SectionFallback({ minHeight = '320px' }) {
  return (
    <div
      className="flex items-center justify-center rounded-3xl border border-[var(--color-border)] bg-[var(--color-surface)]/70 px-6 text-sm text-[var(--color-muted)]"
      style={{ minHeight }}
    >
      Loading section...
    </div>
  );
}

function computeWindowSummaryMetrics(points = []) {
  const numericPrices = points
    .map((point) => Number(point?.price))
    .filter((value) => Number.isFinite(value));

  if (!numericPrices.length) {
    return {
      stats: { min: 0, max: 0, avg: 0 },
      advancedStats: {
        neg_ratio: 0,
        neg_avg: null,
        neg_min: null,
        pos_avg: null,
        pos_max: null,
        days_below_100: 0,
        days_above_300: 0,
      },
    };
  }

  const negativePrices = numericPrices.filter((value) => value < 0);
  const positivePrices = numericPrices.filter((value) => value > 0);
  const byDay = new Map();

  points.forEach((point) => {
    const dayKey = String(point?.time || '').slice(0, 10);
    const price = Number(point?.price);
    if (!dayKey || !Number.isFinite(price)) {
      return;
    }
    const dayValues = byDay.get(dayKey) || [];
    dayValues.push(price);
    byDay.set(dayKey, dayValues);
  });

  return {
    stats: {
      min: Number(Math.min(...numericPrices).toFixed(2)),
      max: Number(Math.max(...numericPrices).toFixed(2)),
      avg: Number((numericPrices.reduce((sum, value) => sum + value, 0) / numericPrices.length).toFixed(2)),
    },
    advancedStats: {
      neg_ratio: Number(((negativePrices.length / numericPrices.length) * 100).toFixed(2)),
      neg_avg: negativePrices.length
        ? Number((negativePrices.reduce((sum, value) => sum + value, 0) / negativePrices.length).toFixed(2))
        : null,
      neg_min: negativePrices.length ? Number(Math.min(...negativePrices).toFixed(2)) : null,
      pos_avg: positivePrices.length
        ? Number((positivePrices.reduce((sum, value) => sum + value, 0) / positivePrices.length).toFixed(2))
        : null,
      pos_max: positivePrices.length ? Number(Math.max(...positivePrices).toFixed(2)) : null,
      days_below_100: [...byDay.values()].filter((values) => values.some((value) => value < -100)).length,
      days_above_300: [...byDay.values()].filter((values) => values.some((value) => value > 300)).length,
    },
  };
}

function App() {
  const prefersReducedMotion = useReducedMotion();
  const [lang, setLang] = useState(() => {
    try {
      return localStorage.getItem('app_lang') || 'zh';
    } catch {
      return 'zh';
    }
  });
  const [years, setYears] = useState([]);
  const [selectedYear, setSelectedYear] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState('ALL');
  const [selectedQuarter, setSelectedQuarter] = useState('ALL');
  const [selectedDayType, setSelectedDayType] = useState('ALL');
  const [selectedRegion, setSelectedRegion] = useState('NSW1');
  const [chartData, setChartData] = useState(null);
  const [visibleChartData, setVisibleChartData] = useState([]);
  const [eventOverlay, setEventOverlay] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [showToc, setShowToc] = useState(false);
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [showMonthFilter, setShowMonthFilter] = useState(true);
  const [activeSection, setActiveSection] = useState('');
  const [showStickyFilter, setShowStickyFilter] = useState(false);
  const filterPanelRef = useRef(null);

  // Scroll observer for back-to-top button and active section tracking
  useEffect(() => {
    const handleScroll = () => {
      setShowBackToTop(window.scrollY > 600);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // IntersectionObserver: show sticky filter bar when main filter panel scrolls out of view
  useEffect(() => {
    const el = filterPanelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setShowStickyFilter(!entry.isIntersecting);
      },
      { threshold: 0, rootMargin: '-48px 0px 0px 0px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [loading, error]);

  // Scroll-based active section tracking (more reliable than IntersectionObserver for tall sections)
  useEffect(() => {
    const sectionIds = ['sec-overview', 'sec-forecast', 'sec-negative', 'sec-arbitrage', 'sec-fcas', 'sec-simulator', 'sec-stacking', 'sec-charging', 'sec-cycle', 'sec-investment'];

    const handleScroll = () => {
      const offset = 120; // account for sticky bar + margin
      let current = '';
      for (const id of sectionIds) {
        const el = document.getElementById(id);
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.top <= offset) {
            current = id;
          }
        }
      }
      setActiveSection(current);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll(); // initial check
    return () => window.removeEventListener('scroll', handleScroll);
  }, [loading, error]);

  const scrollToSection = useCallback((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setShowToc(false);
    }
  }, []);

  const scrollToTop = useCallback(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const t = translations[lang];
  const sectionLinks = [
    { id: 'sec-overview', label: lang === 'zh' ? '总览' : 'Overview' },
    { id: 'sec-forecast', label: t.forecast?.sectionLabel || (lang === 'zh' ? '电网预测' : 'Forecast') },
    { id: 'sec-negative', label: lang === 'zh' ? '负电价' : 'Negative Price' },
    { id: 'sec-arbitrage', label: lang === 'zh' ? '套利分析' : 'Arbitrage' },
    { id: 'sec-fcas', label: 'FCAS' },
    { id: 'sec-simulator', label: lang === 'zh' ? '盈利模拟' : 'Simulator' },
    { id: 'sec-stacking', label: lang === 'zh' ? '收入叠加' : 'Stacking' },
    { id: 'sec-charging', label: lang === 'zh' ? '充电窗口' : 'Charging' },
    { id: 'sec-cycle', label: lang === 'zh' ? '循环成本' : 'Cycle Cost' },
    { id: 'sec-investment', label: lang === 'zh' ? '投资分析' : 'Investment' },
  ];
  const simulatorScopeNote = t.simulator.fullYearModelNote || (
    lang === 'zh'
      ? '使用全年代表性参数；month / quarter / day_type 筛选不作用于本模块，事件与预测信号仅用于说明。'
      : 'Uses full-year representative data. Month, quarter, and day-type filters do not apply here. Event and forecast signals are explanatory only and are not injected into simulator results.'
  );
  const investmentScopeNote = t.investment?.fullYearModelNote || (
    lang === 'zh'
      ? '使用全年历史与现金流假设；month / quarter / day_type 筛选不作用于本模块，事件与预测信号不会自动改写收益、NPV、IRR 或回本期。'
      : 'Uses full-year historical and cash-flow assumptions. Month, quarter, and day-type filters do not apply here. Event and forecast signals do not automatically change revenue, NPV, IRR, or payback.'
  );

  // Initial Fetch Setup
  const fetchInitial = async () => {
    try {
      setError(false);
      setLoading(true);
      const [yearsData, sumData] = await Promise.all([
        fetchJson(`${API_BASE}/years`),
        fetchJson(`${API_BASE}/summary`)
      ]);

      if (yearsData.years?.length > 0) {
        setYears(yearsData.years);
        setSelectedYear(yearsData.years[0]);
      } else {
        setLoading(false);
      }
      if (sumData.last_update) {
        setLastUpdate(sumData.last_update);
      }
    } catch (err) {
      console.error("Failed to fetch initial data", err);
      setError(true);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitial();
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem('app_lang', lang);
    } catch {
      // Ignore localStorage write failures in restricted environments.
    }
  }, [lang]);

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      const res = await fetch(`${API_BASE}/sync_data`, { method: 'POST' });
      if (res.ok) {
         // Simple alert for now as per requirement
         alert(lang === 'zh' ? '数据同步已在后台启动，可能需要几分钟。' : 'Data sync started in background. This may take a few minutes.');
      } else {
         alert(lang === 'zh' ? '更新失败，请检查服务日志。' : 'Update failed. Please check server logs.');
      }
    } catch(e) {
      console.error(e);
      alert(lang === 'zh' ? '触发更新时发生错误。' : 'Error triggering update.');
    }
    setTimeout(() => setIsSyncing(false), 2000);
  };

  // Fetch metrics when year or region changes
  useEffect(() => {
    if (!selectedYear) return;

    setLoading(true);
    let url = `${API_BASE}/price-trend?year=${selectedYear}&region=${selectedRegion}&limit=1500`;
    if (selectedMonth !== 'ALL') {
      url += `&month=${selectedMonth}`;
    }
    if (selectedQuarter !== 'ALL') {
      url += `&quarter=${selectedQuarter}`;
    }
    if (selectedDayType !== 'ALL') {
      url += `&day_type=${selectedDayType}`;
    }

    let eventUrl = `${API_BASE}/event-overlays?year=${selectedYear}&region=${selectedRegion}`;
    if (selectedMonth !== 'ALL') {
      eventUrl += `&month=${selectedMonth}`;
    }
    if (selectedQuarter !== 'ALL') {
      eventUrl += `&quarter=${selectedQuarter}`;
    }
    if (selectedDayType !== 'ALL') {
      eventUrl += `&day_type=${selectedDayType}`;
    }

    Promise.all([
      fetchJson(url),
      fetchJson(eventUrl).catch(() => null),
    ])
      .then(([priceData, overlayData]) => {
        setChartData(priceData);
        setVisibleChartData(Array.isArray(priceData?.data) ? priceData.data : []);
        setEventOverlay(overlayData);
        setError(false);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setError(true);
        setLoading(false);
      });
  }, [selectedYear, selectedMonth, selectedQuarter, selectedDayType, selectedRegion]);

    const visibleSummaryMetrics = computeWindowSummaryMetrics(
      visibleChartData.length ? visibleChartData : (chartData?.data || [])
    );

    const tocSections = [
      { id: 'sec-overview', label: lang === 'zh' ? '市场总览' : 'Overview', shortLabel: lang === 'zh' ? '总览' : 'Overview' },
      { id: 'sec-forecast', label: t.forecast?.sectionLabel || (lang === 'zh' ? '电网预测' : 'Grid Forecast'), shortLabel: lang === 'zh' ? '预测' : 'Forecast' },
      { id: 'sec-negative', label: lang === 'zh' ? '负电价分布' : 'Negative Price', shortLabel: lang === 'zh' ? '负电价' : 'Negative' },
      { id: 'sec-arbitrage', label: lang === 'zh' ? '储能套利' : 'Arbitrage', shortLabel: lang === 'zh' ? '套利' : 'Arbitrage' },
      { id: 'sec-fcas', label: lang === 'zh' ? 'FCAS 分析' : 'FCAS', shortLabel: 'FCAS' },
      { id: 'sec-simulator', label: lang === 'zh' ? '盈利模拟' : 'Simulator', shortLabel: lang === 'zh' ? '模拟' : 'Sim' },
      { id: 'sec-stacking', label: lang === 'zh' ? '收入叠加' : 'Stacking', shortLabel: lang === 'zh' ? '叠加' : 'Stack' },
      { id: 'sec-charging', label: lang === 'zh' ? '充电窗口' : 'Charging', shortLabel: lang === 'zh' ? '充电' : 'Charge' },
      { id: 'sec-cycle', label: lang === 'zh' ? '循环成本' : 'Cycle Cost', shortLabel: lang === 'zh' ? '循环' : 'Cycle' },
      { id: 'sec-investment', label: lang === 'zh' ? '投资分析' : 'Investment', shortLabel: lang === 'zh' ? '投资' : 'Invest' },
    ];

    return (
    <div className="min-h-screen pb-20">

      <div className="mx-auto flex min-h-screen w-full gap-0 max-[1100px]:block">

      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 overflow-hidden border-r border-white/8 bg-[#13161A] px-4 py-5 text-[#F3F5F7] md:block max-[1100px]:hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top_left,rgba(110,168,255,0.14),transparent_60%)]" />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-px bg-[linear-gradient(to_bottom,transparent,rgba(255,255,255,0.08),transparent)]" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-[linear-gradient(to_top,rgba(255,255,255,0.02),transparent)]" />

        <div className="relative border-b border-white/8 pb-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/42">
            {t.nav.brand}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <motion.span
              aria-hidden="true"
              className="inline-block h-2 w-2 rounded-full bg-[#7FB0FF]"
              animate={prefersReducedMotion ? undefined : { opacity: [0.45, 1, 0.45], scale: [1, 1.18, 1] }}
              transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
            />
            <span className="text-[10px] uppercase tracking-[0.18em] text-white/38">
              {lang === 'zh' ? '研究工作台' : 'Research Desk'}
            </span>
          </div>
          <div className="mt-2 pr-3 text-sm leading-6 text-white/58">
            {t.header.title1} {t.header.title2}
          </div>
        </div>

        <div className="relative mt-4">
          <div className="px-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/38">
            {lang === 'zh' ? '市场模块' : 'Market Modules'}
          </div>
          <div className="mt-2 grid gap-1">
            {sectionLinks.map((item) => {
              const isActive = activeSection === item.id || (!activeSection && item.id === 'sec-overview');
              return (
                <motion.button
                  key={item.id}
                  onClick={() => scrollToSection(item.id)}
                  whileHover={prefersReducedMotion ? undefined : { x: 3 }}
                  whileTap={prefersReducedMotion ? undefined : { scale: 0.988 }}
                  transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                  className={`relative flex min-h-[40px] items-center overflow-hidden rounded-lg px-3 text-left text-sm transition-colors ${
                    isActive
                      ? 'text-white'
                      : 'border border-transparent text-white/62 hover:text-white'
                  }`}
                >
                  {isActive ? (
                    <motion.span
                      layoutId="sidebar-active-item"
                      className="absolute inset-0 rounded-lg border border-white/10 bg-[linear-gradient(135deg,rgba(255,255,255,0.14),rgba(255,255,255,0.06))] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_12px_30px_rgba(0,0,0,0.22)]"
                      transition={{ type: 'spring', stiffness: 380, damping: 34, mass: 0.7 }}
                    />
                  ) : (
                    <span className="absolute inset-0 rounded-lg bg-transparent transition-colors duration-200 hover:bg-white/6" />
                  )}
                  <span className={`absolute left-1 top-1 bottom-1 w-0.5 rounded-full bg-[#8AB7FF] transition-opacity duration-200 ${isActive ? 'opacity-100' : 'opacity-0'}`} />
                  <span className={`relative z-10 transition-transform duration-200 ${isActive ? 'translate-x-1 font-medium' : ''}`}>
                    {item.label}
                  </span>
                </motion.button>
              );
            })}
          </div>
        </div>

        <div className="relative mt-5 border-t border-white/8 pt-4">
          <div className="px-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/38">
            {lang === 'zh' ? '其他入口' : 'Other Views'}
          </div>
          <div className="mt-2 grid gap-1">
            <motion.a
              href="/fingrid"
              whileHover={prefersReducedMotion ? undefined : { x: 3 }}
              whileTap={prefersReducedMotion ? undefined : { scale: 0.988 }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
              className="relative flex min-h-[40px] items-center overflow-hidden rounded-lg px-3 text-sm text-white/56 transition-colors hover:text-white"
            >
              <span className="absolute inset-0 rounded-lg bg-transparent transition-colors duration-200 hover:bg-white/6" />
              <span className="relative z-10">{t.nav.fingrid || 'Fingrid'}</span>
            </motion.a>
            <motion.a
              href="/developer"
              whileHover={prefersReducedMotion ? undefined : { x: 3 }}
              whileTap={prefersReducedMotion ? undefined : { scale: 0.988 }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
              className="relative flex min-h-[40px] items-center overflow-hidden rounded-lg px-3 text-sm text-white/56 transition-colors hover:text-white"
            >
              <span className="absolute inset-0 rounded-lg bg-transparent transition-colors duration-200 hover:bg-white/6" />
              <span className="relative z-10">{t.nav.developerPortal || 'Developer Portal'}</span>
            </motion.a>
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1 pl-1 pt-2">

      {/* Back to Top Button */}
      <AnimatePresence>
        {showBackToTop && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            onClick={scrollToTop}
            className="fixed right-6 bottom-8 z-50 w-10 h-10 flex items-center justify-center bg-[var(--color-inverted)] text-[var(--color-inverted-text)] rounded-full shadow-lg hover:scale-110 transition-transform"
            aria-label="Back to top"
          >
            <ChevronUp size={20} />
          </motion.button>
        )}
      </AnimatePresence>
      {/* Sticky Compact Filter Bar 鈥?appears when main filters scroll out of view */}
      <AnimatePresence>
        {showStickyFilter && !loading && !error && (
          <motion.div
            initial={{ y: -48, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -48, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="fixed top-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-sm border-b border-[var(--color-border)] shadow-sm"
          >
            <div className="grid-container flex items-center justify-between h-12">
              {/* Left: Year selector */}
              <div className="flex items-center gap-1">
                <span className="text-[10px] font-bold tracking-widest text-[var(--color-muted)] uppercase mr-2 hidden sm:inline">
                  {lang === 'zh' ? '骞翠唤' : 'YEAR'}
                </span>
                {years.map(y => (
                  <button
                    key={y}
                    onClick={() => setSelectedYear(y)}
                    className={`px-3 py-1 text-xs font-mono transition-colors rounded ${
                      selectedYear === y
                        ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                        : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                    }`}
                  >
                    {y}
                  </button>
                ))}
              </div>

              {/* Center: Current section indicator */}
              {activeSection && (
                <div className="hidden md:flex items-center gap-2 text-xs text-[var(--color-muted)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-primary)]" />
                  <span className="font-sans tracking-wide">
                    {tocSections.find(s => s.id === activeSection)?.label || ''}
                  </span>
                </div>
              )}

              {/* Right: Region selector */}
              <div className="flex items-center gap-1">
                <span className="text-[10px] font-bold tracking-widest text-[var(--color-muted)] uppercase mr-2 hidden sm:inline">
                  {lang === 'zh' ? '鍖哄煙' : 'REGION'}
                </span>
                {['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1', 'WEM'].map(r => (
                  <button
                    key={r}
                    onClick={() => setSelectedRegion(r)}
                    className={`px-2.5 py-1 text-xs font-mono transition-colors rounded ${
                      selectedRegion === r
                        ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                        : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                    }`}
                  >
                    {r.replace('1', '')}
                  </button>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="grid-container">

        <motion.header
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="col-span-12 mb-6 flex flex-col gap-4 border-b border-[var(--color-border)] pb-5 lg:flex-row lg:items-center lg:justify-between"
        >
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-2">
            <h1 className="text-2xl font-bold leading-tight md:text-3xl">
              {t.header.title1} {t.header.title2}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm font-sans text-[var(--color-muted)]">
            {lastUpdate ? (
              <span className="rounded-full border border-[var(--color-border)] px-3 py-1 text-xs">
                {lastUpdate}
              </span>
            ) : null}
            <button
              onClick={handleSync}
              disabled={isSyncing}
              title="Trigger Background Data Sync"
              className="flex min-h-[40px] items-center gap-2 rounded border border-[var(--color-border)] px-3 py-1.5 transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]"
            >
              <svg className={isSyncing ? "h-4 w-4 animate-spin" : "h-4 w-4"} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>{isSyncing ? (t.nav.syncing || 'Syncing') : (t.nav.sync || 'Sync')}</span>
            </button>
            <button
              aria-label="Toggle language"
              title="Toggle language"
              onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
              className="min-h-[40px] rounded border border-[var(--color-border)] px-3 py-1.5 transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]"
            >
              {t.nav.toggleOptions}
            </button>
          </div>
        </motion.header>

        {/* Filters Panel (Black/White minimal controls) */}
        <div ref={filterPanelRef} className="col-span-12 mb-5 flex flex-col gap-4.5">

          {/* Top row: Year & Region */}
          <div className="flex flex-col justify-between gap-6 md:flex-row md:gap-4">

            <div className="flex flex-col gap-2.5">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.yearSelect}</span>
              <div className="flex flex-wrap gap-2">
                {years.map(y => (
                  <button
                    key={y}
                    onClick={() => setSelectedYear(y)}
                    className={`px-3.5 py-1 min-h-[32px] font-sans text-[13px] transition-colors
                      ${selectedYear === y
                        ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                        : 'bg-transparent text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]'
                      }`}
                  >
                    {y}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex w-full flex-col gap-2.5 md:w-auto md:items-end">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.regionSelect}</span>
              <div className="flex flex-wrap gap-2 md:justify-end">
                {['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1', 'WEM'].map(r => (
                  <button
                    key={r}
                    onClick={() => setSelectedRegion(r)}
                    className={`px-3.5 py-1 min-h-[32px] font-sans text-[13px] transition-colors border-b-2
                      ${selectedRegion === r
                        ? 'border-[var(--color-text)] text-[var(--color-text)] font-medium'
                        : 'border-transparent text-[var(--color-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text)]/30'
                      }`}
                  >
                    {r.replace('1', '')}
                  </button>
                ))}
              </div>
            </div>

          </div>

          {/* Middle row: Quarter & Day Type */}
          <div className="flex flex-col justify-between gap-6 border-t border-dashed border-[var(--color-border)] pt-5 md:flex-row md:gap-4">

            <div className="flex flex-col gap-2.5">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.quarterSelect}</span>
              <div className="flex flex-wrap gap-2">
                {['ALL', 'Q1', 'Q2', 'Q3', 'Q4'].map(q => (
                  <button
                    key={q}
                    onClick={() => { setSelectedQuarter(q); if (q !== 'ALL') setSelectedMonth('ALL'); }}
                    className={`px-4 py-1.5 min-h-[38px] font-sans text-[13px] transition-colors rounded-full border
                      ${selectedQuarter === q
                        ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-inverted)]'
                        : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-text)]'
                      }`}
                  >
                    {q === 'ALL' ? t.filters.allQuarters : t.filters[q.toLowerCase()]}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex w-full flex-col gap-2.5 md:w-auto md:items-end">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.dayTypeSelect}</span>
              <div className="flex flex-wrap gap-2 md:justify-end">
                {['ALL', 'WEEKDAY', 'WEEKEND'].map(d => (
                  <button
                    key={d}
                    onClick={() => setSelectedDayType(d)}
                    className={`px-4 py-1.5 min-h-[38px] font-sans text-[13px] transition-colors rounded-full border
                      ${selectedDayType === d
                        ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-inverted)]'
                        : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-text)]'
                      }`}
                  >
                    {d === 'ALL' ? t.filters.allDays : t.filters[d.toLowerCase()]}
                  </button>
                ))}
              </div>
            </div>

          </div>

          {/* Bottom row: Month (collapsible) + Reset */}
          <div className="flex flex-col gap-2.5 border-t border-dashed border-[var(--color-border)] pt-5">
            <div className="flex items-center justify-between">
              <button
                onClick={() => setShowMonthFilter(prev => !prev)}
                className="flex items-center gap-2 text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase hover:text-[var(--color-text)] transition-colors"
              >
                {t.filters.monthSelect}
                <span className={`transition-transform duration-200 ${showMonthFilter ? 'rotate-90' : ''}`}>+</span>
                {selectedMonth !== 'ALL' && (
                  <span className="ml-1 px-2 py-0.5 bg-[var(--color-inverted)] text-[var(--color-inverted-text)] rounded-full text-[10px] font-medium normal-case">
                    {lang === 'zh' ? `${parseInt(selectedMonth, 10)}月` : `M${selectedMonth}`}
                  </span>
                )}
              </button>
              {(selectedMonth !== 'ALL' || selectedQuarter !== 'ALL' || selectedDayType !== 'ALL') && (
                <button
                  onClick={() => { setSelectedMonth('ALL'); setSelectedQuarter('ALL'); setSelectedDayType('ALL'); }}
                  className="text-xs font-sans text-[var(--color-muted)] hover:text-[var(--color-error)] transition-colors underline underline-offset-2"
                >
                  {t.filters.resetFilters || 'Reset Filters'}
                </button>
              )}
            </div>
            <AnimatePresence>
              {showMonthFilter && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="flex flex-wrap gap-2 pt-1">
                    {['ALL', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'].map((m) => {
                      const monthLabels = lang === 'zh'
                        ? ['全年', '1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
                        : ['All', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                      const idx = m === 'ALL' ? 0 : parseInt(m, 10);
                      return (
                        <button
                          key={m}
                          onClick={() => { setSelectedMonth(m); if (m !== 'ALL') setSelectedQuarter('ALL'); }}
                          className={`px-3.5 py-1.5 min-h-[36px] font-sans text-[13px] transition-colors rounded-full border ${
                            selectedMonth === m
                              ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-inverted)]'
                              : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-text)]'
                          }`}
                        >
                          {monthLabels[idx]}
                        </button>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

        </div>

        {/* Data Presentation Area */}
        <AnimatePresence mode="wait">
          {error ? (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="col-span-12 h-96 flex flex-col items-center justify-center font-sans"
            >
              <div className="text-[var(--color-error)] mb-4">{t.status.error}</div>
              <button 
                onClick={() => {
                  if (!years || years.length === 0) {
                     fetchInitial();
                  } else {
                     setLoading(true);
                     setError(false);
                     setSelectedYear((prev) => prev); // trigger effect
                  }
                }}
                className="px-6 py-3 border border-[var(--color-error)] text-[var(--color-error)] uppercase tracking-widest text-xs font-bold hover:bg-[var(--color-error)] hover:text-white transition-colors"
                aria-label="Retry"
              >
                {t.status.retry}
              </button>
            </motion.div>
          ) : loading ? (
            <motion.div
              key="loader"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="col-span-12 h-96 flex items-center justify-center font-serif text-2xl text-[var(--color-muted)]"
            >
              {t.status.loading}
            </motion.div>
          ) : (
            <motion.div
              key="content"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.5, ease: "easeOut" }}
              className="col-span-12 grid grid-cols-12 gap-12"
            >
              {/* Left Column: Stats */}
              <div id="sec-overview" className="col-span-12 md:col-span-3 scroll-mt-24">
                <SummaryStats
                  stats={visibleSummaryMetrics.stats}
                  advancedStats={visibleSummaryMetrics.advancedStats}
                  t={{ ...t.summary_stats, ...t.advanced_metrics }}
                />
              </div>

              {/* Right Column: Chart */}
              <div className="col-span-12 md:col-span-9">
                <div className="h-[500px]">
                  <PriceChart
                    data={chartData?.data}
                    t={t.price_chart}
                    overlay={eventOverlay}
                    locale={lang}
                    onWindowDataChange={setVisibleChartData}
                  />
                </div>
              </div>

              <div id="sec-forecast" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <GridForecast
                    apiBase={API_BASE}
                    region={selectedRegion}
                    locale={lang}
                    t={t.forecast}
                  />
                </Suspense>
              </div>

              {/* Lower View: Anomalous Bidding Analytics */}
              <div id="sec-negative" className="col-span-12 mt-16 pt-12 border-t border-[var(--color-border)] scroll-mt-24">
                <div className="flex items-center justify-between mb-8">
                  <h2 className="text-3xl font-serif">{t.hourly_dist.title || 'Negative Price Time Dist.'}</h2>
                  <div className="text-[var(--color-muted)] text-sm tracking-widest uppercase font-bold">{t.advanced_metrics.deepDive}</div>
                </div>

                <div className="grid grid-cols-12 gap-12">
                  <div className="col-span-12 md:col-span-10 md:col-start-2">
                    <Suspense fallback={<SectionFallback minHeight="360px" />}>
                      <HourlyDistributionChart data={chartData?.hourly_distribution} t={t.hourly_dist} />
                    </Suspense>
                  </div>
                </div>
              </div>

              {/* Peak/Trough Arbitrage Analysis */}
              <div id="sec-arbitrage" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <PeakAnalysis
                    year={selectedYear}
                    region={selectedRegion}
                    lang={lang}
                    month={selectedMonth}
                    quarter={selectedQuarter}
                    dayType={selectedDayType}
                    eventOverlay={eventOverlay}
                    apiBase={API_BASE}
                    t={{...t.peak_analysis, loadingMsg: t.loading_states.peak}}
                  />
                </Suspense>
              </div>

              {/* FCAS Revenue Analysis */}
              <div id="sec-fcas" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <FcasAnalysis
                    year={selectedYear}
                    region={selectedRegion}
                    lang={lang}
                    month={selectedMonth}
                    quarter={selectedQuarter}
                    dayType={selectedDayType}
                    eventOverlay={eventOverlay}
                    apiBase={API_BASE}
                    t={{...t.fcas, ...t.peak_analysis, loadingMsg: t.loading_states.fcas}}
                  />
                </Suspense>
              </div>

              {/* BESS P&L Simulator (Waterfall) */}
              <div id="sec-simulator" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <BessSimulator
                  year={selectedYear}
                  region={selectedRegion}
                  apiBase={API_BASE}
                  scopeNote={simulatorScopeNote}
                  t={{...t.simulator, loadingMsg: t.loading_states.simulator}}
                  />
                </Suspense>
              </div>

              {/* Revenue Stacking (Arbitrage + FCAS) */}
              <div id="sec-stacking" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <RevenueStacking
                  year={selectedYear}
                  region={selectedRegion}
                  lang={lang}
                  month={selectedMonth}
                  quarter={selectedQuarter}
                  dayType={selectedDayType}
                  eventOverlay={eventOverlay}
                  apiBase={API_BASE}
                  t={{...t.stacking, ...t.peak_analysis, loadingMsg: t.loading_states.stacking}}
                  />
                </Suspense>
              </div>

              {/* Charging Window Clock Heatmap */}
              <div id="sec-charging" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <ChargingWindow
                  year={selectedYear}
                  region={selectedRegion}
                  lang={lang}
                  eventOverlay={eventOverlay}
                  apiBase={API_BASE}
                  t={{...t.charging, ...t.peak_analysis, loadingMsg: t.loading_states.charging}}
                  />
                </Suspense>
              </div>

              {/* Cycle Cost vs Profitability */}
              <div id="sec-cycle" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <CycleCost
                  year={selectedYear}
                  region={selectedRegion}
                  lang={lang}
                  month={selectedMonth}
                  quarter={selectedQuarter}
                  dayType={selectedDayType}
                  eventOverlay={eventOverlay}
                  apiBase={API_BASE}
                  t={{...t.cycleCost, ...t.peak_analysis, loadingMsg: t.loading_states.cycleCost}}
                  />
                </Suspense>
              </div>

              {/* BESS Investment Analysis */}
              <div id="sec-investment" className="col-span-12 scroll-mt-24">
                <Suspense fallback={<SectionFallback />}>
                  <InvestmentAnalysis
                  year={selectedYear}
                  region={selectedRegion}
                  lang={lang}
                  scopeNote={investmentScopeNote}
                  t={t}
                  />
                </Suspense>
              </div>

            </motion.div>
          )}
        </AnimatePresence>

        {/* CTA "The Next Drop" mimicking a minimalist gallery/product page */}
        <div className="col-span-12 mt-24 border-t border-[var(--color-border)] pt-12 flex justify-between items-center">
          <div className="font-serif italic text-xl text-[var(--color-muted)]">
            {t.cta.message}
          </div>

          <button className="group flex items-center font-sans tracking-widest text-sm uppercase text-[var(--color-primary)] hover:opacity-80 transition-opacity">
            <span className="mr-2 font-bold mb-[2px]">{t.cta.button}</span>
            <ArrowRight size={16} className="transform group-hover:translate-x-1 transition-transform" />
          </button>
        </div>

      </main>
      </div>
      </div>
    </div>
  )
}

export default App;
