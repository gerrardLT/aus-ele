import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowRight, Activity, Database } from 'lucide-react';
import PriceChart from './components/PriceChart';
import SummaryStats from './components/SummaryStats';
import HourlyDistributionChart from './components/HourlyDistributionChart';
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

  const t = translations[lang];

  // Initial Fetch Setup
  useEffect(() => {
    async function fetchInitial() {
      try {
        const [yearsRes, summaryRes] = await Promise.all([
          fetch(`${API_BASE}/years`),
          fetch(`${API_BASE}/summary`)
        ]);
        const yearsData = await yearsRes.json();
        const sumData = await summaryRes.json();

        if (yearsData.years?.length > 0) {
          setYears(yearsData.years);
          setSelectedYear(yearsData.years[0]);
        }
        if (sumData.tables) {
          setSummaryData(sumData.tables);
        }
      } catch (err) {
        console.error("Failed to fetch initial data", err);
      }
    }
    fetchInitial();
  }, []);

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
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [selectedYear, selectedMonth, selectedQuarter, selectedDayType, selectedRegion]);

  return (
    <div className="min-h-screen pb-20">
      {/* 极简无边框导航 Minimal Text-based Nav */}
      <nav className="w-full border-b border-[var(--color-border)] py-6 mb-12">
        <div className="grid-container flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Activity size={20} />
            <span className="font-serif font-semibold text-lg hover:italic transition-all cursor-default">
              {t.nav.brand}
            </span>
          </div>
          <div className="flex items-center space-x-6 text-sm font-sans tracking-wide text-[var(--color-muted)]">
            <span className="hidden md:inline">{t.nav.subtitle}</span>
            <button
              onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
              className="px-3 py-1 border border-[var(--color-border)] rounded hover:bg-black hover:text-white transition-colors"
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
          className="col-span-12 md:col-span-8 mb-16"
        >
          <h1 className="text-5xl md:text-7xl leading-tight mb-6">
            {t.header.title1} <br />{t.header.title2}
          </h1>
          <p className="text-[var(--color-muted)] font-sans max-w-xl text-lg leading-relaxed">
            {t.header.description}
          </p>
        </motion.header>

        {/* Filters Panel (Black/White minimal controls) */}
        <div className="col-span-12 border-t border-[var(--color-border)] pt-8 mb-12 flex flex-col gap-8">

          {/* Top row: Year & Region */}
          <div className="flex flex-col md:flex-row justify-between gap-8 md:gap-4">

            <div className="flex flex-col gap-3">
              <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.yearSelect}</span>
              <div className="flex flex-wrap gap-2">
                {years.map(y => (
                  <button
                    key={y}
                    onClick={() => setSelectedYear(y)}
                    className={`px-4 py-2 font-sans text-sm transition-colors
                      ${selectedYear === y
                        ? 'bg-black text-white'
                        : 'bg-transparent text-[var(--color-text)] hover:bg-gray-100'
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
                {['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1'].map(r => (
                  <button
                    key={r}
                    onClick={() => setSelectedRegion(r)}
                    className={`px-4 py-2 font-sans text-sm transition-colors border-b-2
                      ${selectedRegion === r
                        ? 'border-black text-black font-medium'
                        : 'border-transparent text-[var(--color-muted)] hover:text-black hover:border-black/30'
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
                    className={`px-4 py-1.5 font-sans text-sm transition-colors rounded-full border
                      ${selectedQuarter === q
                        ? 'bg-black text-white border-black'
                        : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-black'
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
                    className={`px-4 py-1.5 font-sans text-sm transition-colors rounded-full border
                      ${selectedDayType === d
                        ? 'bg-black text-white border-black'
                        : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-black'
                      }`}
                  >
                    {d === 'ALL' ? t.filters.allDays : t.filters[d.toLowerCase()]}
                  </button>
                ))}
              </div>
            </div>

          </div>

          {/* Bottom row: Month */}
          <div className="flex flex-col gap-3 border-t border-dashed border-[var(--color-border)] pt-6">
            <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{t.filters.monthSelect}</span>
            <div className="flex flex-wrap gap-2">
              {['ALL', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'].map(m => (
                <button
                  key={m}
                  onClick={() => { setSelectedMonth(m); if (m !== 'ALL') setSelectedQuarter('ALL'); }}
                  className={`px-4 py-1.5 font-sans text-sm transition-colors rounded-full border
                    ${selectedMonth === m
                      ? 'bg-black text-white border-black'
                      : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-black'
                    }`}
                >
                  {m === 'ALL' ? t.filters.allMonths : m}
                </button>
              ))}
            </div>
          </div>

        </div>

        {/* Data Presentation Area */}
        <AnimatePresence mode="wait">
          {loading ? (
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
              <div className="col-span-12 md:col-span-3">
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
              <div className="col-span-12 mt-16 pt-12 border-t border-[var(--color-border)]">
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
