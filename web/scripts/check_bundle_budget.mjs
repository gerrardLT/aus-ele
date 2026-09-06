/**
 * check_bundle_budget.mjs — 前端产物体积预算检查（零依赖，读 dist）。
 *
 * 断言：
 *   ① index.html 静态引用的初始 JS chunk 总 raw 不超过预算；
 *   ② 不存在"同时含 PDF 导出栈标记（html2canvas/jspdf/html2pdf）且被 index.html
 *      静态引用"的 chunk —— 防止 pdf-vendor 回到关键路径。
 *   ③ ⌘K 命令面板（R3.4）必须独立成 chunk 且其代码标记不得出现在任何被 index.html
 *      静态引用的 chunk 里 —— Spec 要求「必须动态 import（不进 entry chunk）」。
 *      注意标记不能用 `openapi.json`：flags.js 的中文说明里就有这个词，会误报。
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
// ⌘K 面板/端点索引标记：都取自面板链路上独有的字符串字面量。
// 之所以不查 `openapi.json`：flags.js 的中文开关说明里就写着这个词，会稳定误报。
const PALETTE_MARKERS = ['AUS_ELE_API_KEY', 'Meta+K Control+K'];

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

// 断言③：⌘K 面板必须被切出去，且其代码不得混进入口静态引用的 chunk
// （Spec §129「必须动态 import」）。这条只在构建产物上可证：源码里的 import 形态
// 相同，但任何一处额外的静态引入都会把它拽回关键路径。
const chunkNames = fs.existsSync(path.join(DIST, 'assets'))
  ? fs.readdirSync(path.join(DIST, 'assets')).filter((n) => /^CommandPalette-.*\.js$/.test(n))
  : [];
if (chunkNames.length === 0) {
  fail('dist/assets 下没有 CommandPalette-*.js chunk —— 动态 import 的分包已失效，面板被并入其它 chunk');
}
// 门本身是否失效：标记全是源码里的字符串字面量，源码改了措辞这里就变成恒真的空门。
// 所以要求至少一个标记在整个产物里出现过（即面板代码确实被构建了）。
const allChunks = fs.existsSync(path.join(DIST, 'assets'))
  ? fs.readdirSync(path.join(DIST, 'assets')).filter((n) => n.endsWith('.js'))
  : [];
const liveMarkers = PALETTE_MARKERS.filter((marker) =>
  allChunks.some((n) => fs.readFileSync(path.join(DIST, 'assets', n), 'utf8').includes(marker)));
if (liveMarkers.length === 0) {
  fail(`⌘K 面板标记在产物中一个都不存在（${PALETTE_MARKERS.join(' / ')}）—— 该门已失效，请同步更新标记`);
}
for (const name of referenced) {
  const file = path.join(DIST, 'assets', name);
  if (!fs.existsSync(file)) continue;
  const content = fs.readFileSync(file, 'utf8');
  const hit = PALETTE_MARKERS.filter((marker) => content.includes(marker));
  if (hit.length > 0) {
    fail(`${name} 被 index.html 静态引用且含 ⌘K 面板标记（${hit.join(', ')}），命令面板回到关键路径`);
  }
}

if (process.exitCode === 1) {
  process.exit(1);
}
console.log('[bundle-budget] PASS');
