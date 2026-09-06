// web/src/components/AppChrome.jsx
// R3.3/R3.4/R3.5 的全局外壳（2026-09-06）：移动抽屉 + ⌘K 命令面板。
//
// 挂在路由之外而不是 PageShell 之内，理由很具体：PageShell 只被 MarketPage 使用，
// 而「手机上没有页面导航」这个缺陷（R3.5 要修的原罪）在 /finland、/agent、/account 上
// 同样存在 —— 侧边栏在 ≤1100px 是**整条隐藏**的。放进 PageShell 等于修了三分之一。
//
// 本文件由 main.jsx 以 `lazy(() => import(...))` 引入，且自己再把 CommandPalette
// 也做成 lazy：抽屉是每次都要的（小），面板是按下组合键才要的（大 + 带 OpenAPI 解析）。
// 两层分开才既能让 chrome 立刻可用，又不把面板拖进入口链路。
//
// 每个 flag 关掉时的表现都必须等价于「这个组件不存在」：不注册监听、不渲染 DOM、
// 不发 openapi 请求 —— 见 flagsGuard.test.js 对 offState 的承诺。

import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import MobileNavDrawer from './MobileNavDrawer.jsx';
import { isFlagEnabled } from '../lib/flags.js';
import { getApiBase } from '../lib/apiBase.js';
import { readAppLang } from '../lib/appLang.js';
import { useRoute } from '../hooks/useRoute.js';

const CommandPalette = lazy(() => import('./CommandPalette.jsx'));

/** ⌘K（macOS）/ Ctrl+K（其它）/ Ctrl+Shift+K（部分浏览器占用时的替代）。 */
export function isPaletteHotkey(event) {
  if (!event || event.defaultPrevented) return false;
  if (event.key !== 'k' && event.key !== 'K') return false;
  return Boolean(event.metaKey || event.ctrlKey);
}

export default function AppChrome() {
  const lang = readAppLang();
  const zh = lang === 'zh';
  const route = useRoute();
  const paletteEnabled = isFlagEnabled(import.meta.env, 'commandPalette');
  const drawerEnabled = isFlagEnabled(import.meta.env, 'mobileNavDrawer');
  const [paletteOpen, setPaletteOpen] = useState(false);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  useEffect(() => {
    if (!paletteEnabled) return undefined;
    if (typeof globalThis.addEventListener !== 'function') return undefined;
    const onKeyDown = (event) => {
      if (!isPaletteHotkey(event)) return;
      event.preventDefault();
      setPaletteOpen((current) => !current);
    };
    globalThis.addEventListener('keydown', onKeyDown);
    return () => globalThis.removeEventListener('keydown', onKeyDown);
  }, [paletteEnabled]);

  return (
    <>
      {drawerEnabled && <MobileNavDrawer lang={lang} activePage={route.page} />}

      {/* 桌面端可发现性入口：⌘K 是个隐形功能，没有可见锚点就没人知道它存在。
          放在左下与移动端抽屉按钮同一位置带（两者按断点互斥），不新开一个视觉区域。 */}
      {paletteEnabled && (
        <button
          type="button"
          onClick={openPalette}
          aria-label={zh ? '打开命令面板' : 'Open command palette'}
          aria-keyshortcuts="Meta+K Control+K"
          className="max-[1100px]:hidden fixed bottom-4 left-4 z-40 flex min-h-[36px] items-center gap-2 rounded-full border border-white/12 bg-[#13161A] px-3 text-[11px] text-white/60 shadow-lg hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8AB7FF]"
        >
          <span aria-hidden="true">⌘K</span>
          <span>{zh ? '搜索页面/端点' : 'Search pages/endpoints'}</span>
        </button>
      )}

      {paletteEnabled && (
        <Suspense fallback={null}>
          <CommandPalette
            open={paletteOpen}
            onClose={closePalette}
            lang={lang}
            apiBase={getApiBase()}
          />
        </Suspense>
      )}
    </>
  );
}
