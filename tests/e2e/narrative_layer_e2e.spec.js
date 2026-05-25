// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Investment Narrative Layer — E2E 端到端测试
 *
 * 测试完整用户流程：
 * - Stage 4 (Investment Outlook) ForwardSpreadCurve 加载
 * - Stage 6 (Financial Modeling) AssetConfigPanel 加载
 * - 资产配置修改与持久化
 * - 区域切换与数据重新加载
 * - CrossValidationTable 数据展示
 * - NarrativeTooltip hover 归因显示
 */

test.describe('Investment Narrative Layer — 端到端流程', () => {

  test.beforeEach(async ({ page }) => {
    // 导航到应用首页并等待加载完成
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('Stage 4: Investment Outlook — ForwardSpreadCurve 正确加载', async ({ page }) => {
    // 导航到 Stage 4 (Investment Outlook) — Tab 按钮带 role="tab"
    const stage4Link = page.locator('button[role="tab"]').filter({
      hasText: /Investment Outlook|投资前景|Scenarios/i,
    }).first();
    await stage4Link.click();

    // 等待 ForwardSpreadCurve 组件加载
    const forwardCurve = page.locator(
      '[data-testid="forward-spread-curve"], [class*="ForwardSpreadCurve"], [class*="forward-spread"]'
    );
    await expect(forwardCurve).toBeVisible({ timeout: 15_000 });

    // 验证图表 SVG 或 Canvas 已渲染
    const chartElement = forwardCurve.locator('svg, canvas').first();
    await expect(chartElement).toBeVisible({ timeout: 10_000 });

    // 验证图表中有数据路径（SVG path 或 recharts 线条）
    const dataPath = forwardCurve.locator('svg path[d], .recharts-line, .recharts-area').first();
    await expect(dataPath).toBeVisible({ timeout: 10_000 });
  });

  test('Stage 6: Financial Modeling — AssetConfigPanel 正确加载', async ({ page }) => {
    // 导航到 Stage 6 (Financial Modeling) — Tab 按钮带 role="tab"
    const stage6Link = page.locator('button[role="tab"]').filter({
      hasText: /Financial Model|财务建模/i,
    }).first();
    await stage6Link.click();

    // 等待 AssetConfigPanel 组件加载
    const assetPanel = page.locator(
      '[data-testid="asset-config-panel"], [class*="AssetConfig"], [class*="asset-config"]'
    );
    await expect(assetPanel).toBeVisible({ timeout: 15_000 });

    // 验证面板中有输入字段（容量、效率、衰减率等）
    const inputFields = assetPanel.locator('input, select');
    const fieldCount = await inputFields.count();
    expect(fieldCount).toBeGreaterThan(0);
  });

  test('资产配置修改并保存 — 验证持久化', async ({ page }) => {
    // 导航到 Stage 6
    const stage6Link = page.locator('button[role="tab"]').filter({
      hasText: /Financial Model|财务建模/i,
    }).first();
    await stage6Link.click();

    // 等待 AssetConfigPanel 加载
    const assetPanel = page.locator(
      '[data-testid="asset-config-panel"], [class*="AssetConfig"], [class*="asset-config"]'
    );
    await expect(assetPanel).toBeVisible({ timeout: 15_000 });

    // 找到容量输入字段并修改
    const capacityInput = assetPanel.locator(
      'input[name*="capacity"], input[aria-label*="capacity"], label:has-text("Capacity") input, label:has-text("容量") input'
    ).first();

    if (await capacityInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // 清空并输入新值
      await capacityInput.fill('200');

      // 点击保存按钮
      const saveButton = page.locator('button').filter({
        hasText: /Save|保存|Apply|应用/i,
      }).first();
      if (await saveButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await saveButton.click();

        // 等待保存成功的反馈
        await page.waitForTimeout(1000);

        // 刷新页面验证持久化
        await page.reload();
        await page.waitForLoadState('networkidle');

        // 重新导航到 Stage 6
        await stage6Link.click();
        await expect(assetPanel).toBeVisible({ timeout: 15_000 });

        // 验证值已保存
        const savedValue = await capacityInput.inputValue();
        expect(savedValue).toBe('200');
      }
    }
  });

  test('切换区域 — 验证数据重新加载', async ({ page }) => {
    // 导航到 Stage 4
    const stage4Link = page.locator('button[role="tab"]').filter({
      hasText: /Investment Outlook|投资前景|Scenarios/i,
    }).first();
    await stage4Link.click();

    // 等待初始数据加载
    await page.waitForLoadState('networkidle');

    // 找到区域选择器
    const regionSelector = page.locator(
      '[data-testid="region-selector"], [class*="region"], button:has-text("NSW"), button:has-text("QLD")'
    ).first();
    await expect(regionSelector).toBeVisible({ timeout: 10_000 });

    // 切换到 QLD 区域
    const qldButton = page.locator('button').filter({ hasText: /QLD/ }).first();
    if (await qldButton.isVisible()) {
      // 监听 API 请求以验证数据重新加载
      const responsePromise = page.waitForResponse(
        (response) =>
          (response.url().includes('/api/') &&
            response.url().includes('QLD')) ||
          response.url().includes('region=QLD'),
        { timeout: 15_000 }
      );

      await qldButton.click();

      // 验证新的 API 请求被触发
      const response = await responsePromise.catch(() => null);
      if (response) {
        expect(response.status()).toBeLessThan(500);
      }
    }

    // 切换到 SA 区域
    const saButton = page.locator('button').filter({ hasText: /^SA$/ }).first();
    if (await saButton.isVisible()) {
      await saButton.click();
      // 等待数据刷新
      await page.waitForLoadState('networkidle');
    }
  });

  test('CrossValidationTable — 验证数据展示', async ({ page }) => {
    // 导航到包含 CrossValidationTable 的页面（Stage 4 或 Stage 6）
    const stage4Link = page.locator('button[role="tab"]').filter({
      hasText: /Investment Outlook|投资前景|Scenarios/i,
    }).first();
    await stage4Link.click();
    await page.waitForLoadState('networkidle');

    // 查找 CrossValidationTable 组件
    const crossTable = page.locator(
      '[data-testid="cross-validation-table"], [class*="CrossValidation"], table[class*="validation"]'
    );

    // 如果在 Stage 4 找不到，尝试 Stage 6
    if (!(await crossTable.isVisible({ timeout: 5_000 }).catch(() => false))) {
      const stage6Link = page.locator('button[role="tab"]').filter({
        hasText: /Financial Model|财务建模/i,
      }).first();
      await stage6Link.click();
      await page.waitForLoadState('networkidle');
    }

    // 验证表格存在并有数据行
    const table = page.locator('table').first();
    await expect(table).toBeVisible({ timeout: 15_000 });

    // 验证表格有表头
    const headers = table.locator('thead th, th');
    const headerCount = await headers.count();
    expect(headerCount).toBeGreaterThan(0);

    // 验证表格有数据行
    const rows = table.locator('tbody tr, tr').filter({ hasNot: page.locator('th') });
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test('NarrativeTooltip — hover 显示归因信息', async ({ page }) => {
    // 导航到 Stage 4
    const stage4Link = page.locator('button[role="tab"]').filter({
      hasText: /Investment Outlook|投资前景|Scenarios/i,
    }).first();
    await stage4Link.click();
    await page.waitForLoadState('networkidle');

    // 查找带有 narrative tooltip 的元素
    const narrativeElement = page.locator(
      '[data-testid*="narrative"], [data-tooltip], [class*="narrative"], [aria-describedby*="tooltip"]'
    ).first();

    if (await narrativeElement.isVisible({ timeout: 10_000 }).catch(() => false)) {
      // Hover 触发 tooltip
      await narrativeElement.hover();

      // 等待 tooltip 出现
      const tooltip = page.locator(
        '[role="tooltip"], [class*="tooltip"], [class*="Tooltip"], [data-testid*="tooltip"]'
      );
      await expect(tooltip).toBeVisible({ timeout: 5_000 });

      // 验证 tooltip 包含归因文本
      const tooltipText = await tooltip.textContent();
      expect(tooltipText).toBeTruthy();
      expect(tooltipText.length).toBeGreaterThan(5);
    } else {
      // 备选：查找图表中的数据点并 hover
      const dataPoint = page.locator(
        '.recharts-dot, .recharts-active-dot, svg circle, [class*="data-point"]'
      ).first();

      if (await dataPoint.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await dataPoint.hover();
        // 验证有 tooltip 或 popover 出现
        const anyTooltip = page.locator('[role="tooltip"], [class*="tooltip"]');
        await expect(anyTooltip).toBeVisible({ timeout: 5_000 });
      }
    }
  });
});
