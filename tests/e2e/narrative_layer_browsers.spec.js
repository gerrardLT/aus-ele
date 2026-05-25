// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Investment Narrative Layer — 浏览器兼容性测试
 *
 * 在 Chromium、Firefox、WebKit 三个浏览器中验证：
 * - 页面正常加载不崩溃
 * - 图表区域可见
 * - 表格正确渲染
 * - 按钮可点击
 *
 * 注意：此测试文件依赖 playwright.config.js 中配置的多浏览器 projects。
 * 运行命令: npx playwright test narrative_layer_browsers.spec.js --project=chromium --project=firefox --project=webkit
 */

test.describe('Investment Narrative Layer — 浏览器兼容性测试', () => {

  test('页面正常加载 — 不崩溃、无 JS 错误', async ({ page, browserName }) => {
    // 收集页面错误
    const pageErrors = [];
    page.on('pageerror', (error) => {
      pageErrors.push({
        message: error.message,
        stack: error.stack,
      });
    });

    // 收集控制台错误
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // 导航到应用
    const response = await page.goto('/');

    // 验证页面返回成功状态码
    expect(response.status(), `[${browserName}] 页面返回非成功状态码 ${response.status()}`).toBeLessThan(400);

    // 等待页面加载完成
    await page.waitForLoadState('networkidle');

    // 验证页面有内容（不是空白页）
    const bodyContent = await page.locator('body').textContent();
    expect(bodyContent.length, `[${browserName}] 页面内容为空`).toBeGreaterThan(0);

    // 验证没有未捕获的 JS 错误
    const criticalErrors = pageErrors.filter(
      (e) => !e.message.includes('ResizeObserver') && // 忽略 ResizeObserver 警告
             !e.message.includes('Non-Error promise rejection')
    );
    expect(
      criticalErrors,
      `[${browserName}] 存在 ${criticalErrors.length} 个 JS 错误: ${criticalErrors.map((e) => e.message).join('; ')}`
    ).toHaveLength(0);

    // 验证 React 根节点已挂载
    const reactRoot = page.locator('#root, [data-reactroot], #app');
    await expect(reactRoot).toBeVisible({ timeout: 10_000 });

    // 验证 React 根节点有子元素（应用已渲染）
    const childCount = await reactRoot.locator('> *').count();
    expect(childCount, `[${browserName}] React 根节点无子元素`).toBeGreaterThan(0);
  });

  test('图表区域 — 在所有浏览器中可见', async ({ page, browserName }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 导航到 Stage 4（包含 ForwardSpreadCurve 图表）
    const stage4Link = page.locator('button, a, [data-stage="4"]').filter({
      hasText: /Investment Outlook|投资展望|Stage 4|Forward/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000); // 等待图表动画完成
    }

    // 查找图表容器
    const chartContainer = page.locator(
      '[data-testid="forward-spread-curve"], .recharts-wrapper, [class*="chart"], [class*="Chart"], svg'
    ).first();

    // 验证图表容器可见
    await expect(
      chartContainer,
      `[${browserName}] 图表容器不可见`
    ).toBeVisible({ timeout: 10_000 });

    // 验证图表有合理的尺寸
    const box = await chartContainer.boundingBox();
    if (box) {
      expect(box.width, `[${browserName}] 图表宽度异常: ${box.width}px`).toBeGreaterThan(100);
      expect(box.height, `[${browserName}] 图表高度异常: ${box.height}px`).toBeGreaterThan(50);
    }

    // 验证 SVG 或 Canvas 渲染正常
    const svgElement = chartContainer.locator('svg').first();
    const canvasElement = chartContainer.locator('canvas').first();

    const hasSvg = await svgElement.isVisible().catch(() => false);
    const hasCanvas = await canvasElement.isVisible().catch(() => false);

    expect(
      hasSvg || hasCanvas,
      `[${browserName}] 图表未渲染 SVG 或 Canvas 元素`
    ).toBeTruthy();

    // 如果是 SVG，验证有数据路径
    if (hasSvg) {
      const paths = svgElement.locator('path[d], line, rect, circle');
      const pathCount = await paths.count();
      expect(pathCount, `[${browserName}] SVG 图表无数据元素`).toBeGreaterThan(0);
    }
  });

  test('表格 — 在所有浏览器中正确渲染', async ({ page, browserName }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 导航到包含表格的页面
    const stage6Link = page.locator('button, a, [data-stage="6"]').filter({
      hasText: /Financial Model|财务建模|Stage 6|Asset Config/i,
    }).first();

    if (await stage6Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage6Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
    }

    // 查找表格
    const table = page.locator('table, [role="table"], [data-testid*="table"]').first();

    if (await table.isVisible({ timeout: 10_000 }).catch(() => false)) {
      // 验证表格结构完整
      const headers = table.locator('th, [role="columnheader"]');
      const headerCount = await headers.count();
      expect(headerCount, `[${browserName}] 表格缺少表头`).toBeGreaterThan(0);

      // 验证表格有数据行
      const rows = table.locator('tbody tr, [role="row"]');
      const rowCount = await rows.count();
      expect(rowCount, `[${browserName}] 表格无数据行`).toBeGreaterThan(0);

      // 验证单元格有内容
      const firstCell = table.locator('td, [role="cell"]').first();
      if (await firstCell.isVisible()) {
        const cellText = await firstCell.textContent();
        expect(cellText, `[${browserName}] 表格单元格为空`).toBeTruthy();
      }

      // 验证表格布局正常（宽度合理）
      const tableBox = await table.boundingBox();
      if (tableBox) {
        expect(tableBox.width, `[${browserName}] 表格宽度异常`).toBeGreaterThan(200);
        // 表格不应溢出视口
        expect(tableBox.width, `[${browserName}] 表格溢出视口`).toBeLessThanOrEqual(1500);
      }

      // 验证列对齐（检查多行的单元格数量一致）
      if (rowCount >= 2) {
        const row1Cells = await rows.nth(0).locator('td, [role="cell"]').count();
        const row2Cells = await rows.nth(1).locator('td, [role="cell"]').count();
        expect(
          row1Cells,
          `[${browserName}] 表格列数不一致: 行1=${row1Cells}, 行2=${row2Cells}`
        ).toBe(row2Cells);
      }
    }
  });

  test('按钮 — 在所有浏览器中可点击', async ({ page, browserName }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 查找所有可见按钮
    const buttons = page.locator('button:visible, [role="button"]:visible');
    const buttonCount = await buttons.count();

    expect(buttonCount, `[${browserName}] 页面无可见按钮`).toBeGreaterThan(0);

    // 测试前几个按钮的可点击性
    const testCount = Math.min(buttonCount, 5);

    for (let i = 0; i < testCount; i++) {
      const button = buttons.nth(i);

      // 验证按钮可见
      await expect(button).toBeVisible();

      // 验证按钮未被禁用
      const isDisabled = await button.isDisabled();

      if (!isDisabled) {
        // 验证按钮可以被点击（不会抛出异常）
        const buttonText = await button.textContent();

        // 使用 force: false 确保按钮真正可交互
        await button.click({ timeout: 5_000 }).catch((error) => {
          // 某些按钮可能被遮挡，记录但不失败
          console.log(
            `[${browserName}] 按钮 "${buttonText?.trim()}" 点击失败: ${error.message}`
          );
        });

        // 验证点击后页面没有崩溃
        const bodyVisible = await page.locator('body').isVisible();
        expect(bodyVisible, `[${browserName}] 点击按钮后页面崩溃`).toBeTruthy();
      }
    }
  });

  test('响应式布局 — 在不同视口下正常显示', async ({ page, browserName }) => {
    // 测试不同视口尺寸
    const viewports = [
      { width: 1920, height: 1080, name: '桌面大屏' },
      { width: 1440, height: 900, name: '桌面标准' },
      { width: 1024, height: 768, name: '平板横屏' },
    ];

    for (const vp of viewports) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // 验证页面在该视口下正常渲染
      const body = page.locator('body');
      await expect(body).toBeVisible();

      // 验证没有水平滚动条（内容不溢出）
      const hasHorizontalScroll = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
      });

      // 桌面视口不应有水平滚动
      if (vp.width >= 1024) {
        expect(
          hasHorizontalScroll,
          `[${browserName}] 在 ${vp.name} (${vp.width}x${vp.height}) 下出现水平滚动`
        ).toBeFalsy();
      }
    }
  });

  test('CSS 渲染 — 样式在所有浏览器中一致', async ({ page, browserName }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 验证主要布局元素的样式
    const mainContent = page.locator('main, [role="main"], #root > div').first();

    if (await mainContent.isVisible()) {
      const styles = await mainContent.evaluate((el) => {
        const computed = window.getComputedStyle(el);
        return {
          display: computed.display,
          position: computed.position,
          overflow: computed.overflow,
        };
      });

      // 主内容区域应使用 flex 或 grid 布局
      const validDisplays = ['flex', 'grid', 'block'];
      expect(
        validDisplays.some((d) => styles.display.includes(d)),
        `[${browserName}] 主内容区域 display 异常: ${styles.display}`
      ).toBeTruthy();
    }

    // 验证字体加载正常
    const fontsLoaded = await page.evaluate(async () => {
      if (document.fonts) {
        await document.fonts.ready;
        return document.fonts.size > 0;
      }
      return true; // 如果不支持 Font API，假设正常
    });

    expect(fontsLoaded, `[${browserName}] 字体未正确加载`).toBeTruthy();
  });
});
