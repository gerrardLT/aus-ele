// web/src/components/MobileNavDrawer.jsx
// R3.5 移动端导航抽屉（2026-09-06）。
//
// 背景：侧边栏在 ≤1100px 直接 `max-[1100px]:hidden` 整条藏掉，手机上**没有任何页面导航**
// —— 只能靠浏览器地址栏。这里补一个抽屉。
//
// 两条刻意的不做：
// 1. **不动 SidebarNavigation 的断点**。finlandBoard.test.js:698-702 那组断言锁的是
//    触控尺寸与 focus-visible，改断点会带一批静默视觉回归；本组件按同样的规格自己写。
// 2. **不做动画库**。抽屉每天被打开的次数远少于页面被加载的次数，为它多背一份 motion
//    进主包不划算（本仓入口预算只剩 6%）。CSS transition 足够。
//
// 可达性三件套不是装饰：抽屉是覆盖全页的，读屏用户需要 role/aria-modal/aria-label；
// 键盘用户需要 Esc 能关、焦点能进得去出得来；触屏用户需要 44px 命中区。

import { useCallback, useEffect, useRef, useState } from 'react';
import { navItems, interceptNavClick } from './SidebarNavigation.jsx';
import { resolveRootPage } from '../lib/pageRouter.js';

export default function MobileNavDrawer({ lang = 'zh', activePage = null }) {
  const zh = lang === 'zh';
  const [open, setOpen] = useState(false);
  const panelRef = useRef(null);
  const triggerRef = useRef(null);

  const close = useCallback(() => {
    setOpen(false);
    // 焦点交还触发按钮：不还给的话键盘用户的下一次 Tab 会从文档开头重来。
    try { triggerRef.current?.focus?.(); } catch { /* 节点可能已卸载 */ }
  }, []);

  // Esc 关闭 + Tab 圈在抽屉内（简化版焦点陷阱：只处理首尾两个边界）。
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      const nodes = panelRef.current?.querySelectorAll?.('a[href], button:not([disabled])');
      if (!nodes || !nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, close]);

  // 换页后自动收起：抽屉盖在半页上不是用户想要的状态。
  useEffect(() => {
    if (open) setOpen(false);
    // 只在 activePage 变化时收，open 变化不该触发自己关闭
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePage]);

  const items = navItems(lang);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-label={zh ? '打开导航菜单' : 'Open navigation menu'}
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
        className="min-[1100px]:hidden fixed bottom-4 left-4 z-40 flex min-h-[44px] min-w-[44px] items-center justify-center gap-2 rounded-full border border-white/12 bg-[#13161A] px-4 text-xs font-medium text-white/80 shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8AB7FF]"
      >
        <span aria-hidden="true">☰</span>
        <span>{zh ? '菜单' : 'Menu'}</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 min-[1100px]:hidden" role="dialog" aria-modal="true" aria-label={zh ? '页面导航' : 'Page navigation'}>
          <button
            type="button"
            aria-label={zh ? '关闭导航菜单' : 'Close navigation menu'}
            onClick={close}
            className="absolute inset-0 h-full w-full cursor-default bg-black/55"
          />
          <nav
            id="mobile-nav-drawer"
            ref={panelRef}
            className="absolute inset-y-0 left-0 flex w-[78%] max-w-[320px] flex-col gap-1 overflow-y-auto bg-[#13161A] px-4 py-5 text-[#F3F5F7]"
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/60">
                {zh ? '导航' : 'NAVIGATION'}
              </span>
              <button
                type="button"
                onClick={close}
                aria-label={zh ? '关闭' : 'Close'}
                className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-white/60 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8AB7FF]"
              >
                ✕
              </button>
            </div>
            {items.map((item) => (
              <a
                key={`${item.id}-${item.path}`}
                href={item.path}
                onClick={(event) => {
                  interceptNavClick(event, item.path);
                  // 交给浏览器时不收：整页跳转前收一下没意义，跳转失败时留着抽屉更不奇怪
                  if (resolvesToNewPage(item.path, activePage)) setOpen(false);
                }}
                className={`flex min-h-[44px] items-center rounded-lg px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8AB7FF] ${
                  activePage === item.id ? 'bg-white/10 font-medium text-white' : 'text-white/70 hover:bg-white/5'
                }`}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>
      )}
    </>
  );
}

/** 这条链接会不会真的换页（换页才收起抽屉，同页交回浏览器）。 */
function resolvesToNewPage(href, activePage) {
  return resolveRootPage(String(href || '/').split('?')[0]) !== activePage;
}
