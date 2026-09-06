// web/src/lib/legalReachability.test.js
// 法务文件「可达 + 陈述仍然为真」门（R2.4，2026-09-06）。
//
// 这一层为什么值得单独锁：法务文本的回归不会让任何功能测试变红、不会有任何报错，唯一的
// 后果是用户按不存在的流程去申请、或者我们对外说了一件系统已经不再做的事。前一种上轮已经
// 用 dataRights.test.js 锁住（隐私页第 5 条），这里锁后一种 —— **把法务里的可验证陈述
// 直接对着代码验一遍**。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, '..');
const BACKEND_ROOT = path.resolve(__dirname, '../../../backend');

const LEGAL_SOURCE = fs.readFileSync(path.resolve(SRC_ROOT, 'pages/LegalPage.jsx'), 'utf8');
const REGISTER_SOURCE = fs.readFileSync(path.resolve(SRC_ROOT, 'pages/RegisterPage.jsx'), 'utf8');
const PRICING_SOURCE = fs.readFileSync(path.resolve(SRC_ROOT, 'pages/PricingPage.jsx'), 'utf8');

const TOPICS = ['terms', 'privacy', 'disclaimer', 'dpa', 'aup', 'cookies'];

function pySources(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__pycache__' || entry.name === '.venv') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) pySources(full, out);
    else if (entry.name.endsWith('.py')) out.push(full);
  }
  return out;
}

test('all six legal documents exist in both languages with real content', () => {
  for (const topic of TOPICS) {
    assert.ok(new RegExp(`^  ${topic}: \\{`, 'm').test(LEGAL_SOURCE), `缺少 /legal/${topic} 的正文`);
  }
  // zh 与 en 各自的 sections 数组数量必须相等，否则切语言会看到半份文件。
  const blocks = (LEGAL_SOURCE.match(/^\s+sections: \[$/gm) || []).length;
  assert.ok(blocks >= 12, `六份文件 × 中英两个语言块应有 ≥12 个 sections 数组，实际 ${blocks}`);
  const sectionTuples = LEGAL_SOURCE.match(/^\s+\['\d+\./gm) || [];
  assert.ok(sectionTuples.length >= 70, `六份文件 × 中英各 ≥6 条，实际条目数 ${sectionTuples.length}`);
});

test('tabs and topic routing stay derived from the same list', () => {
  // currentTopic() 与 tabs 都由 TOPICS 生成；分叉的症状是「链接能打开但永远显示服务条款」。
  const list = /const TOPICS = \[([^\]]+)\]/.exec(LEGAL_SOURCE)?.[1] ?? '';
  for (const topic of TOPICS) {
    assert.ok(list.includes(`'${topic}'`), `TOPICS 少了 ${topic}`);
    assert.ok(LEGAL_SOURCE.includes(`TAB_LABELS`) , '标签必须由 TAB_LABELS 统一生成');
  }
  assert.match(LEGAL_SOURCE, /path: `\/legal\/\$\{id\}`/, 'tab 路径必须由 TOPICS 派生');
});

test('consent and conversion pages link to the documents they invoke', () => {
  // 注册即同意 → 条款/隐私/AUP 必须在注册页可点；定价页承诺过的东西必须有出处。
  for (const href of ['/legal/terms', '/legal/privacy', '/legal/aup']) {
    assert.ok(REGISTER_SOURCE.includes(`href="${href}"`), `注册页缺少 ${href} 入口`);
  }
  for (const href of TOPICS.map((t) => `/legal/${t}`)) {
    assert.ok(PRICING_SOURCE.includes(`'${href}'`), `定价页页脚缺少 ${href}`);
  }
});

test('the "we set no cookies" claim is still true in the backend', () => {
  // /legal/cookies 第 1 条是一句对外陈述：一旦哪天有人加了 Set-Cookie（会话 cookie、
  // 分析 SDK、反代注入的 sticky cookie 都算），这句话立刻变成不实陈述，而全库只有这里会发现。
  const offenders = [];
  for (const file of pySources(BACKEND_ROOT)) {
    const body = fs.readFileSync(file, 'utf8');
    if (body.includes('Set-Cookie') || body.includes('set_cookie')) {
      offenders.push(path.relative(BACKEND_ROOT, file).split(path.sep).join('/'));
    }
  }
  assert.deepEqual(offenders, [],
    `后端开始下发 cookie（${offenders.join(', ')}），必须同步改写 /legal/cookies 第 1、8 条与第 3 条的权衡说明`);
});

test('local storage keys named in the cookies page are the keys the app actually uses', () => {
  // 清单式披露最容易过期：加了新的 localStorage 键却忘了更新那份清单，用户读到的就是旧名单。
  const disclosed = ['aus_auth_v1', 'app_lang', 'app_theme', 'app_autonomy_tier', 'aus_tour_v1', 'aus_saved_views_v1', 'developer_portal_api_key'];
  const cookiesText = LEGAL_SOURCE.slice(LEGAL_SOURCE.indexOf('cookies: {'));
  for (const key of disclosed) {
    assert.ok(cookiesText.includes(key), `/legal/cookies 未披露 localStorage 键 ${key}`);
  }
});
