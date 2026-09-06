// web/src/lib/flagsGuard.test.js
// R5.4 feature flag 层的三道门（2026-09-06）。
//
// 这三道门各自盯一类「只在出事那天才暴露」的缺陷：
//
// 1. **死 flag**：注册表里声明了、但代码里没人读。它的危害不是多余，而是误导 —— 线上出
//    问题时有人会去拧这个开关，而拧它什么都不会发生。flags.js 的注释把这条写成了判据，
//    注释不构成约束，这里才构成。
// 2. **未登记的开关**：某个组件直接写 `import.meta.env.VITE_SOMETHING_NEW === 'true'`，
//    绕开注册表。表现是控制台看不到它、没人知道它的默认值，回滚时漏掉。
// 3. **拧不动的 flag**：前端读得很欢，但部署链路上没有任何一处把这个变量传进构建 ——
//    这类 flag 等价于「写死在源码里的常量」。第 6 项断言专门抓它：VITE_* 只有构建期注入
//    这一条路，`web/Dockerfile` 没有对应 ARG 就等于生产永远拿不到运维设的值。
//    （本门首跑就抓出 VITE_DATA_RIGHTS_UI / VITE_LEGAL_* 不在 Dockerfile ARG 里：
//    docker 构建路径下这些开关全部失效，只有宿主机 npm run build 才生效。）

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { FLAG_DEFS, FLAG_NAMES, isFlagEnabled, unregisteredFlagKeys } from './flags.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(__dirname, '../..', '..');

// 非 flag 的构建期配置（密钥/端点/邮箱），它们不是布尔位，不该进开关注册表。
const DECLARED_CONFIG = new Set([
  'VITE_API_BASE',
  'VITE_BOOTSTRAP_SECRET',
  'VITE_SUPPORT_EMAIL',
  'VITE_LEGAL_ENTITY_NAME',
  'VITE_LEGAL_ABN',
  'VITE_LEGAL_JURISDICTION',
  'VITE_ANALYTICS_SDK_URL',
  'VITE_ANALYTICS_TOKEN',
  'VITE_ANALYTICS_HOST',
]);

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, out);
    else out.push(abs);
  }
  return out;
}

function rel(abs) {
  return path.relative(SRC_ROOT, abs).split(path.sep).join('/');
}

/** 被测源码：排除测试自身与 __tests__ 目录（测试里引用 flag 名不算「有读者」）。 */
function appSources() {
  return walk(SRC_ROOT)
    .filter((f) => /\.jsx?$/.test(f))
    .filter((f) => !f.endsWith('.test.js'))
    .filter((f) => !rel(f).startsWith('__tests__/'))
    .filter((f) => !rel(f).includes('/__tests__/'));
}

const SOURCES = appSources().map((f) => ({ rel: rel(f), body: fs.readFileSync(f, 'utf8') }));

test('flag registry defaults are all off (new UI must be opt-in)', () => {
  assert.ok(FLAG_NAMES.length >= 1, '注册表不应为空');
  for (const name of FLAG_NAMES) {
    assert.equal(FLAG_DEFS[name].default, false, `${name} 的默认值必须是 false：未验收的新界面不能默认存在`);
  }
  // 空 env 下全关，是最基础的一次交叉验证
  for (const name of FLAG_NAMES) {
    assert.equal(isFlagEnabled({}, name), false, `${name} 在空配置下必须关闭`);
    assert.equal(isFlagEnabled(undefined, name), false, `${name} 在 env 缺失时必须关闭`);
  }
});

test('every flag carries an explanation the console can render', () => {
  for (const name of FLAG_NAMES) {
    const def = FLAG_DEFS[name];
    for (const field of ['envKey', 'controls', 'offState']) {
      assert.equal(typeof def[field], 'string', `${name}.${field} 缺失`);
      assert.ok(def[field].trim().length >= 4, `${name}.${field} 不能是占位文本`);
    }
    assert.match(def.envKey, /^VITE_[A-Z0-9_]+$/, `${name}.envKey 命名不符合构建期注入约定`);
    for (const dep of def.requires || []) {
      assert.ok(FLAG_DEFS[dep], `${name} 依赖未登记的 flag：${dep}`);
      assert.notEqual(dep, name, `${name} 不能依赖自身`);
    }
  }
});

test('no dead flags: every registered name has a reader outside the registry', () => {
  const offenders = [];
  for (const name of FLAG_NAMES) {
    const { envKey } = FLAG_DEFS[name];
    const quotedName = new RegExp(`['"\`]${name}['"\`]`);
    const reader = SOURCES.find((s) => {
      if (s.rel === 'lib/flags.js') return false;
      return s.body.includes(envKey) || quotedName.test(s.body);
    });
    if (!reader) offenders.push(`${name} (${envKey})`);
  }
  assert.deepEqual(offenders, [], '注册了却没人读的 flag 必须删除或接线');
});

test('no source file bypasses the registry with its own VITE_ boolean switch', () => {
  const registered = new Set(FLAG_NAMES.map((n) => FLAG_DEFS[n].envKey));
  const offenders = [];
  for (const s of SOURCES) {
    if (s.rel === 'lib/flags.js') continue;
    for (const m of s.body.matchAll(/\bVITE_[A-Z0-9_]+\b/g)) {
      const key = m[0];
      if (!registered.has(key) && !DECLARED_CONFIG.has(key)) {
        offenders.push(`${s.rel} :: ${key}`);
      }
    }
  }
  assert.deepEqual([...new Set(offenders)].sort(), [], '新增开关请先登记进 FLAG_DEFS，新增配置项请同步加进 DECLARED_CONFIG');
});

test('only the literal string true turns a flag on', () => {
  for (const name of FLAG_NAMES) {
    const def = FLAG_DEFS[name];
    // 带依赖的 flag 要连父项一起点亮，否则测的是依赖链而不是本项的解释规则
    const env = {};
    for (const dep of [name, ...(def.requires || [])]) env[FLAG_DEFS[dep].envKey] = 'true';
    for (const bad of ['1', 'yes', 'TRUE', 'True', 'on', 'true1', ' truex', '  ']) {
      const candidate = { ...env, [def.envKey]: bad };
      assert.equal(isFlagEnabled(candidate, name), false, `${name} 被误开：${JSON.stringify(bad)}`);
    }
    assert.equal(isFlagEnabled({ ...env, [def.envKey]: 'true' }, name), true, `${name} 的字面量 true 未生效`);
    assert.equal(isFlagEnabled({ ...env, [def.envKey]: ' true ' }, name), true, '两侧空白应被忽略');
  }
  // 未注册的名字一律关闭：拼错 flag 名不能点亮任何功能
  assert.equal(isFlagEnabled({ VITE_ANYTHING: 'true' }, 'typoFlag'), false);
});

test('requires is a hard constraint, not documentation', () => {
  const child = FLAG_NAMES.find((n) => (FLAG_DEFS[n].requires || []).length);
  assert.ok(child, '至少应有一个带依赖的 flag，否则本门失去意义');
  const parents = FLAG_DEFS[child].requires;
  const env = { [FLAG_DEFS[child].envKey]: 'true' };
  for (const p of parents) env[FLAG_DEFS[p].envKey] = 'true';
  assert.equal(isFlagEnabled(env, child), true);
  for (const p of parents) {
    const partial = { ...env, [FLAG_DEFS[p].envKey]: 'false' };
    assert.equal(isFlagEnabled(partial, child), false, `父 flag ${p} 关掉后 ${child} 仍开着`);
  }
});

test('unregisteredFlagKeys reports nothing for the shipped config surface', () => {
  // 真实配置文件里出现的开关必须全部可枚举 —— 否则控制台上的开关清单是不完整的。
  const env = {};
  for (const file of ['web/.env.production', '.env.example']) {
    const abs = path.join(REPO_ROOT, file);
    if (!fs.existsSync(abs)) continue;
    for (const line of fs.readFileSync(abs, 'utf8').split('\n')) {
      const m = line.match(/^\s*(VITE_[A-Z0-9_]+)\s*=/);
      if (m) env[m[1]] = 'true';
    }
  }
  const strays = unregisteredFlagKeys(env);
  assert.deepEqual(strays, [], `配置文件里存在未登记开关：${strays.join(', ')}`);
});

test('every flag is actually reachable by ops through the build pipeline', () => {
  const dockerfile = fs.readFileSync(path.join(REPO_ROOT, 'web', 'Dockerfile'), 'utf8');
  const compose = fs.readFileSync(path.join(REPO_ROOT, 'docker-compose.yml'), 'utf8');
  // 生产镜像是 CI 构建的（docker-compose.prod.yml 只 pull 现成镜像），所以「compose 里有」
  // 仍然不等于拧得动 —— 本轮真实漏的就是这一环：CI 只传了 VITE_BOOTSTRAP_SECRET。
  const ci = fs.readFileSync(path.join(REPO_ROOT, '.github', 'workflows', 'ci.yml'), 'utf8');
  // 第四道：CI 把 vars 注入环境变量后，还要靠那个 `for key in ...` 循环逐个转成 --build-arg。
  // 只查上一项会漏 —— 「vars 里有」而「循环里没有」的结果同样是构建拿到默认值，
  // 且现象与「运维忘了设」完全一样，是这四段里最难被发现的一段。
  const loopBlock = /for key in([\s\S]*?); do/.exec(ci);
  const loopKeys = new Set((loopBlock ? loopBlock[1] : '').replace(/\\\s*/g, ' ').split(/\s+/).filter(Boolean));
  assert.ok(loopKeys.size >= 10, `未解析到 CI 的 --build-arg 循环（只看到 ${loopKeys.size} 个键）—— 门本身失效了`);
  const missing = [];
  for (const name of FLAG_NAMES) {
    const { envKey } = FLAG_DEFS[name];
    if (!new RegExp(`ARG\\s+${envKey}\\b`).test(dockerfile)) missing.push(`${envKey} (Dockerfile ARG)`);
    if (!new RegExp(`${envKey}:`).test(compose)) missing.push(`${envKey} (compose build arg)`);
    if (!new RegExp(`\\$\\{\\{\\s*vars\\.${envKey}\\s*\\}\\}`).test(ci)) missing.push(`${envKey} (ci.yml vars)`);
    if (!loopKeys.has(envKey)) missing.push(`${envKey} (ci.yml --build-arg 循环)`);
  }
  assert.deepEqual(missing, [], '前端只有构建期一条注入路径，缺 ARG 的 flag 在生产等于写死的常量');
});

test('the build pipeline exposes no knob the registry does not know', () => {
  // 反方向：CI 里有一个没人读的 VITE_ 变量，比没有更糟 —— 有人会去拧它并相信它生效了。
  const ci = fs.readFileSync(path.join(REPO_ROOT, '.github', 'workflows', 'ci.yml'), 'utf8');
  const known = new Set([...FLAG_NAMES.map((n) => FLAG_DEFS[n].envKey), ...DECLARED_CONFIG]);
  const strays = [...ci.matchAll(/\$\{\{\s*vars\.(VITE_[A-Z0-9_]+)\s*\}\}/g)].map((m) => m[1]);
  assert.deepEqual(
    [...new Set(strays)].filter((k) => !known.has(k)),
    [],
    'ci.yml 里的 vars 开关必须能在 flags.js 注册表或已声明配置里找到对应项',
  );
});
