// web/src/hooks/useRoute.js
// R3.3 订阅当前路由（2026-09-06）。
//
// 用 useSyncExternalStore 而不是 useState + useEffect 订阅：后者在订阅前发生的变更会漏掉
// （挂载与状态变更之间有窗口），表现是「偶发地点了侧边栏没换页」。这是 React 18 给外部
// 状态源的既定答案，没有别的选型空间。
//
// 快照稳定性由 lib/routeStore.js 保证（位置未变时返回同一对象引用）—— 那是这个 hook
// 能用起来的**前提**，不是优化：每帧返回新对象会直接变成无限重渲染。

import { useSyncExternalStore } from 'react';
import { getRouteSnapshot, subscribeRoute } from '../lib/routeStore.js';

export function useRoute() {
  return useSyncExternalStore(subscribeRoute, getRouteSnapshot, getRouteSnapshot);
}
