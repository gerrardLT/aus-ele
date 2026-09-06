// web/src/lib/dataRights.test.js
// 隐私政策「用户权利」条的文案门控测试（R6.4 顺序约束）。
//
// 最有价值的一条是读 LegalPage.jsx 源码，断言那句不实陈述没有以字面量的形式回来：
// 法务文案的回归不会有任何测试变红、没有任何报错，只有用户按不存在的流程去申请。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  DATA_RIGHTS_FLAG,
  dataRightsStatement,
  isDataRightsEnabled,
  privacyRightsCopy,
  supportEmail,
} from './dataRights.js';
import { FLAG_DEFS } from './flags.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LEGAL_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../pages/LegalPage.jsx'),
  'utf8'
);

test('privacy page no longer asserts a capability as a hard-coded literal', () => {
  // 这三串都是「没有承接方的承诺」：端点不存在时它们就是不实陈述。
  for (const lie of ['可申请导出或删除账户数据', 'Users may request export or deletion']) {
    assert.ok(!LEGAL_SOURCE.includes(lie), `LegalPage.jsx 里又出现了写死的权利承诺：${lie}`);
  }
  assert.match(LEGAL_SOURCE, /privacyRightsCopy\(/, '第 5 条必须由 lib/dataRights 生成，否则 flag 与文案会分叉');
});

test('render loop evaluates function bodies instead of handing them to React', () => {
  // 第 5 条是函数，其它条目是字符串；渲染处必须显式求值，否则 /legal/privacy 整页抛
  // 「Functions are not valid as a React child」。这类回归不会让任何单元测试变红，
  // 因为 lib 层的文案函数自己是对的。
  assert.match(LEGAL_SOURCE, /typeof\s+body\s*===\s*'function'\s*\?\s*body\(/,
    'LegalPage 的 sections 渲染必须对函数型 body 求值');
});

test('flag only turns on for the literal string true', () => {
  assert.equal(isDataRightsEnabled({ VITE_DATA_RIGHTS_UI: 'true' }), true);
  // 拼错配置必须退到「未上线」那一侧：这里的默认值是安全默认（不承诺能力）
  for (const env of [{}, undefined, { VITE_DATA_RIGHTS_UI: 'TRUE' }, { VITE_DATA_RIGHTS_UI: '1' }, { VITE_DATA_RIGHTS_UI: '' }]) {
    assert.equal(isDataRightsEnabled(env), false, `flag 误开：${JSON.stringify(env)}`);
  }
  // 这里原先钉着一个后端 flag 名（data_rights_self_service），但后端从来没有它：
  // routes/data_rights_routes.py 进镜像即常驻。常量指的是 lib/flags.js 的注册项，
  // 所以断言改成「必须真的登记过」—— 否则 flag 层与文案层就读的是两个不同的位。
  assert.equal(DATA_RIGHTS_FLAG, 'dataRights');
  assert.equal(FLAG_DEFS[DATA_RIGHTS_FLAG]?.envKey, 'VITE_DATA_RIGHTS_UI');
});

test('support email must look like an email', () => {
  assert.equal(supportEmail({ VITE_SUPPORT_EMAIL: ' hi@x.test ' }), 'hi@x.test');
  assert.equal(supportEmail({ VITE_SUPPORT_EMAIL: 'not-an-email' }), null);
  assert.equal(supportEmail({ VITE_SUPPORT_EMAIL: '' }), null);
  assert.equal(supportEmail({}), null);
  assert.equal(supportEmail(undefined), null);
});

test('unverified-availability copy never promises self-service', () => {
  for (const zh of [true, false]) {
    const noEmail = dataRightsStatement({ selfService: false, email: null }, zh);
    const withEmail = dataRightsStatement({ selfService: false, email: 'hi@x.test' }, zh);
    for (const copy of [noEmail, withEmail]) {
      assert.ok(!/自助|self[- ]?service|30 天|grace period/i.test(copy), `端点未上线却承诺了自助/宽限期：${copy}`);
      // 「登出后令牌失效」是既成事实，三种状态都必须保留
      assert.match(copy, zh ? /登出后访问令牌即失效/ : /invalidated on logout/);
    }
    assert.match(noEmail, zh ? /帮助与反馈/ : /Help & feedback/, '无邮箱时必须指向站内真实存在的通道');
    assert.match(withEmail, /hi@x\.test/);
  }
});

test('self-service copy names the entry point and the grace period', () => {
  const zh = dataRightsStatement({ selfService: true }, true);
  assert.match(zh, /数据与隐私/);
  assert.match(zh, /30 天宽限期/);
  assert.match(dataRightsStatement({ selfService: true }, false), /Data & privacy/);
  // 自助已上线时不该再把人支去邮箱
  assert.doesNotMatch(zh, /@/);
});

test('privacyRightsCopy reads exactly the two env knobs and nothing else', () => {
  assert.equal(
    privacyRightsCopy({ VITE_DATA_RIGHTS_UI: 'true', VITE_SUPPORT_EMAIL: 'hi@x.test' }, true),
    dataRightsStatement({ selfService: true, email: 'hi@x.test' }, true),
  );
  assert.equal(
    privacyRightsCopy({ VITE_SUPPORT_EMAIL: 'hi@x.test' }, false),
    dataRightsStatement({ selfService: false, email: 'hi@x.test' }, false),
  );
  assert.equal(privacyRightsCopy(undefined, true), dataRightsStatement({ selfService: false, email: null }, true));
});
