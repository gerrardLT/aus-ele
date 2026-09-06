// web/src/lib/pricingCopyGuard.test.js
// 定价页文案与结构门（R2.5）。放在 src/lib 下是因为它是硬门（node --test）的一部分：
// `web/src/pages/__tests__/pricingPage.test.jsx` 用 vitest，不在 CI 阻断路径上，而这里锁的
// 三件事恰恰是最容易在后续迭代里静默坏掉的：
//   1. CTA 指向一个真实存在的承接方（旧版三个按钮全指 /login，形成闭环死路）；
//   2. 不再声明已经作废的能力（「邀请制」在自助注册上线后就是假话）；
//   3. 卡片与功能条目数量不缩水（vitest 那三条 DOM 断言的源码版镜像）。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../pages/PricingPage.jsx'),
  'utf8'
);

test('plan CTAs resolve through resolveCta, not a hard-coded /login', () => {
  assert.match(SOURCE, /function resolveCta\(/, 'resolveCta 被删了：CTA 会退回死链');
  assert.match(SOURCE, /href=\{cta\.href\}/, '套餐按钮必须用解析出来的 href');
  assert.equal(SOURCE.includes('href="/login"'), true, '页头登录入口仍应存在');
  // 页头那一个 /login 之外不得再有 /login —— 套餐卡片的 CTA 是转化出口，不能是登录页。
  assert.equal(
    (SOURCE.match(/href="\/login"/g) || []).length,
    1,
    '出现第二个 href="/login"，说明某个套餐 CTA 又指回登录页了'
  );
  assert.equal(SOURCE.includes('{t.cta}'), false, 'CTA 文案不能再取自 plan 的静态 cta 字段');
});

test('free plan routes to self-registration and paid plans to a human', () => {
  const signup = (SOURCE.match(/ctaKind: 'signup'/g) || []).length;
  const contact = (SOURCE.match(/ctaKind: 'contact'/g) || []).length;
  assert.equal(signup, 1, '恰好一个套餐走自助注册');
  assert.equal(contact, 2, '两个付费套餐走人工联系');
  assert.match(SOURCE, /href: '\/register'/, '免费档出口必须是 /register');
  assert.match(SOURCE, /contactHref\(env, '\/help'\)/, '付费档必须在无邮箱时退化到 /help');
});

test('retired invite-only claims stay retired', () => {
  // 只扫可执行文本：注释里允许出现「旧措辞是 X」这种解释（本文件与 PricingPage 的注释都要
  // 说明为什么禁它），但界面字符串一旦写回旧措辞就是对外说了一句假话。
  const codeOnly = SOURCE.split('\n')
    .filter((line) => !/^\s*(?:\/\/|\*|\/\*)/.test(line))
    .join('\n');
  for (const stale of ['申请邀请', 'Request invite', '邀请制内测', 'invite-only']) {
    assert.equal(codeOnly.includes(stale), false, `定价页又出现了作废的表述：${stale}`);
  }
});

test('card and feature templates do not shrink (vitest assertions mirrored)', () => {
  // pricingPage.test.jsx 断言渲染后 `section.rounded-2xl` 恰好 3 个、`li.flex` > 9；那两条跑在
  // vitest 上（非阻断），这里做源码版镜像：卡片模板必须唯一、套餐数据必须仍是 3 份、功能清单
  // 条目不得减少。「少一个套餐」的症状是页面照旧正常渲染，只有计数能发现。
  assert.equal((SOURCE.match(/<section\b/g) || []).length, 1, '卡片模板必须唯一（数量由 PLANS 决定）');
  assert.equal((SOURCE.match(/^\s+agentRuns:/gm) || []).length, 3, 'PLANS 必须仍是三套餐');
  assert.equal((SOURCE.match(/<li key=\{f\} className="flex/g) || []).length, 1, '功能列表模板必须唯一');
  // 每个 features 数组写成一行，所以按行取数组、再数引号串，而不是按行首猜条目。
  const featureArrays = SOURCE.split('\n').filter((line) => /^\s*(?:zh|en): \['/.test(line));
  assert.equal(featureArrays.length, 6, '三套餐 × 中英各一份功能清单');
  const entries = featureArrays.reduce((sum, line) => sum + (line.match(/'[^']*'/g) || []).length, 0);
  assert.ok(entries >= 24, `功能条目总数不得少于 24（每份 4 条），实际 ${entries}`);
});

test('new legal documents are reachable from the conversion page', () => {
  for (const href of ['/legal/terms', '/legal/privacy', '/legal/disclaimer', '/legal/dpa', '/legal/aup', '/legal/cookies']) {
    assert.ok(SOURCE.includes(`'${href}'`), `定价页页脚缺少 ${href} 入口`);
  }
});
