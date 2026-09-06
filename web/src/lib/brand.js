// web/src/lib/brand.js
// 单一品牌常量层（R2.1，2026-09-06 公测产品化改造）。
//
// 为什么要有一层常量而不是各页各写一遍：改名前「AEMO Intelligence」在前端 12 处、后端
// 14 处各自硬编码，其中 3 处还是大小写变体（顶栏 / eyebrow / 页脚）。改名时漏掉任何一处
// 都会留下一个仍然写着旧名字的真实页面 —— 而品牌名同时是法务陈述的一部分（服务条款第 1
// 条要说清「谁在提供服务」），漏一处就等于界面上出现两个不同的合同主体。
//
// 与法务的关键区分（本轮改名的立足点）：**产品品牌名** 与 **数据源名** 是两件事。
// 「天枢 / Tianshu」是产品名；「AEMO」是 Australian Energy Market Operator 的缩写，是我们
// 分析的公开数据来源之一，永远不该被改名波及 —— 恰恰相反，法务要求我们**显式保留**它并
// 声明无从属/背书关系（见 AEMO_NON_AFFILIATION）。
//
// 本模块刻意不读 import.meta.env：品牌名必须构建期即确定、且能在 node:test 里被直接 import
// （node 环境下 `import.meta.env` 是 undefined，模块顶层碰它会让整条 lib 测试链崩掉）。
// 需要外部配置的只有运营主体与联系邮箱，一律走下面接受 env 形参的函数。

import { supportEmail } from './dataRights.js';

/** 中文品牌名。 */
export const BRAND_NAME_ZH = '天枢';
/** 拉丁品牌名（北斗第一星「天枢」的拼音；中英双语指向同一个名字，不做两套拉丁化）。 */
export const BRAND_NAME_EN = 'Tianshu';

/** 一句话品类描述 —— 品牌名之下必须跟着「这是干什么的」，纯星名对用户零信息量。 */
export const BRAND_SUBTITLE_ZH = '澳洲电力市场与储能决策平台';
export const BRAND_SUBTITLE_EN = 'Australian electricity market & battery decision platform';

/**
 * 顶栏/页脚/邮件的完整字标。
 *
 * 中文场景带拉丁名是有意的：域名、App Store 检索与海外合作方看到的都是 Tianshu，
 * 中英并排可以让「天枢 = Tianshu」这一件事在每一次曝光里自动完成绑定。
 */
export function brandLockup(zh = true) {
  return zh ? `${BRAND_NAME_ZH} ${BRAND_NAME_EN}` : BRAND_NAME_EN;
}

/** eyebrow 小字（大写 + 字距）用的短字标；中文不需要 uppercase，直接用中文名。 */
export function brandEyebrow(zh = true) {
  return zh ? BRAND_NAME_ZH : BRAND_NAME_EN;
}

export function brandSubtitle(zh = true) {
  return zh ? BRAND_SUBTITLE_ZH : BRAND_SUBTITLE_EN;
}

/** 页面 <title>：品牌 + 品类。`web/index.html` 的静态 title 必须逐字含此串（由测试锁定）。 */
export const DOCUMENT_TITLE_ZH = `${BRAND_NAME_ZH} ${BRAND_NAME_EN} \u2014 澳洲储能与电池投资决策平台`;
export const DOCUMENT_TITLE_EN = `${BRAND_NAME_EN} \u2014 BESS investment decision platform`;

export function documentTitle(zh = true) {
  return zh ? DOCUMENT_TITLE_ZH : DOCUMENT_TITLE_EN;
}

/** AI 决策引擎入口名（侧边栏 / Agent 页 / 引导流程 / 报告页脚共用）。 */
export function agentLabel(zh = true) {
  return zh ? `${BRAND_NAME_ZH} · AI 决策引擎` : `${BRAND_NAME_EN} · Decision Engine`;
}

/** 引导流程欢迎语（OnboardingTour 第一步标题）。 */
export function brandWelcome(zh = true) {
  return zh ? `欢迎使用 ${BRAND_NAME_ZH}` : `Welcome to ${BRAND_NAME_EN}`;
}

/**
 * 导出报告 / PDF 预览的页眉字标。
 *
 * 报告是会被转发给第三方看的产物，页眉必须同时出现「谁生成的」与「数据来源」，但**不能**
 * 出现任何暗示 AEMO 授权的字序 —— 旧值 `AEMO Intelligence · 天枢 · AI 决策引擎` 把机构缩写
 * 放在最前面，读者第一反应是官方产品。
 */
export function reportEyebrow(zh = true) {
  return zh ? `${BRAND_NAME_ZH} ${BRAND_NAME_EN} · AI 决策引擎` : `${BRAND_NAME_EN} · AI Decision Engine`;
}

/**
 * 侧边栏/页脚里的 `nav.brand` 值（`translations.js` 的两个字面量必须与此同义）。
 *
 * 为什么品牌名还留在 translations.js 而不是 import 过来：`translations.js` 被
 * `finlandBoard.test.js` / `gridForecast.test.js` 用源码字面量锁死结构，任何 import 或拆文件
 * 都会撞那条硬门。所以值仍写字面量，由 `brandConsistency.test.js` 负责盯住它是否过期。
 */
export function navBrand(zh = true) {
  return zh ? `${BRAND_NAME_ZH} · 澳洲电网智能观测站` : `${BRAND_NAME_EN.toUpperCase()} · GRID INTELLIGENCE`;
}

/**
 * 曾用名。只有法务文本需要它（服务条款要说明品牌变更不影响服务连续性），
 * 因此它是常量层的一部分，而不是在 LegalPage 里再抄一份字面量。
 *
 * 本数组同时是全库扫描唯一的豁免位：`brandConsistency.test.js` 允许这两个文件出现旧名 ——
 * 一个解释「为什么禁止写 X」的规则，和一个声明「我们以前叫 X」的法律文本，都必须能说 X。
 */
export const FORMER_BRAND_NAMES = Object.freeze(['AEMO Intelligence']);

/** 后端邮件主题前缀的镜像值 —— 必须与 `backend/brand.py` 的 `EMAIL_SUBJECT_PREFIX` 逐字相同。 */
export const EMAIL_SUBJECT_PREFIX = '[天枢]';

/**
 * 非背书声明（R2.4 法务补全的核心一句）。
 *
 * 这句是本轮改名的真正动机之一：旧品牌名把数据提供方的机构缩写当成自己的产品名，读起来
 * 像「AEMO 官方智能平台」。改名只解决了暗示，明示仍须写在合同文本里。
 */
export function aemoNonAffiliation(zh = true) {
  return zh
    ? '本产品与 Australian Energy Market Operator (AEMO) 无从属、授权或背书关系；AEMO 为本产品分析的公开数据来源之一，其商标与版权归属原机构。'
    : 'This product is not affiliated with, endorsed by, or sponsored by the Australian Energy Market Operator (AEMO). AEMO is one of the public data sources analysed by this product; its name and marks belong to their owner.';
}

/**
 * 运营主体信息。
 *
 * **刻意没有内置默认值**：法人名称与 ABN/ACN 是对外可核验的法律事实，写进代码就等于伪造。
 * 未配置时法务页渲染成「主体与登记号待公示」这句诚实的话（见 legalEntityStatement）——
 * 一句「还没有」的法律陈述是真的，一个编出来的 11 位 ABN 是刑事级别的问题。
 */
export const LEGAL_ENTITY_ENV = {
  name: 'VITE_LEGAL_ENTITY_NAME',
  abn: 'VITE_LEGAL_ABN',
  jurisdiction: 'VITE_LEGAL_JURISDICTION',
};

export function legalEntity(env) {
  const pick = (key) => {
    const value = typeof env?.[key] === 'string' ? env[key].trim() : '';
    return value || null;
  };
  return {
    name: pick(LEGAL_ENTITY_ENV.name),
    abn: pick(LEGAL_ENTITY_ENV.abn),
    jurisdiction: pick(LEGAL_ENTITY_ENV.jurisdiction),
  };
}

/** ABN 是 11 位数字、ACN 是 8 位数字；配置里写错格式时按「未配置」处理，而不是照抄。 */
function normalizedAbn(value) {
  const digits = (value || '').replace(/[\s-]/g, '');
  return /^\d{11}$/.test(digits) ? digits : null;
}

/**
 * 服务条款第 1 条的主体句。三种配置完整度各有自己的说法，绝不补写没有的事实。
 */
export function legalEntityStatement(env, zh = true) {
  const entity = legalEntity(env);
  const abn = normalizedAbn(entity.abn);
  const name = entity.name;

  if (name && abn) {
    const jurisdictionClause = entity.jurisdiction
      ? (zh ? `，适用${entity.jurisdiction}法律管辖` : `, governed by the laws of ${entity.jurisdiction}`)
      : '';
    return zh
      ? `服务由 ${name}（ABN ${abn}${jurisdictionClause}）提供。`
      : `The Service is provided by ${name} (ABN ${abn}${jurisdictionClause ? ', ' + jurisdictionClause.slice(2) : ''}).`;
  }
  if (name) {
    return zh
      ? `服务由 ${name} 提供；其商业登记号（ABN/ACN）将在补齐后于本页公示。`
      : `The Service is provided by ${name}; its business registration number (ABN/ACN) will be published on this page once finalised.`;
  }
  return zh
    ? '服务由本平台运营方提供；运营主体名称与商业登记号（ABN/ACN）正在办理登记，完成前本节以「本平台运营方」指称。本条不构成对已登记主体的陈述。'
    : 'The Service is provided by the operator of this platform. The operator\'s legal name and business registration number (ABN/ACN) are pending registration; until published here, this page refers to it as "the platform operator". This clause is not a representation that a registered entity has been identified.';
}

/**
 * 联系入口（R2.5 修 CTA 断链用）。
 *
 * 定价页三个 CTA 原本全部指向 `/login`：一个已经在看套餐的人被送到登录页，登录失败又回
 * 到套餐页 —— 环里没有任何出口。这里给出「有邮箱走邮箱、没邮箱走站内反馈页」的退化序，
 * 保证任何配置下 CTA 都指向一个真实存在的承接方。
 */
export function contactHref(env, fallbackPath = '/help') {
  const email = supportEmail(env);
  return email ? `mailto:${email}` : fallbackPath;
}
