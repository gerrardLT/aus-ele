/**
 * check_bundle_budget.mjs — 前端产物体积预算检查（零依赖，读 dist）。
 *
 * 断言：
 *   ① index.html 静态引用的初始 JS chunk 总 raw 不超过预算；
 *   ② 不存在"同时含 PDF 导出栈标记（html2canvas/jspdf/html2pdf）且被 index.html
 *      静态引用"的 chunk —— 防止 pdf-vendor 回到关键路径。
 *
 * 预算基线（2026-08-20，manualChunks 外科后构建实测）：
 *   入口 JS raw ≈ 807KB（charts-vendor 457KB + react-vendor 206KB + motion-vendor 125KB + 入口/运行时 19KB）。
 *   charts-vendor 为 MarketPage 首屏图表（PriceChart/HourlyDistributionChart）的静态依赖，
 *   降到 300KB 需要组件级懒加载 recharts，列为后续 epic；此处先做防回退守门。
 *
 * 用法：node scripts/check_bundle_budget.mjs（在 web/ 目录下，构建后执行）
 */
import fs from 'node:fs';
import path from 'node:path';

const DIST = path.resolve('dist');
const INDEX_HTML = path.join(DIST, 'index.html');
// 初始 JS 预算（raw 字节）：基线 807KB，留 ~5% 余量
const ENTRY_JS_BUDGET_BYTES = 850 * 1024;
// PDF 导出栈标记：任一出现在入口引用的 chunk 中即判定违规
const PDF_MARKERS = ['html2canvas', 'jspdf', 'html2pdf'];

function fail(msg) {
  console.error(`[bundle-budget] FAIL: ${msg}`);
  process.exitCode = 1;
}

if (!fs.existsSync(INDEX_HTML)) {
  fail('dist/index.html 不存在，请先执行 npm run build');
  process.exit(1);
}

const html = fs.readFileSync(INDEX_HTML, 'utf8');
const referenced = [...html.matchAll(/(?:src|href)="\/assets\/([^?#"]+\.js)"/g)].map(m => m[1]);

if (referenced.length === 0) {
  fail('未从 dist/index.html 解析到任何 JS 引用，检查产物结构');
  process.exit(1);
}

// 断言①：初始 JS 总体积
let totalJs = 0;
for (const name of referenced) {
  const file = path.join(DIST, 'assets', name);
  if (!fs.existsSync(file)) {
    fail(`index.html 引用的 ${name} 在 dist/assets 中不存在`);
    continue;
  }
  totalJs += fs.statSync(file).size;
}
console.log(`[bundle-budget] 入口初始 JS：${referenced.length} 个 chunk，raw ${(totalJs / 1024).toFixed(1)}KB，预算 ${(ENTRY_JS_BUDGET_BYTES / 1024).toFixed(0)}KB`);
if (totalJs > ENTRY_JS_BUDGET_BYTES) {
  fail(`初始 JS ${totalJs} 字节超出预算 ${ENTRY_JS_BUDGET_BYTES} 字节`);
}

// 断言②：PDF 栈不得进入入口静态引用的 chunk
for (const name of referenced) {
  const content = fs.readFileSync(path.join(DIST, 'assets', name), 'utf8');
  const hit = PDF_MARKERS.filter(marker => content.includes(marker));
  if (hit.length > 0) {
    fail(`${name} 被 index.html 静态引用且包含 PDF 栈标记（${hit.join(', ')}），PDF 导出栈回到关键路径`);
  }
}

if (process.exitCode === 1) {
  process.exit(1);
}
console.log('[bundle-budget] PASS');
