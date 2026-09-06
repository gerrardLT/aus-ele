// web/src/lib/brandConsistency.test.js
// R2.1/R2.2 品牌一致性门（单一品牌常量层的「锁」）。
//
// 为什么必须有这个常驻测试而不是一次性脚本：改名漏一处的表现是「界面上同时存在两个产品
// 名」，肉眼在两屏内容里看不出差别，也不会让任何功能测试变红。更糟的是 R1.1 批次新建的
// RegisterPage / VerifyEmailPage 本身就带着旧名字写出来 —— 说明「新增代码自带旧名」是持续
// 风险，不是一次改完就结束的事。
//
// 本文件刻意不出现任何被禁字面量：待查串全部由 FORMER_BRAND_NAMES 派生（大写变换），
// 否则本测试文件自己就会成为扫描器要豁免的对象，白名单失去意义。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  BRAND_NAME_EN,
  BRAND_NAME_ZH,
  DOCUMENT_TITLE_ZH,
  EMAIL_SUBJECT_PREFIX,
  FORMER_BRAND_NAMES,
  agentLabel,
  brandEyebrow,
  contactHref,
  legalEntityStatement,
  navBrand,
  reportEyebrow,
} from './brand.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(__dirname, '../..', '..');

// 唯一豁免：常量层自己。一个解释「为什么禁止写 X」的规则必须能说 X，
// 而 FORMER_BRAND_NAMES 就是那条法务文本的数据源。
const ALLOWED_FILES = new Set(['lib/brand.js']);

// 改名位点（R2.2）：这些文件里出现的产品名只能来自 lib/brand.js。
const BRAND_CONSUMERS = [
  'components/SidebarNavigation.jsx',
  'components/OnboardingTour.jsx',
  'components/ExportPreviewModal.jsx',
  'pages/LoginPage.jsx',
  'pages/RegisterPage.jsx',
  'pages/VerifyEmailPage.jsx',
  'pages/InviteAcceptPage.jsx',
  'pages/ForgotPasswordPage.jsx',
  'pages/AccountPage.jsx',
  'pages/AgentPage.jsx',
  'pages/HelpPage.jsx',
  'pages/PricingPage.jsx',
  'pages/LegalPage.jsx',
];

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(rel, out);
    else if (/\.(js|jsx|html)$/.test(entry.name)) out.push(rel);
  }
  return out;
}

const FORBIDDEN = new Set();
for (const former of FORMER_BRAND_NAMES) {
  FORBIDDEN.add(former);
  FORBIDDEN.add(former.toUpperCase());
  FORBIDDEN.add(former.toLowerCase());
}

test('no former product name survives outside the constant layer', () => {
  const files = [...walk(SRC_ROOT), path.resolve(SRC_ROOT, '../index.html')];
  const hits = [];
  for (const file of files) {
    const rel = path.relative(SRC_ROOT, file).split(path.sep).join('/');
    const outsideSrc = rel.startsWith('../');
    if (!outsideSrc && ALLOWED_FILES.has(rel)) continue;
    const body = fs.readFileSync(file, 'utf8');
    for (const needle of FORBIDDEN) {
      if (body.includes(needle)) hits.push(`${rel} :: ${needle}`);
    }
  }
  assert.deepEqual(hits, [], `发现未被常量层接管的产品名硬编码：\n${hits.join('\n')}`);
});

test('every rename site imports the brand layer', () => {
  for (const rel of BRAND_CONSUMERS) {
    const body = fs.readFileSync(path.resolve(SRC_ROOT, rel), 'utf8');
    assert.match(body, /from\s+'[^']*lib\/brand\.js'/, `${rel} 必须从 lib/brand.js 取品牌名`);
  }
});

test('every brand symbol used in a consumer file is actually imported there', () => {
  // 这条是本轮真踩出来的：批量改名脚本替换了 JSX 里的字面量，却因为 lines→text 没拼回而
  // 漏写 import。`npm run build` 完全不报错（未定义标识符在 ESM 里只是运行时
  // ReferenceError），node --test 也照绿 —— 只有把「用了就得 import」变成断言才拦得住。
  const moduleSource = fs.readFileSync(path.resolve(__dirname, 'brand.js'), 'utf8');
  const exported = [...moduleSource.matchAll(/^export\s+(?:const|function)\s+([A-Za-z0-9_$]+)/gm)].map((m) => m[1]);
  assert.ok(exported.length >= 10, `brand.js 导出解析异常（只找到 ${exported.length} 个），扫描失效`);

  const problems = [];
  for (const rel of BRAND_CONSUMERS) {
    const body = fs.readFileSync(path.resolve(SRC_ROOT, rel), 'utf8');
    const stmts = [...body.matchAll(/import\s*\{([^}]*)\}\s*from\s*'[^']*lib\/brand\.js'/g)];
    const imported = new Set(
      stmts.flatMap((m) => m[1].split(',').map((s) => s.trim().split(/\s+as\s+/).pop()).filter(Boolean))
    );
    const stripped = body.replace(/import\s*\{[^}]*\}\s*from\s*'[^']*lib\/brand\.js'/g, '');
    for (const name of exported) {
      const used = new RegExp(`[^\w$.]${name}\\s*\\(`).test(`\n${stripped}`);
      if (used && !imported.has(name)) problems.push(`${rel}: 调用了 ${name}() 但没有 import`);
    }
  }
  assert.deepEqual(problems, [], problems.join('\n'));
});

test('static document title matches the constant', () => {
  const html = fs.readFileSync(path.resolve(SRC_ROOT, '../index.html'), 'utf8');
  const title = /<title>(.*?)<\/title>/.exec(html)?.[1] ?? '';
  assert.equal(title.includes(DOCUMENT_TITLE_ZH), true,
    `index.html <title> 必须含常量 DOCUMENT_TITLE_ZH，实际：${title}`);
});

test('translations.js brand values stay in sync with navBrand()', () => {
  // translations.js 的结构被 finlandBoard/gridForecast 用源码字面量锁死，改不动成 import，
  // 所以这里当它的看门人：值必须与常量层同义，否则改名会留下一个过期的侧边栏品牌。
  return import('../translations.js').then(({ translations }) => {
    assert.equal(translations.zh.nav.brand, navBrand(true));
    assert.equal(translations.en.nav.brand, navBrand(false));
  });
});

test('email subject prefix is byte-identical with backend/brand.py', () => {
  const py = fs.readFileSync(path.resolve(REPO_ROOT, 'backend/brand.py'), 'utf8');
  const value = /EMAIL_SUBJECT_PREFIX\s*=\s*f?["'](.+?)["']/.exec(py)?.[1];
  assert.ok(value, 'backend/brand.py 必须导出 EMAIL_SUBJECT_PREFIX');
  // 后端用的是 f"[{BRAND_NAME_ZH}]" —— 展开后必须与前端镜像值一致，否则邮件标题和品牌名分叉。
  assert.equal(value.replace('{BRAND_NAME_ZH}', BRAND_NAME_ZH), EMAIL_SUBJECT_PREFIX);
});

test('product-facing brand strings never lead with the data source abbreviation', () => {
  // 报告页眉会被转发给第三方，旧值把机构缩写排在最前，读起来像官方产品。
  for (const label of [agentLabel(true), agentLabel(false), reportEyebrow(true), reportEyebrow(false), brandEyebrow(true)]) {
    assert.equal(label.includes('AEMO'), false, `${label} 不应包含数据源缩写`);
    assert.ok(label.includes(BRAND_NAME_ZH) || label.includes(BRAND_NAME_EN));
  }
});

test('legal statements never invent a registration number', () => {
  const digits = /\b\d{11}\b/;
  assert.equal(digits.test(legalEntityStatement({}, true)), false, '未配置时不得出现 11 位数字');
  assert.equal(digits.test(legalEntityStatement({}, false)), false);
  // 格式错的 ABN 按未配置处理，而不是照抄进合同文本。
  const garbage = legalEntityStatement({ VITE_LEGAL_ENTITY_NAME: 'X Pty Ltd', VITE_LEGAL_ABN: '12345' }, true);
  assert.equal(digits.test(garbage), false);
  assert.match(garbage, /X Pty Ltd/);
  // 只有合法 11 位数字才会被渲染出来。
  const full = legalEntityStatement({ VITE_LEGAL_ENTITY_NAME: 'X Pty Ltd', VITE_LEGAL_ABN: '51 824 753 556' }, true);
  assert.match(full, /51824753556/);
});

test('contact CTA degrades to a real destination when no email is configured', () => {
  assert.equal(contactHref({}, '/help'), '/help');
  assert.equal(contactHref({ VITE_SUPPORT_EMAIL: 'hi@example.com' }, '/help'), 'mailto:hi@example.com');
});

test('brand module has no import-time env reads', () => {
  // node:test 下 import.meta.env 是 undefined，模块顶层碰它会让整条 lib 测试链崩掉。
  const body = fs.readFileSync(path.resolve(__dirname, 'brand.js'), 'utf8');
  const codeOnly = body.split('\n').filter((l) => !l.trim().startsWith('*') && !l.trim().startsWith('//')).join('\n');
  assert.equal(codeOnly.includes('import.meta.env'), false, 'brand.js 只能在函数形参里接收 env');
});
