// web/src/components/OnboardingTour.jsx
// 沉浸式新手导览（2026-08-14 重做）：欢迎页 → 聚光灯逐步高亮真实 UI → 完成页。
// 锚点：[data-tour] 属性（sidebar/stages/filters/ai/bell）；无依赖纯 React 实现。
// 状态持久化 localStorage（aus_tour_v1）；/?tour=1 可强制重新开启。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const TOUR_KEY = 'aus_tour_v1';

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function isTourDone() {
  try { return globalThis.localStorage?.getItem(TOUR_KEY) === 'done'; } catch { return false; }
}

function markTourDone() {
  try { globalThis.localStorage?.setItem(TOUR_KEY, 'done'); } catch { /* ignore */ }
}

function buildSteps(zh) {
  return [
    {
      id: 'welcome',
      target: null,
      title: zh ? '欢迎使用 AEMO Intelligence' : 'Welcome to AEMO Intelligence',
      body: zh
        ? '澳洲 NEM/WEM 储能市场进入与收益判断工作台：市场真相 → 前瞻机会 → 进入结论，每一步数值都可溯源。花 60 秒了解核心动线。'
        : 'Your workbench for Australia NEM/WEM storage market entry & revenue judgment. Every number is traceable. Take 60 seconds to see the core flow.',
    },
    {
      id: 'sidebar',
      target: '[data-tour="sidebar"]',
      title: zh ? '全局导航' : 'Global navigation',
      body: zh
        ? 'NEM / WEM 双市场、天枢 · AI 决策引擎、报告中心、定价与账户都在这里。登录后可在「账户中心」管理成员、API Key 与告警。'
        : 'NEM/WEM markets, Tianshu · Decision Engine, report center, pricing and account live here. After signing in, manage members, API keys and alerts in the Account Center.',
      placement: 'right',
    },
    {
      id: 'stages',
      target: '[data-tour="stages"]',
      title: zh ? '五段分析动线' : 'Five-stage analysis flow',
      body: zh
        ? '从市场真相层出发，经峰值/收益/前瞻判断，落到市场进入结论。点击标签即可切换阶段，每个阶段都有可交互图表。'
        : 'From market truth through peak/revenue/forward views to the market-entry conclusion. Click tabs to switch stages; every stage has interactive charts.',
      placement: 'bottom',
    },
    {
      id: 'filters',
      target: '[data-tour="filters"]',
      title: zh ? '筛选与保存视图' : 'Filters & saved views',
      body: zh
        ? '切换区域、年份、季度与负荷类型，图表即时联动。常用组合可「保存视图」，下次一键恢复。'
        : 'Switch region, year, quarter and day type — charts update live. Save favorite combinations as views and restore them with one click.',
      placement: 'bottom',
    },
    {
      id: 'bell',
      target: '[data-tour="bell"]',
      optional: true,
      title: zh ? '通知中心' : 'Notifications',
      body: zh
        ? '告警触发与订阅报告会在这里通知你。可在「账户中心 → 告警规则」创建价格阈值等规则。'
        : 'Alert triggers and subscribed reports notify you here. Create rules (e.g., price thresholds) under Account Center → Alerts.',
      placement: 'left',
    },
    {
      id: 'finale',
      target: null,
      title: zh ? '准备好了' : 'You are set',
      body: zh
        ? '建议通过侧边栏「天枢 · AI 决策引擎」开始你的第一个问题，或浏览定价页了解套餐。祝分析顺利！'
        : 'Start with your first question via "Tianshu · Decision Engine" in the sidebar, or check the pricing page. Happy analyzing!',
    },
  ];
}

function useTourRect(target, stepIndex) {
  const [rect, setRect] = useState(null);

  useEffect(() => {
    if (!target) { setRect(null); return undefined; }
    let alive = true;
    const update = () => {
      if (!alive) return;
      const el = document.querySelector(target);
      if (!el) { setRect(null); return; }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    // 步骤切换时先滚动到目标，再测量；滚动/缩放时仅重新测量（避免重复滚动循环）
    const el = document.querySelector(target);
    if (el) {
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      setTimeout(update, 220);
    }
    update();
    const onViewport = () => update();
    window.addEventListener('resize', onViewport);
    window.addEventListener('scroll', onViewport, true);
    return () => {
      alive = false;
      window.removeEventListener('resize', onViewport);
      window.removeEventListener('scroll', onViewport, true);
    };
  }, [target, stepIndex]);

  return rect;
}

export default function OnboardingTour({ lang }) {
  const zh = (lang || readLang()) === 'zh';
  const steps = useMemo(() => buildSteps(zh).filter((s) => {
    if (!s.optional) return true;
    return typeof document !== 'undefined' && Boolean(document.querySelector(s.target));
  }), [zh]);

  const [phase, setPhase] = useState(() => {
    const params = new URLSearchParams(globalThis.location.search || '');
    if (params.get('tour') === '1') return 'welcome';
    return isTourDone() ? 'idle' : 'welcome';
  });
  const [index, setIndex] = useState(0);
  const cardRef = useRef(null);

  // ?tour=1：从 URL 移除标记，避免刷新反复弹出
  useEffect(() => {
    const params = new URLSearchParams(globalThis.location.search || '');
    if (params.get('tour') === '1') {
      params.delete('tour');
      const qs = params.toString();
      globalThis.history.replaceState(null, '', qs ? `?${qs}` : globalThis.location.pathname);
    }
  }, []);

  const step = phase === 'tour' ? steps[index] : null;
  const rect = useTourRect(step?.target || null, index);

  // 目标不可见（隐藏/不存在）时自动跳过该步
  useEffect(() => {
    if (phase !== 'tour' || !step?.target) return;
    if (!rect || rect.width === 0) {
      const t = setTimeout(() => {
        setIndex((i) => {
          if (i + 1 >= steps.length) {
            markTourDone();
            setPhase('done');
            return i;
          }
          return i + 1;
        });
      }, 350);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [phase, step, rect, steps.length]);

  const finish = useCallback((done = true) => {
    if (done) markTourDone();
    setPhase('idle');
    setIndex(0);
  }, []);

  const next = useCallback(() => {
    setIndex((i) => {
      if (i + 1 >= steps.length) {
        markTourDone();
        setPhase('done');
        return i;
      }
      return i + 1;
    });
  }, [steps.length]);

  const prev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  // 键盘导航
  useEffect(() => {
    if (phase !== 'tour' && phase !== 'welcome' && phase !== 'done') return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') finish(true);
      if (e.key === 'ArrowRight' || e.key === 'Enter') {
        if (phase === 'welcome') setPhase('tour');
        else if (phase === 'tour') next();
        else finish(true);
      }
      if (e.key === 'ArrowLeft' && phase === 'tour') prev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, next, prev, finish]);

  if (phase === 'idle') return null;

  // ── 欢迎 / 完成：居中卡片 ────────────────────────────────
  if (phase === 'welcome' || phase === 'done') {
    const isWelcome = phase === 'welcome';
    const first = steps[0];
    const last = steps[steps.length - 1];
    const content = isWelcome ? first : last;
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
        <div className="w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center shadow-2xl">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--color-primary)]/15">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {isWelcome
                ? <><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></>
                : <><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><path d="M22 4L12 14.01l-3-3" /></>}
            </svg>
          </div>
          <h2 className="font-serif text-xl text-[var(--color-text)]">{content.title}</h2>
          <p className="mt-3 text-sm leading-relaxed text-[var(--color-muted)]">{content.body}</p>
          {phase === 'done' && (
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <a href="/pricing" className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
                {zh ? '查看定价' : 'View pricing'}
              </a>
              <a href="/help" className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
                {zh ? '帮助中心' : 'Help center'}
              </a>
            </div>
          )}
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => (isWelcome ? setPhase('tour') : finish(true))}
              className="rounded-lg bg-[var(--color-primary)] px-6 py-2.5 text-sm font-semibold text-white hover:opacity-90"
            >
              {isWelcome ? (zh ? '开始 60 秒导览' : 'Start 60s tour') : (zh ? '开始探索' : 'Start exploring')}
            </button>
            <button type="button" onClick={() => finish(true)} className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
              {zh ? '跳过' : 'Skip'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── 聚光灯步骤 ─────────────────────────────────────────
  if (!step) return null;
  const total = steps.length;
  const progress = ((index + 1) / total) * 100;

  // 目标不存在（如铃铛未登录隐藏）→ 跳过该步
  if (step.target && !rect) {
    return null;
  }

  const PAD = 8;
  const spotlight = rect
    ? {
        top: rect.top - PAD,
        left: rect.left - PAD,
        width: rect.width + PAD * 2,
        height: rect.height + PAD * 2,
      }
    : null;

  // 卡片定位：优先按 placement，空间不足时回落
  const cardStyle = {};
  const CARD_W = 340;
  if (spotlight) {
    const vh = window.innerHeight;
    const vw = window.innerWidth;
    const place = step.placement || 'bottom';
    if (place === 'bottom') {
      cardStyle.top = Math.min(spotlight.top + spotlight.height + 14, vh - 230);
      cardStyle.left = Math.max(12, Math.min(spotlight.left, vw - CARD_W - 12));
    } else if (place === 'right') {
      cardStyle.top = Math.max(12, Math.min(spotlight.top, vh - 240));
      cardStyle.left = Math.min(spotlight.left + spotlight.width + 14, vw - CARD_W - 12);
    } else if (place === 'left') {
      cardStyle.top = Math.max(12, Math.min(spotlight.top - 40, vh - 240));
      cardStyle.left = Math.max(12, spotlight.left - CARD_W - 14);
    }
  } else {
    cardStyle.top = '50%';
    cardStyle.left = '50%';
    cardStyle.transform = 'translate(-50%, -50%)';
  }

  return (
    <div className="fixed inset-0 z-[100]">
      {/* 遮罩 + 聚光灯挖空 */}
      {spotlight ? (
        <div
          className="absolute rounded-xl transition-all duration-300 ease-out"
          style={{
            ...spotlight,
            boxShadow: '0 0 0 9999px rgba(4, 8, 16, 0.72)',
            outline: '2px solid var(--color-primary)',
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-[rgba(4,8,16,0.72)]" />
      )}

      {/* 步骤卡片 */}
      <div
        ref={cardRef}
        className="absolute w-[340px] rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-2xl"
        style={cardStyle}
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-primary)]">
            {index + 1} / {total}
          </span>
          <button type="button" onClick={() => finish(true)} className="text-[10px] text-[var(--color-muted)] hover:text-[var(--color-text)]">
            {zh ? '退出导览' : 'Exit'}
          </button>
        </div>
        <h3 className="font-serif text-base text-[var(--color-text)]">{step.title}</h3>
        <p className="mt-2 text-xs leading-relaxed text-[var(--color-muted)]">{step.body}</p>

        {/* 进度条 */}
        <div className="mt-4 h-1 overflow-hidden rounded-full bg-[var(--color-border)]">
          <div className="h-1 rounded-full bg-[var(--color-primary)] transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>

        <div className="mt-4 flex items-center justify-between">
          <button
            type="button"
            onClick={prev}
            disabled={index === 0}
            className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-text)] disabled:opacity-40"
          >
            {zh ? '上一步' : 'Back'}
          </button>
          <div className="flex gap-1">
            {steps.map((s, i) => (
              <span key={s.id} className={`h-1.5 w-1.5 rounded-full ${i === index ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-border)]'}`} />
            ))}
          </div>
          <button
            type="button"
            onClick={next}
            className="rounded-lg bg-[var(--color-primary)] px-4 py-1.5 text-xs font-semibold text-white hover:opacity-90"
          >
            {index + 1 >= total ? (zh ? '完成' : 'Done') : zh ? '下一步' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  );
}
