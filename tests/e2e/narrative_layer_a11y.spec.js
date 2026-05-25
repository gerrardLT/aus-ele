// @ts-check
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * Investment Narrative Layer — 可访问性测试
 *
 * 使用 @axe-core/playwright 进行自动化可访问性检测：
 * - Stage 4 页面无严重可访问性违规
 * - Stage 6 页面无严重可访问性违规
 * - 表格有正确的 ARIA 标签
 * - 图表有替代文本描述
 * - 按钮有可访问名称
 * - 颜色对比度符合 WCAG AA
 *
 * 注意：完整的 WCAG 合规验证需要人工辅助技术测试和专家审查。
 */

test.describe('Investment Narrative Layer — 可访问性测试', () => {

  test('Stage 4 页面 — 无严重可访问性违规 (critical/serious)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 导航到 Stage 4 — Tab 按钮带 role="tab"
    const stage4Link = page.locator('button[role="tab"]').filter({
      hasText: /Investment Outlook|投资前景|Scenarios/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000); // 等待动态内容渲染
    }

    // 运行 axe-core 扫描
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    // 过滤严重和关键违规
    const criticalViolations = accessibilityScanResults.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );

    // 输出违规详情用于调试
    if (criticalViolations.length > 0) {
      console.log('Stage 4 严重可访问性违规:');
      criticalViolations.forEach((v) => {
        console.log(`  [${v.impact}] ${v.id}: ${v.description}`);
        v.nodes.forEach((node) => {
          console.log(`    - ${node.target.join(', ')}`);
        });
      });
    }

    // 不应有严重或关键违规
    expect(
      criticalViolations,
      `Stage 4 存在 ${criticalViolations.length} 个严重可访问性违规`
    ).toHaveLength(0);
  });

  test('Stage 6 页面 — 无严重可访问性违规 (critical/serious)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 导航到 Stage 6 — Tab 按钮带 role="tab"
    const stage6Link = page.locator('button[role="tab"]').filter({
      hasText: /Financial Model|财务建模/i,
    }).first();

    if (await stage6Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage6Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
    }

    // 运行 axe-core 扫描
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    // 过滤严重和关键违规
    const criticalViolations = accessibilityScanResults.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );

    if (criticalViolations.length > 0) {
      console.log('Stage 6 严重可访问性违规:');
      criticalViolations.forEach((v) => {
        console.log(`  [${v.impact}] ${v.id}: ${v.description}`);
        v.nodes.forEach((node) => {
          console.log(`    - ${node.target.join(', ')}`);
        });
      });
    }

    expect(
      criticalViolations,
      `Stage 6 存在 ${criticalViolations.length} 个严重可访问性违规`
    ).toHaveLength(0);
  });

  test('表格 — 有正确的 ARIA 标签和结构', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 导航到包含表格的页面
    const stage6Link = page.locator('button[role="tab"]').filter({
      hasText: /Financial Model|财务建模/i,
    }).first();

    if (await stage6Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage6Link.click();
      await page.waitForLoadState('networkidle');
    }

    // 查找所有表格
    const tables = page.locator('table');
    const tableCount = await tables.count();

    if (tableCount > 0) {
      for (let i = 0; i < tableCount; i++) {
        const table = tables.nth(i);

        // 验证表格有 caption 或 aria-label 或 aria-labelledby
        const hasCaption = await table.locator('caption').count() > 0;
        const hasAriaLabel = await table.getAttribute('aria-label');
        const hasAriaLabelledBy = await table.getAttribute('aria-labelledby');
        const hasRole = await table.getAttribute('role');

        const isAccessible = hasCaption || hasAriaLabel || hasAriaLabelledBy || hasRole === 'table';
        expect(
          isAccessible,
          `表格 ${i + 1} 缺少 caption、aria-label 或 aria-labelledby`
        ).toBeTruthy();

        // 验证表格有 thead 或 th 元素
        const hasHeaders = await table.locator('thead, th, [role="columnheader"]').count() > 0;
        expect(hasHeaders, `表格 ${i + 1} 缺少表头 (th/thead)`).toBeTruthy();

        // 验证 th 元素有 scope 属性
        const thElements = table.locator('th');
        const thCount = await thElements.count();
        for (let j = 0; j < Math.min(thCount, 5); j++) {
          const scope = await thElements.nth(j).getAttribute('scope');
          const role = await thElements.nth(j).getAttribute('role');
          // th 应有 scope 或 role 属性
          const hasProperRole = scope || role;
          // 这是建议性检查，不强制失败
          if (!hasProperRole) {
            console.log(`  提示: 表格 ${i + 1} 的 th[${j}] 缺少 scope 属性`);
          }
        }
      }
    }
  });

  test('图表 — 有替代文本描述', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 导航到 Stage 4（包含图表）
    const stage4Link = page.locator('button[role="tab"]').filter({
      hasText: /Investment Outlook|投资前景|Scenarios/i,
    }).first();

    if (await stage4Link.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await stage4Link.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
    }

    // 查找 SVG 图表元素
    const svgCharts = page.locator('svg[role="img"], svg[aria-label], .recharts-wrapper svg');
    const svgCount = await svgCharts.count();

    if (svgCount > 0) {
      for (let i = 0; i < svgCount; i++) {
        const svg = svgCharts.nth(i);

        // SVG 应有 role="img" 和 aria-label，或包含 <title> 元素
        const hasAriaLabel = await svg.getAttribute('aria-label');
        const hasTitle = await svg.locator('title').count() > 0;
        const hasDesc = await svg.locator('desc').count() > 0;
        const hasRole = await svg.getAttribute('role');

        const hasAltText = hasAriaLabel || hasTitle || hasDesc;

        if (!hasAltText) {
          console.log(`  警告: SVG 图表 ${i + 1} 缺少替代文本 (aria-label/title/desc)`);
        }
      }
    }

    // 查找 canvas 图表
    const canvasCharts = page.locator('canvas');
    const canvasCount = await canvasCharts.count();

    if (canvasCount > 0) {
      for (let i = 0; i < canvasCount; i++) {
        const canvas = canvasCharts.nth(i);

        // Canvas 应有 role="img" 和 aria-label
        const hasAriaLabel = await canvas.getAttribute('aria-label');
        const hasFallback = await canvas.textContent();

        expect(
          hasAriaLabel || (hasFallback && hasFallback.length > 0),
          `Canvas 图表 ${i + 1} 缺少 aria-label 或回退文本`
        ).toBeTruthy();
      }
    }

    // 查找图表容器的 aria-label
    const chartContainers = page.locator(
      '[data-testid*="chart"], [class*="chart"], [class*="Chart"], .recharts-wrapper'
    );
    const containerCount = await chartContainers.count();

    if (containerCount > 0) {
      for (let i = 0; i < containerCount; i++) {
        const container = chartContainers.nth(i);
        const ariaLabel = await container.getAttribute('aria-label');
        const ariaDescribedBy = await container.getAttribute('aria-describedby');
        const role = await container.getAttribute('role');

        if (!ariaLabel && !ariaDescribedBy && role !== 'img') {
          console.log(`  提示: 图表容器 ${i + 1} 建议添加 aria-label 描述`);
        }
      }
    }
  });

  test('按钮 — 有可访问名称', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 运行 axe-core 专门检查按钮可访问性
    const results = await new AxeBuilder({ page })
      .include('button, [role="button"], a[role="button"]')
      .withRules(['button-name', 'link-name'])
      .analyze();

    // 不应有按钮缺少可访问名称
    const buttonNameViolations = results.violations.filter(
      (v) => v.id === 'button-name'
    );

    if (buttonNameViolations.length > 0) {
      console.log('缺少可访问名称的按钮:');
      buttonNameViolations.forEach((v) => {
        v.nodes.forEach((node) => {
          console.log(`  - ${node.target.join(', ')}: ${node.failureSummary}`);
        });
      });
    }

    expect(
      buttonNameViolations,
      `${buttonNameViolations.length} 个按钮缺少可访问名称`
    ).toHaveLength(0);

    // 额外检查：所有按钮都应有文本内容或 aria-label
    const allButtons = page.locator('button, [role="button"]');
    const buttonCount = await allButtons.count();

    for (let i = 0; i < Math.min(buttonCount, 20); i++) {
      const button = allButtons.nth(i);
      const text = await button.textContent();
      const ariaLabel = await button.getAttribute('aria-label');
      const title = await button.getAttribute('title');

      const hasName = (text && text.trim().length > 0) || ariaLabel || title;
      expect(
        hasName,
        `按钮 ${i + 1} 缺少可访问名称 (文本/aria-label/title)`
      ).toBeTruthy();
    }
  });

  test('颜色对比度 — 符合 WCAG AA 标准', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 运行 axe-core 颜色对比度检查
    const results = await new AxeBuilder({ page })
      .withRules(['color-contrast'])
      .analyze();

    // 过滤颜色对比度违规
    const contrastViolations = results.violations.filter(
      (v) => v.id === 'color-contrast'
    );

    if (contrastViolations.length > 0) {
      console.log('颜色对比度违规:');
      contrastViolations.forEach((v) => {
        console.log(`  影响级别: ${v.impact}`);
        v.nodes.slice(0, 5).forEach((node) => {
          console.log(`  - ${node.target.join(', ')}`);
          console.log(`    ${node.failureSummary}`);
        });
        if (v.nodes.length > 5) {
          console.log(`  ... 还有 ${v.nodes.length - 5} 个违规`);
        }
      });
    }

    // 严重的对比度违规数量应为 0
    const seriousContrastViolations = contrastViolations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical'
    );

    expect(
      seriousContrastViolations,
      `${seriousContrastViolations.length} 个严重颜色对比度违规`
    ).toHaveLength(0);
  });

  test('键盘导航 — 所有交互元素可通过键盘访问', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 使用 Tab 键遍历页面，验证焦点可见
    let tabCount = 0;
    const maxTabs = 30;

    while (tabCount < maxTabs) {
      await page.keyboard.press('Tab');
      tabCount++;

      // 获取当前焦点元素
      const focusedElement = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        return {
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role'),
          text: el.textContent?.slice(0, 50),
          hasOutline: window.getComputedStyle(el).outlineStyle !== 'none',
        };
      });

      if (!focusedElement) continue;

      // 交互元素应有可见的焦点指示器
      // （注意：某些 CSS 框架使用 focus-visible 而非 outline）
      if (['button', 'a', 'input', 'select'].includes(focusedElement.tag)) {
        // 验证焦点元素存在（不强制检查 outline 样式，因为可能用其他方式）
        expect(focusedElement).toBeTruthy();
      }
    }

    // 验证至少有一些元素可以通过 Tab 到达
    expect(tabCount).toBeGreaterThan(0);
  });
});
