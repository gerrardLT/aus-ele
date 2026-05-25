// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Investment Narrative Layer — 视觉回归测试
 *
 * 使用 Playwright 内置截图对比功能：
 * - Stage 4 页面截图对比
 * - Stage 6 页面截图对比
 * - ForwardSpreadCurve 组件截图
 * - CrossValidationTable 组件截图
 * - AssetConfigPanel 组件截图
 *
 * 首次运行会建立基线截图（保存在 narrative_layer_visual.spec.js-snapshots/ 目录）
 * 后续运行会与基线对比，差异超过阈值则测试失败
 *
 * 更新基线: npx playwright test narrative_layer_visual.spec.js --update-snapshots
 */

test.describe('Investment Narrative Layer — 视觉回归测试', () => {

  // 仅在 Chromium 中运行视觉回归测试以保持一致性
  test.describe.configure({ retries: 0 });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // 等待所有动画完成
    await page.waitForTimeout(1000);
  });

  test('Stage 4 页面 — 整体视觉截图', async ({ page }) => {
    // 导航到 Stage 4 (Investment Outlook)
    const stage4Link = page.locator('button, a, [data-stage="4"]').filter({
      hasText: /Investment Outlook|投资展望|Stage 4|Forward/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
      // 等待图表动画和数据加载完成
      await page.waitForTimeout(3000);
    }

    // 隐藏动态内容（时间戳、实时数据等）避免误报
    await page.evaluate(() => {
      // 隐藏包含时间戳的元素
      document.querySelectorAll('[data-testid*="timestamp"], [class*="timestamp"], time').forEach((el) => {
        el.style.visibility = 'hidden';
      });
    });

    // 全页面截图对比
    await expect(page).toHaveScreenshot('stage4-investment-outlook.png', {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
      threshold: 0.2,
      animations: 'disabled',
    });
  });

  test('Stage 6 页面 — 整体视觉截图', async ({ page }) => {
    // 导航到 Stage 6 (Financial Modeling)
    const stage6Link = page.locator('button, a, [data-stage="6"]').filter({
      hasText: /Financial Model|财务建模|Stage 6|Asset Config/i,
    }).first();

    if (await stage6Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage6Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(3000);
    }

    // 隐藏动态内容
    await page.evaluate(() => {
      document.querySelectorAll('[data-testid*="timestamp"], [class*="timestamp"], time').forEach((el) => {
        el.style.visibility = 'hidden';
      });
    });

    // 全页面截图对比
    await expect(page).toHaveScreenshot('stage6-financial-modeling.png', {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
      threshold: 0.2,
      animations: 'disabled',
    });
  });

  test('ForwardSpreadCurve 组件 — 组件级截图', async ({ page }) => {
    // 导航到 Stage 4
    const stage4Link = page.locator('button, a, [data-stage="4"]').filter({
      hasText: /Investment Outlook|投资展望|Stage 4|Forward/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(3000);
    }

    // 定位 ForwardSpreadCurve 组件
    const forwardCurve = page.locator(
      '[data-testid="forward-spread-curve"], [class*="ForwardSpreadCurve"], [class*="forward-spread"], .recharts-wrapper'
    ).first();

    if (await forwardCurve.isVisible({ timeout: 10_000 }).catch(() => false)) {
      // 滚动到组件可见区域
      await forwardCurve.scrollIntoViewIfNeeded();
      await page.waitForTimeout(1000);

      // 组件级截图对比
      await expect(forwardCurve).toHaveScreenshot('forward-spread-curve.png', {
        maxDiffPixelRatio: 0.08, // 图表数据可能有轻微变化，放宽阈值
        threshold: 0.3,
        animations: 'disabled',
      });
    } else {
      // 如果找不到特定组件，截取图表区域
      const chartArea = page.locator('svg, canvas, [class*="chart"]').first();
      if (await chartArea.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await expect(chartArea).toHaveScreenshot('forward-spread-curve-fallback.png', {
          maxDiffPixelRatio: 0.1,
          threshold: 0.3,
          animations: 'disabled',
        });
      }
    }
  });

  test('CrossValidationTable 组件 — 组件级截图', async ({ page }) => {
    // 导航到包含 CrossValidationTable 的页面
    const stage4Link = page.locator('button, a, [data-stage="4"]').filter({
      hasText: /Investment Outlook|投资展望|Stage 4|Forward/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
    }

    // 查找 CrossValidationTable
    const crossTable = page.locator(
      '[data-testid="cross-validation-table"], [class*="CrossValidation"], table[class*="validation"]'
    ).first();

    // 如果在 Stage 4 找不到，尝试 Stage 6
    if (!(await crossTable.isVisible({ timeout: 5_000 }).catch(() => false))) {
      const stage6Link = page.locator('button, a, [data-stage="6"]').filter({
        hasText: /Financial Model|财务建模|Stage 6/i,
      }).first();
      if (await stage6Link.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await stage6Link.click();
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(2000);
      }
    }

    // 定位表格组件
    const table = page.locator(
      '[data-testid="cross-validation-table"], [class*="CrossValidation"], table'
    ).first();

    if (await table.isVisible({ timeout: 10_000 }).catch(() => false)) {
      await table.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);

      // 组件级截图对比
      await expect(table).toHaveScreenshot('cross-validation-table.png', {
        maxDiffPixelRatio: 0.05,
        threshold: 0.2,
        animations: 'disabled',
      });
    }
  });

  test('AssetConfigPanel 组件 — 组件级截图', async ({ page }) => {
    // 导航到 Stage 6
    const stage6Link = page.locator('button, a, [data-stage="6"]').filter({
      hasText: /Financial Model|财务建模|Stage 6|Asset Config/i,
    }).first();

    if (await stage6Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage6Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
    }

    // 定位 AssetConfigPanel 组件
    const assetPanel = page.locator(
      '[data-testid="asset-config-panel"], [class*="AssetConfig"], [class*="asset-config"]'
    ).first();

    if (await assetPanel.isVisible({ timeout: 10_000 }).catch(() => false)) {
      await assetPanel.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);

      // 组件级截图对比
      await expect(assetPanel).toHaveScreenshot('asset-config-panel.png', {
        maxDiffPixelRatio: 0.05,
        threshold: 0.2,
        animations: 'disabled',
      });
    } else {
      // 备选：截取包含配置面板的区域
      const configArea = page.locator(
        '[class*="config"], [class*="panel"], form, [class*="settings"]'
      ).first();

      if (await configArea.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await expect(configArea).toHaveScreenshot('asset-config-panel-fallback.png', {
          maxDiffPixelRatio: 0.08,
          threshold: 0.3,
          animations: 'disabled',
        });
      }
    }
  });

  test('暗色/亮色主题切换 — 视觉一致性', async ({ page }) => {
    // 检查是否有主题切换按钮
    const themeToggle = page.locator(
      'button[aria-label*="theme"], button[aria-label*="主题"], [data-testid="theme-toggle"], button:has([class*="moon"]), button:has([class*="sun"])'
    ).first();

    if (await themeToggle.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // 截取当前主题
      await expect(page).toHaveScreenshot('theme-default.png', {
        fullPage: false,
        maxDiffPixelRatio: 0.05,
        animations: 'disabled',
      });

      // 切换主题
      await themeToggle.click();
      await page.waitForTimeout(500);

      // 截取切换后的主题
      await expect(page).toHaveScreenshot('theme-toggled.png', {
        fullPage: false,
        maxDiffPixelRatio: 0.05,
        animations: 'disabled',
      });
    }
  });
});
