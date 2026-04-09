import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowRight, Activity, Database, ChevronUp, List } from 'lucide-react';
import PriceChart from './components/PriceChart';
import SummaryStats from './components/SummaryStats';
import HourlyDistributionChart from './components/HourlyDistributionChart';
import PeakAnalysis from './components/PeakAnalysis';
import FcasAnalysis from './components/FcasAnalysis';
import BessSimulator from './components/BessSimulator';
import RevenueStacking from './components/RevenueStacking';
import ChargingWindow from './components/ChargingWindow';
import CycleCost from './components/CycleCost';
import InvestmentAnalysis from './components/InvestmentAnalysis';
import { translations } from './translations';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8085/api';

"use client";

function App() {
  const [lang, setLang] = useState('zh');
  const [years, setYears] = useState([]);
  const [selectedYear, setSelectedYear] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState('ALL');
  const [selectedQuarter, setSelectedQuarter] = useState('ALL');
  const [selectedDayType, setSelectedDayType] = useState('ALL');
  const [selectedRegion, setSelectedRegion] = useState('NSW1');
  const [chartData, setChartData] = useState(null);
  const [summaryData, setSummaryData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [showToc, setShowToc] = useState(false);
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [showMonthFilter, setShowMonthFilter] = useState(false);
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
    const sectionIds = ['sec-overview', 'sec-negative', 'sec-arbitrage', 'sec-fcas', 'sec-simulator', 'sec-stacking', 'sec-charging', 'sec-cycle', 'sec-investment'];

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

  // Initial Fetch Setup
  const fetchInitial = async () => {
    try {
      setError(false);
      setLoading(true);
      const [yearsRes, summaryRes] = await Promise.all([
        fetch(`${API_BASE}/years`),
        fetch(`${API_BASE}/summary`)
      ]);
      const yearsData = await yearsRes.json();
      const sumData = await summaryRes.json();

      if (yearsData.years?.length > 0) {
        setYears(yearsData.years);
        setSelectedYear(yearsData.years[0]);
      } else {
        setLoading(false);
      }
      if (sumData.tables) {
        setSummaryData(sumData.tables);
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

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      const res = await fetch(`${API_BASE}/sync_data`, { method: 'POST' });
      if (res.ok) {
         // Simple alert for now as per requirement
         alert(lang === 'zh' ? '✅ 数据同步已在后台启动！爬取过程可能需要几分钟的时间。' : '✅ Data sync started in background! This may take a few minutes.');
      } else {
         alert('❌ Update failed. Please check server logs.');
      }
    } catch(e) {
      console.error(e);
      alert('❌ Error triggering update.');
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

    fetch(url)
      .then(res => res.json())
      .then(data => {
        setChartData(data);
        setError(false);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setError(true);
        setLoading(false);
      });
  }, [selectedYear, selectedMonth, selectedQuarter, selectedDayType, selectedRegion]);

    const tocSections = [
      { id: 'sec-overview', label: lang === 'zh' ? '市场总览' : 'Overview', shortLabel: '总览' },
      { id: 'sec-negative', label: lang === 'zh' ? '负电价分布' : 'Negative Price', shortLabel: '负电价' },
      { id: 'sec-arbitrage', label: lang === 'zh' ? '储能套利' : 'Arbitrage', shortLabel: '套利' },
      { id: 'sec-fcas', label: lang === 'zh' ? 'FCAS 分析' : 'FCAS', shortLabel: 'FCAS' },
      { id: 'sec-simulator', label: lang === 'zh' ? '盈利模拟' : 'Simulator', shortLabel: '模拟' },
      { id: 'sec-stacking', label: lang === 'zh' ? '收入叠加' : 'Stacking', shortLabel: '叠加' },
      { id: 'sec-charging', label: lang === 'zh' ? '充电窗口' : 'Charging', shortLabel: '充电' },
      { id: 'sec-cycle', label: lang === 'zh' ? '循环成本' : 'Cycle Cost', shortLabel: '循环' },
      { id: 'sec-investment', label: lang === 'zh' ? '投资分析' : 'Investment', shortLabel: '投资' },
    ];

    return (
    <div className="min-h-screen pb-20">

      {/* Floating TOC Toggle Button — shrinks when panel is open */}
      {!loading && !error && (
        <motion.button
          onClick={() => setShowToc(prev => !prev)}
          animate={showToc
            ? { width: 28, height: 28, left: 8, top: 'calc(50% - 160px)' }
            : { width: 40, height: 40, left: 16, top: '50%' }
          }
          transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
          className="fixed -translate-y-1/2 z-[51] flex items-center justify-center bg-[var(--color-inverted)] text-[var(--color-inverted-text)] rounded-full shadow-lg"
          aria-label="Toggle navigation"
          title={lang === 'zh' ? '模块导航' : 'Section Navigation'}
        >
          {showToc ? <ChevronUp size={14} className="rotate-[-90deg]" /> : <List size={18} />}
        </motion.button>
      )}

      {/* Compact TOC Panel — flush left edge */}
      <AnimatePresence>
        {showToc && (
          <motion.nav
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
            className="fixed left-2 top-1/2 -translate-y-1/2 z-50 backdrop-blur-lg bg-[#2a2a2a]/60 rounded-xl shadow-2xl py-2.5 px-1.5"
          >
            {tocSections.map(sec => (
              <button
                key={sec.id}
                onClick={() => { scrollToSection(sec.id); setShowToc(false); }}
                className={`flex items-center gap-2.5 w-full text-left px-3 py-[7px] text-[13px] font-sans transition-all rounded-lg whitespace-nowrap
                  ${activeSection === sec.id
                    ? 'text-white font-semibold'
                    : 'text-white/60 hover:text-white/90'
                  }`}
              >
                <span className={`flex-shrink-0 rounded-full transition-all duration-200 ${
                  activeSection === sec.id
                    ? 'w-1.5 h-1.5 bg-white'
                    : 'w-1 h-1 bg-white/30'
                }`} />
                {sec.shortLabel || sec.label}
              </button>
            ))}
          </motion.nav>
        )}
      </AnimatePresence>

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
      {/* Sticky Compact Filter Bar — appears when main filters scroll out of view */}
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
                  {lang === 'zh' ? '年份' : 'YEAR'}
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
                  {lang === 'zh' ? '区域' : 'REGION'}
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

      {/* 极简无边框导航 Minimal Text-based Nav */}
      <nav className="w-full border-b border-[var(--color-border)] py-3 mb-8">
        <div className="grid-container flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Activity size={20} />
            <span className="font-serif font-semibold text-lg hover:italic transition-all cursor-default">
              {t.nav.brand}
            </span>
          </div>
          <div className="flex items-center space-x-6 text-sm font-sans tracking-wide text-[var(--color-muted)]">
            <span className="hidden md:inline">{t.nav.subtitle}</span>
            {lastUpdate && <span className="hidden lg:inline text-xs border border-[var(--color-border)] rounded-full px-3 py-1 bg-[var(--color-bg)]">{lastUpdate}</span>}
            <button
               onClick={handleSync}
               disabled={isSyncing}
               title="Trigger Background Data Sync"
               className="flex items-center gap-2 px-3 py-1.5 border border-[var(--color-border)] rounded hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)] transition-colors min-h-[44px]"
            >
               <svg className={isSyncing ? "animate-spin w-4 h-4" : "w-4 h-4"} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
               </svg>
               <span className="hidden sm:inline">{lang === 'zh' ? (isSyncing ? '同步中' : '同步数据') : (isSyncing ? 'Syncing' : 'Sync')}</span>
            </button>
            <button
              aria-label="Toggle language"
              title="Toggle language"
              onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
              className="px-3 py-1.5 border border-[var(--color-border)] rounded hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)] transition-colors min-h-[44px]"
            >
              {t.nav.toggleOptions}
            </button>
          </div>
        </div>
      </nav>

      <main className="grid-container">

        {/* Header / Typography Focus */}
        <motion.header
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="col-span-12 md:col-span-12 mb-6 flex flex-col md:flex-row md:items-end justify-between items-start gap-4"
        >
          <h1 className="text-2xl md:text-3xl font-bold leading-tight">
            {t.header.title1} {t.header.title2}
          </h1>
          <p className="text-[var(--color-text)]/60 font-sans max-w-2xl text-base leading-relaxed mb-1">
            {t.header.description}
          </p>
        </motion.header>

        {/* Filters Panel (Black/White minimal controls) */}
        <div ref={filterPanelRef} className="col-span-12 border-t border-[var(--color-border)] pt-4 mb-6 flex flex-col gap-6">

          {/* Top row: Year & Region */}
          <div className="flex flex-col md:flex-row justify-between gap-8 md:gap-4">

            <div className="flex flex-col gap-3">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.yearSelect}</span>
              <div className="flex flex-wrap gap-2">
                {years.map(y => (
                  <button
                    key={y}
                    onClick={() => setSelectedYear(y)}
                    className={`px-4 py-1.5 min-h-[36px] font-sans text-sm transition-colors
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

            <div className="flex flex-col gap-3 md:items-end w-full md:w-auto">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.regionSelect}</span>
              <div className="flex flex-wrap gap-2 md:justify-end">
                {['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1', 'WEM'].map(r => (
                  <button
                    key={r}
                    onClick={() => setSelectedRegion(r)}
                    className={`px-4 py-1.5 min-h-[36px] font-sans text-sm transition-colors border-b-2
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
          <div className="flex flex-col md:flex-row justify-between gap-8 md:gap-4 border-t border-dashed border-[var(--color-border)] pt-6">

            <div className="flex flex-col gap-3">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.quarterSelect}</span>
              <div className="flex flex-wrap gap-2">
                {['ALL', 'Q1', 'Q2', 'Q3', 'Q4'].map(q => (
                  <button
                    key={q}
                    onClick={() => { setSelectedQuarter(q); if (q !== 'ALL') setSelectedMonth('ALL'); }}
                    className={`px-5 py-2 min-h-[44px] font-sans text-sm transition-colors rounded-full border
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

            <div className="flex flex-col gap-3 md:items-end w-full md:w-auto">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.dayTypeSelect}</span>
              <div className="flex flex-wrap gap-2 md:justify-end">
                {['ALL', 'WEEKDAY', 'WEEKEND'].map(d => (
                  <button
                    key={d}
                    onClick={() => setSelectedDayType(d)}
                    className={`px-5 py-2 min-h-[44px] font-sans text-sm transition-colors rounded-full border
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
          <div className="flex flex-col gap-3 border-t border-dashed border-[var(--color-border)] pt-6">
            <div className="flex items-center justify-between">
              <button
                onClick={() => setShowMonthFilter(prev => !prev)}
                className="flex items-center gap-2 text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase hover:text-[var(--color-text)] transition-colors"
              >
                {t.filters.monthSelect}
                <span className={`transition-transform duration-200 ${showMonthFilter ? 'rotate-90' : ''}`}>▶</span>
                {selectedMonth !== 'ALL' && (
                  <span className="ml-1 px-2 py-0.5 bg-[var(--color-inverted)] text-[var(--color-inverted-text)] rounded-full text-[10px] font-medium normal-case">
                    {lang === 'zh' ? `${parseInt(selectedMonth)}月` : `M${selectedMonth}`}
                  </span>
                )}
              </button>
              {/* Reset All Filters */}
              {(selectedMonth !== 'ALL' || selectedQuarter !== 'ALL' || selectedDayType !== 'ALL') && (
                <button
                  onClick={() => { setSelectedMonth('ALL'); setSelectedQuarter('ALL'); setSelectedDayType('ALL'); }}
                  className="text-xs font-sans text-[var(--color-muted)] hover:text-[var(--color-error)] transition-colors underline underline-offset-2"
                >
                  {lang === 'zh' ? '重置筛选' : 'Reset Filters'}
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
                    {['ALL', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'].map(m => {
                      const monthLabels = lang === 'zh'
                        ? ['全年综合', '1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
                        : ['All', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                      const idx = m === 'ALL' ? 0 : parseInt(m);
                      return (
                        <button
                          key={m}
                          onClick={() => { setSelectedMonth(m); if (m !== 'ALL') setSelectedQuarter('ALL'); }}
                          className={`px-4 py-2 min-h-[40px] font-sans text-sm transition-colors rounded-full border
                            ${selectedMonth === m
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
                  stats={chartData?.stats}
                  advancedStats={chartData?.advanced_stats}
                  t={{ ...t.summary_stats, ...t.advanced_metrics }}
                />
              </div>

              {/* Right Column: Chart */}
              <div className="col-span-12 md:col-span-9 h-[500px]">
                <PriceChart data={chartData?.data} t={t.price_chart} />
              </div>

              {/* Lower View: Anomalous Bidding Analytics */}
              <div id="sec-negative" className="col-span-12 mt-16 pt-12 border-t border-[var(--color-border)] scroll-mt-24">
                <div className="flex items-center justify-between mb-8">
                  <h2 className="text-3xl font-serif">{t.hourly_dist.title || 'Negative Price Time Dist.'}</h2>
                  <div className="text-[var(--color-muted)] text-sm tracking-widest uppercase font-bold">{t.advanced_metrics.deepDive}</div>
                </div>

                <div className="grid grid-cols-12 gap-12">
                  <div className="col-span-12 md:col-span-10 md:col-start-2">
                    <HourlyDistributionChart data={chartData?.hourly_distribution} t={t.hourly_dist} />
                  </div>
                </div>
              </div>

              {/* Peak/Trough Arbitrage Analysis */}
              <div id="sec-arbitrage" className="col-span-12 scroll-mt-24">
                <PeakAnalysis
                  year={selectedYear}
                  region={selectedRegion}
                  apiBase={API_BASE}
                  t={{...t.peak_analysis, loadingMsg: t.loading_states.peak}}
                />
              </div>

              {/* FCAS Revenue Analysis */}
              <div id="sec-fcas" className="col-span-12 scroll-mt-24">
                <FcasAnalysis
                  year={selectedYear}
                  region={selectedRegion}
                  apiBase={API_BASE}
                  t={{...t.fcas, ...t.peak_analysis, loadingMsg: t.loading_states.fcas}}
                />
              </div>

              {/* BESS P&L Simulator (Waterfall) */}
              <div id="sec-simulator" className="col-span-12 scroll-mt-24">
                <BessSimulator
                  year={selectedYear}
                  region={selectedRegion}
                  apiBase={API_BASE}
                  t={{...t.simulator, loadingMsg: t.loading_states.simulator}}
                />
              </div>

              {/* Revenue Stacking (Arbitrage + FCAS) */}
              <div id="sec-stacking" className="col-span-12 scroll-mt-24">
                <RevenueStacking
                  year={selectedYear}
                  region={selectedRegion}
                  apiBase={API_BASE}
                  t={{...t.stacking, ...t.peak_analysis, loadingMsg: t.loading_states.stacking}}
                />
              </div>

              {/* Charging Window Clock Heatmap */}
              <div id="sec-charging" className="col-span-12 scroll-mt-24">
                <ChargingWindow
                  year={selectedYear}
                  region={selectedRegion}
                  apiBase={API_BASE}
                  t={{...t.charging, ...t.peak_analysis, loadingMsg: t.loading_states.charging}}
                />
              </div>

              {/* Cycle Cost vs Profitability */}
              <div id="sec-cycle" className="col-span-12 scroll-mt-24">
                <CycleCost
                  year={selectedYear}
                  region={selectedRegion}
                  apiBase={API_BASE}
                  t={{...t.cycleCost, ...t.peak_analysis, loadingMsg: t.loading_states.cycleCost}}
                />
              </div>

              {/* BESS Investment Analysis */}
              <div id="sec-investment" className="col-span-12 scroll-mt-24">
                <InvestmentAnalysis
                  year={selectedYear}
                  region={selectedRegion}
                  t={t}
                />
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
  )
}

export default App;
