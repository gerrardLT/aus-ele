// web/src/lib/dataRights.js
// 隐私政策「用户权利」条的文案生成器（R6.4 顺序约束 + R1.7 数据权利端点）。
//
// 为什么这段文案要生成而不是直接写字面量：这一条陈述的**真假取决于端点是否在线**。
// Spec §102/§232 要求「文案修正必须早于端点」，因为端点不存在时写「可申请导出或删除」
// 是不实陈述（在欧盟/澳洲属 APP 与 ACL 层面的实质性问题）。但把字面量改成
// 「请通过邮箱申请」会在端点上线后反过来变成另一种不实陈述；而端点带 flag（R5.4 要求
// 新 UI 一律可零代码回滚）—— flag 关掉的那一小时里，写死的「自助导出」文案就又回到
// 撒谎状态。所以唯一的稳定解是让文案与它描述的那个开关读同一个位。

import { isFlagEnabled } from './flags.js';

/**
 * R1.7 自助导出/删除入口的 flag 名 —— 指向 lib/flags.js 注册表里的那一条。
 *
 * 这里曾经写着一个后端 flag 名（`data_rights_self_service`），但后端从来没有它：
 * `routes/data_rights_routes.py` 一旦进入镜像就常驻生效，没有任何布尔位可拧。留着这个
 * 名字会让排障的人去后端找一个不存在的开关，所以改成注册表名，由 flagsGuard 保证它真的在注册表里。
 */
export const DATA_RIGHTS_FLAG = 'dataRights';

/** flag 是否打开。判据收口在 lib/flags.js（只认字面量 'true'），此处不再自带一份解释规则。 */
export function isDataRightsEnabled(env) {
  return isFlagEnabled(env, DATA_RIGHTS_FLAG);
}

/** 对外联系邮箱；未配置时返回 null（调用方必须准备无邮箱时的说法）。 */
export function supportEmail(env) {
  const value = typeof env?.VITE_SUPPORT_EMAIL === 'string' ? env.VITE_SUPPORT_EMAIL.trim() : '';
  return value.includes('@') ? value : null;
}

/**
 * 隐私页第 5 条正文。三种状态各自只说自己成立的那半句：
 *
 * 1. 自助端点已上线 → 说清楚入口在哪、删除有宽限期（这是用户真正会据此行动的信息）；
 * 2. 未上线但配了联系邮箱 → 按 Spec 给的临时文案「可通过 {SUPPORT_EMAIL} 申请」；
 * 3. 两者都没有 → 指向站内真实存在的那条路（帮助与反馈页，HelpPage 走
 *    POST /api/v1/feedback）。绝不写「可申请导出或删除」这种没有承接方的承诺。
 *
 * 三种状态都保留「登出后访问令牌即失效」—— 那句是当前实现的既成事实，与端点无关。
 */
export function dataRightsStatement(state, zh = true) {
  const { selfService = false, email = null } = state || {};
  const tokenClause = zh ? '登出后访问令牌即失效。' : 'Tokens are invalidated on logout.';

  if (selfService) {
    const selfServiceClause = zh
      ? '可在账户中心「数据与隐私」自助导出你的全部账户数据，或提交删除请求；删除有 30 天宽限期，期内可撤销。'
      : 'You can export all of your account data, or request deletion, from Account → Data & privacy; deletions carry a 30-day grace period and can be cancelled within it.';
    return `${selfServiceClause}${zh ? '' : ' '}${tokenClause}`;
  }

  const requestClause = email
    ? (zh ? `可通过 ${email} 申请导出或删除账户数据。` : `You may request export or deletion of your account data via ${email}.`)
    : (zh ? '如需导出或删除账户数据，请登录后在「帮助与反馈」页提交请求。' : 'To export or delete your account data, sign in and submit a request on the Help & feedback page.');

  return `${requestClause}${zh ? '' : ' '}${tokenClause}`;
}

/** LegalPage 用：从 import.meta.env 组装判据（集中一处，便于测试替换）。 */
export function privacyRightsCopy(env, zh) {
  return dataRightsStatement({ selfService: isDataRightsEnabled(env), email: supportEmail(env) }, zh);
}
