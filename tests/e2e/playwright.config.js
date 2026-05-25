// @ts-check
import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright 配置 — AEMO Intelligence Platform E2E 测试
 *
 * 支持多浏览器（Chromium, Firefox, WebKit）
 * 包含视觉回归截图配置
 *
 * 前提：
 * - 前端开发服务器运行在 http://localhost:5173 (Vite)
 * - 后端 API 运行在 http://localhost:8085 (通过 Vite 代理)
 */
export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.js',
  timeout: 60_000,
  retries: 1,
  workers: 1,

  /* 全局期望配置 */
  expect: {
    /* 视觉回归截图对比阈值 */
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.05,
      threshold: 0.2,
    },
  },

  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    viewport: { width: 1440, height: 900 },
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: '../../playwright-report' }],
  ],

  outputDir: '../../test-results',
});
