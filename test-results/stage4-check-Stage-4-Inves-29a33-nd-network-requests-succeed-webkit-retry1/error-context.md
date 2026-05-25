# Test info

- Name: Stage 4 Investment Outlook - Frontend Check >> check Stage 4 modules render and network requests succeed
- Location: G:\project\aus-ele\tests\e2e\stage4-check.spec.js:8:7

# Error details

```
Error: browserType.launch: Executable doesn't exist at C:\Users\LT\AppData\Local\ms-playwright\webkit-2158\Playwright.exe
╔═════════════════════════════════════════════════════════════════════════╗
║ Looks like Playwright Test or Playwright was just installed or updated. ║
║ Please run the following command to download new browsers:              ║
║                                                                         ║
║     npx playwright install                                              ║
║                                                                         ║
║ <3 Playwright Team                                                      ║
╚═════════════════════════════════════════════════════════════════════════╝
```

# Test source

```ts
   1 | // @ts-check
   2 | import { test, expect } from '@playwright/test';
   3 |
   4 | /**
   5 |  * Stage 4 (投资前景情景) 前后端一致性检查
   6 |  */
   7 | test.describe('Stage 4 Investment Outlook - Frontend Check', () => {
>  8 |   test('check Stage 4 modules render and network requests succeed', async ({ page }) => {
     |       ^ Error: browserType.launch: Executable doesn't exist at C:\Users\LT\AppData\Local\ms-playwright\webkit-2158\Playwright.exe
   9 |     const consoleErrors = [];
   10 |     const networkFailures = [];
   11 |     const networkRequests = [];
   12 |
   13 |     // Capture console errors
   14 |     page.on('console', (msg) => {
   15 |       if (msg.type() === 'error') {
   16 |         consoleErrors.push(msg.text());
   17 |       }
   18 |     });
   19 |
   20 |     // Monitor network requests
   21 |     page.on('response', (response) => {
   22 |       const url = response.url();
   23 |       if (url.includes('/api/')) {
   24 |         networkRequests.push({ url, status: response.status() });
   25 |         if (response.status() >= 400) {
   26 |           networkFailures.push({ url, status: response.status() });
   27 |         }
   28 |       }
   29 |     });
   30 |
   31 |     // Navigate to the main page
   32 |     await page.goto('/', { waitUntil: 'networkidle' });
   33 |
   34 |     // Wait for page to load
   35 |     await page.waitForTimeout(2000);
   36 |
   37 |     // Look for Stage 4 tab/section - try clicking on it
   38 |     // The stage id is 'investment-outlook'
   39 |     const stage4Section = page.locator('[data-stage-id="investment-outlook"], #investment-outlook, [id*="investment-outlook"]');
   40 |     const stage4Tab = page.locator('text=投资前景情景').or(page.locator('text=Investment Outlook'));
   41 |
   42 |     if (await stage4Tab.count() > 0) {
   43 |       await stage4Tab.first().click();
   44 |       await page.waitForTimeout(3000);
   45 |     }
   46 |
   47 |     // Wait for network requests to settle
   48 |     await page.waitForTimeout(5000);
   49 |
   50 |     // Output results
   51 |     console.log('=== NETWORK REQUESTS ===');
   52 |     for (const req of networkRequests) {
   53 |       console.log(`  ${req.status} ${req.url}`);
   54 |     }
   55 |
   56 |     console.log('\n=== NETWORK FAILURES ===');
   57 |     for (const fail of networkFailures) {
   58 |       console.log(`  ${fail.status} ${fail.url}`);
   59 |     }
   60 |
   61 |     console.log('\n=== CONSOLE ERRORS ===');
   62 |     for (const err of consoleErrors) {
   63 |       console.log(`  ${err}`);
   64 |     }
   65 |
   66 |     // Check for Stage 4 specific API calls
   67 |     const stage4Apis = [
   68 |       'narrative/forward-spread',
   69 |       'narrative/events',
   70 |       'narrative/stratification',
   71 |       'outlook/cannibalization',
   72 |       'outlook/fcas-collapse',
   73 |       'outlook/regional-timing',
   74 |       'outlook/merchant-risk',
   75 |     ];
   76 |
   77 |     console.log('\n=== STAGE 4 API STATUS ===');
   78 |     for (const api of stage4Apis) {
   79 |       const matching = networkRequests.filter(r => r.url.includes(api));
   80 |       if (matching.length > 0) {
   81 |         for (const m of matching) {
   82 |           console.log(`  ${api}: ${m.status}`);
   83 |         }
   84 |       } else {
   85 |         console.log(`  ${api}: NOT CALLED`);
   86 |       }
   87 |     }
   88 |
   89 |     // Get page HTML structure for Stage 4 area
   90 |     const pageContent = await page.content();
   91 |     const hasForwardSpread = pageContent.includes('ForwardSpreadCurve') || pageContent.includes('forward-spread-curve') || pageContent.includes('前瞻价差');
   92 |     const hasEventAnnotation = pageContent.includes('EventAnnotation') || pageContent.includes('event-annotation');
   93 |     const hasStratification = pageContent.includes('Stratification') || pageContent.includes('收入分层') || pageContent.includes('Revenue Risk');
   94 |     const hasCannibalization = pageContent.includes('Cannibalization') || pageContent.includes('蚕食') || pageContent.includes('cannibalization');
   95 |     const hasFcasCollapse = pageContent.includes('FcasCollapse') || pageContent.includes('FCAS') || pageContent.includes('崩塌');
   96 |     const hasRegionalTiming = pageContent.includes('RegionalTiming') || pageContent.includes('区域投资时机') || pageContent.includes('Regional Timing');
   97 |     const hasMerchantRisk = pageContent.includes('MerchantRisk') || pageContent.includes('商户风险') || pageContent.includes('Merchant Risk');
   98 |
   99 |     console.log('\n=== COMPONENT RENDERING ===');
  100 |     console.log(`  ForwardSpreadCurve: ${hasForwardSpread ? 'RENDERED' : 'NOT FOUND'}`);
  101 |     console.log(`  EventAnnotationOverlay: ${hasEventAnnotation ? 'RENDERED' : 'NOT FOUND'}`);
  102 |     console.log(`  RevenueStratificationChart: ${hasStratification ? 'RENDERED' : 'NOT FOUND'}`);
  103 |     console.log(`  CannibalizationSimulator: ${hasCannibalization ? 'RENDERED' : 'NOT FOUND'}`);
  104 |     console.log(`  FcasCollapseForecaster: ${hasFcasCollapse ? 'RENDERED' : 'NOT FOUND'}`);
  105 |     console.log(`  RegionalTimingScorer: ${hasRegionalTiming ? 'RENDERED' : 'NOT FOUND'}`);
  106 |     console.log(`  MerchantRiskQuantifier: ${hasMerchantRisk ? 'RENDERED' : 'NOT FOUND'}`);
  107 |
  108 |     // Take a screenshot for reference
```