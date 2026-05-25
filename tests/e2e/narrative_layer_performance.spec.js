// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Investment Narrative Layer — 性能测试
 *
 * 测试指标：
 * - API 响应时间 < 2 秒
 * - 页面首次内容绘制 (FCP) < 3 秒
 * - Stage 4 图表渲染完成 < 5 秒
 * - Stage 6 表格渲染完成 < 3 秒
 * - 20 年数据量下无明显卡顿
 */

test.describe('Investment Narrative Layer — 性能测试', () => {

  test('API 响应时间 — narrative 端点应在 2 秒内响应', async ({ page }) => {
    // 收集所有 API 响应时间（通过请求开始和响应结束的时间差）
    const apiTimings = [];
    const requestStartTimes = new Map();

    page.on('request', (request) => {
      if (request.url().includes('/api/')) {
        requestStartTimes.set(request.url(), Date.now());
      }
    });

    page.on('response', (response) => {
      if (response.url().includes('/api/')) {
        const startTime = requestStartTimes.get(response.url());
        if (startTime) {
          apiTimings.push({
            url: response.url(),
            duration: Date.now() - startTime,
          });
        }
      }
    });

    // 导航到应用
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 导航到 Stage 4 触发 narrative 相关 API
    const stage4Link = page.locator('button, a, [data-stage="4"]').filter({
      hasText: /Investment Outlook|投资展望|Stage 4|Forward/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
    }

    // 使用 Performance API 测量 API 调用时间
    const resourceTimings = await page.evaluate(() => {
      const entries = performance.getEntriesByType('resource');
      return entries
        .filter((entry) => entry.name.includes('/api/'))
        .map((entry) => ({
          name: entry.name,
          duration: entry.duration,
          startTime: entry.startTime,
        }));
    });

    // 验证所有 API 调用在 2 秒内完成
    for (const timing of resourceTimings) {
      expect(
        timing.duration,
        `API ${timing.name} 响应时间 ${timing.duration}ms 超过 2000ms 阈值`
      ).toBeLessThan(2000);
    }
  });

  test('首次内容绘制 (FCP) — 应在 3 秒内完成', async ({ page }) => {
    // 导航到应用并测量 FCP
    await page.goto('/');

    // 等待页面加载完成
    await page.waitForLoadState('domcontentloaded');

    // 获取 FCP 指标
    const fcp = await page.evaluate(() => {
      return new Promise((resolve) => {
        // 使用 PerformanceObserver 获取 FCP
        const observer = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const fcpEntry = entries.find((entry) => entry.name === 'first-contentful-paint');
          if (fcpEntry) {
            observer.disconnect();
            resolve(fcpEntry.startTime);
          }
        });
        observer.observe({ type: 'paint', buffered: true });

        // 超时回退：直接从 performance entries 获取
        setTimeout(() => {
          const entries = performance.getEntriesByName('first-contentful-paint');
          if (entries.length > 0) {
            resolve(entries[0].startTime);
          } else {
            // 如果没有 FCP 数据，使用 DOM 加载时间作为近似值
            const navEntries = performance.getEntriesByType('navigation');
            if (navEntries.length > 0) {
              resolve(navEntries[0].domContentLoadedEventEnd);
            } else {
              resolve(0);
            }
          }
          observer.disconnect();
        }, 5000);
      });
    });

    // FCP 应在 3 秒内
    expect(fcp, `FCP 时间 ${fcp}ms 超过 3000ms 阈值`).toBeLessThan(3000);
  });

  test('Stage 4 图表渲染 — 应在 5 秒内完成', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 记录开始时间
    const startTime = Date.now();

    // 导航到 Stage 4
    const stage4Link = page.locator('button, a, [data-stage="4"]').filter({
      hasText: /Investment Outlook|投资展望|Stage 4|Forward/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
    }

    // 等待图表元素出现（SVG path 或 canvas）
    const chartElement = page.locator(
      '[data-testid="forward-spread-curve"] svg path[d], .recharts-line path, .recharts-area path, svg path[d*="C"], canvas'
    ).first();

    await expect(chartElement).toBeVisible({ timeout: 5_000 });

    // 计算渲染时间
    const renderTime = Date.now() - startTime;

    // 图表渲染应在 5 秒内完成
    expect(renderTime, `Stage 4 图表渲染时间 ${renderTime}ms 超过 5000ms 阈值`).toBeLessThan(5000);
  });

  test('Stage 6 表格渲染 — 应在 3 秒内完成', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 记录开始时间
    const startTime = Date.now();

    // 导航到 Stage 6
    const stage6Link = page.locator('button, a, [data-stage="6"]').filter({
      hasText: /Financial Model|财务建模|Stage 6|Asset Config/i,
    }).first();

    if (await stage6Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage6Link.click();
    }

    // 等待表格渲染完成
    const table = page.locator('table, [data-testid="cross-validation-table"]').first();
    await expect(table).toBeVisible({ timeout: 3_000 });

    // 验证表格有数据行
    const rows = table.locator('tbody tr, tr');
    await expect(rows.first()).toBeVisible({ timeout: 3_000 });

    // 计算渲染时间
    const renderTime = Date.now() - startTime;

    // 表格渲染应在 3 秒内完成
    expect(renderTime, `Stage 6 表格渲染时间 ${renderTime}ms 超过 3000ms 阈值`).toBeLessThan(3000);
  });

  test('20 年数据量 — 无明显卡顿（Long Task 检测）', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 注入 Long Task 观察器（检测超过 50ms 的任务）
    await page.evaluate(() => {
      window.__longTasks = [];
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__longTasks.push({
            duration: entry.duration,
            startTime: entry.startTime,
            name: entry.name,
          });
        }
      });
      observer.observe({ type: 'longtask', buffered: true });
    });

    // 导航到 Stage 4（包含 20 年前瞻数据）
    const stage4Link = page.locator('button, a, [data-stage="4"]').filter({
      hasText: /Investment Outlook|投资展望|Stage 4|Forward/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
    }

    // 等待数据加载和渲染完成
    await page.waitForTimeout(3000);

    // 收集 Long Task 数据
    const longTasks = await page.evaluate(() => window.__longTasks || []);

    // 验证没有超过 500ms 的严重卡顿任务
    const severeTasks = longTasks.filter((task) => task.duration > 500);
    expect(
      severeTasks.length,
      `检测到 ${severeTasks.length} 个超过 500ms 的严重卡顿任务: ${JSON.stringify(severeTasks)}`
    ).toBe(0);

    // 验证 Long Task 总时间不超过 2 秒
    const totalBlockingTime = longTasks.reduce((sum, task) => sum + (task.duration - 50), 0);
    expect(
      totalBlockingTime,
      `总阻塞时间 ${totalBlockingTime}ms 超过 2000ms 阈值`
    ).toBeLessThan(2000);
  });

  test('页面导航性能 — Navigation Timing 指标', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('load');

    // 获取 Navigation Timing 数据
    const navTiming = await page.evaluate(() => {
      const entries = performance.getEntriesByType('navigation');
      if (entries.length > 0) {
        const nav = entries[0];
        return {
          // DNS 查询时间
          dnsLookup: nav.domainLookupEnd - nav.domainLookupStart,
          // TCP 连接时间
          tcpConnect: nav.connectEnd - nav.connectStart,
          // 请求响应时间
          ttfb: nav.responseStart - nav.requestStart,
          // DOM 解析时间
          domParsing: nav.domInteractive - nav.responseEnd,
          // DOM 内容加载
          domContentLoaded: nav.domContentLoadedEventEnd - nav.startTime,
          // 页面完全加载
          loadComplete: nav.loadEventEnd - nav.startTime,
        };
      }
      return null;
    });

    if (navTiming) {
      // TTFB 应在 500ms 内（本地开发服务器）
      expect(navTiming.ttfb, `TTFB ${navTiming.ttfb}ms 超过 500ms`).toBeLessThan(500);

      // DOM Content Loaded 应在 3 秒内
      expect(
        navTiming.domContentLoaded,
        `DOMContentLoaded ${navTiming.domContentLoaded}ms 超过 3000ms`
      ).toBeLessThan(3000);

      // 页面完全加载应在 5 秒内
      if (navTiming.loadComplete > 0) {
        expect(
          navTiming.loadComplete,
          `页面完全加载 ${navTiming.loadComplete}ms 超过 5000ms`
        ).toBeLessThan(5000);
      }
    }
  });
});
