// web/src/lib/accountNotices.js
// 匿名/未验证状态下的提示判据（R1.9 + R1.1 前端 banner，2026-09-06）。
//
// 为什么把判据抽成纯函数：这是「什么情况下该对用户说什么」的业务规则，散进 JSX 三元
// 之后就没法测，而它的错误恰恰是用户可感知的（把已验证用户长期挂着「去验证」横幅，
// 或者反过来让匿名访客看不到注册入口）。组件只负责渲染。
//
// 三条判据：
// 1. 匿名 → 提示注册可解锁的能力（这是公测期的主转化位，不可关掉就不再出现）；
// 2. 已登录但邮箱未验证 → 提示验证（R1.1 把未验证定为**软限制**，所以这里是引导不是拦截）；
// 3. 状态未知（拉取失败）→ **什么都不显示**。一个「不确定却常驻」的横幅比没有横幅更糟：
//    用户会据此判断自己的账号状态，而我们在撒谎。

const DISMISS_STORE_KEY = 'aus_account_notice_dismissed_v1';

const COPY = {
  anonymous: {
    title: ['免费注册后可保存视图、接收价格异动提醒并导出报告', 'Create a free account to save views, get price alerts and export reports'],
    body: ['匿名访问不会保存任何数据，也不会有告警。', 'Anonymous visits save nothing and receive no alerts.'],
    cta: ['创建账号', 'Create account'],
    href: '/register',
  },
  unverified: {
    title: ['邮箱尚未验证', 'Email not verified yet'],
    body: ['验证后才能稳定接收告警与报告邮件。链接 24 小时内有效。', 'Verify your email so alerts and reports reach your inbox. The link is valid for 24 hours.'],
    cta: ['去验证邮箱', 'Verify email'],
    href: '/account',
  },
};

/** 关闭状态的有效期：过期后横幅重新出现（见 noticeFor 内的理由）。 */
export const DISMISS_TTL_MS = 14 * 24 * 60 * 60 * 1000;

/**
 * @param {{hasSession:boolean, emailVerified:boolean|null, dismissed?:Record<string,*>}} state
 *        emailVerified 为 null 表示状态未知（尚未拉到 / 拉取失败）；
 *        dismissed 的值是关闭时刻的 epoch 毫秒
 * @returns {{kind:string,title:string,body:string,ctaLabel:string,href:string}|null}
 */
export function noticeFor(state, zh = true, nowMs = Date.now()) {
  const { hasSession, emailVerified, dismissed } = state || {};
  const kind = !hasSession ? 'anonymous' : (emailVerified === false ? 'unverified' : null);
  if (!kind) return null;
  // 「关闭」不等于「永不再提」：这条横幅讲的是用户当下用不了的能力，而公测期的能力
  // 一直在增加。永久静默会让半年前随手关掉的人永远看不到新入口。
  const closedAt = Number(dismissed?.[kind]);
  if (Number.isFinite(closedAt) && nowMs - closedAt < DISMISS_TTL_MS) return null;
  const entry = COPY[kind];
  const pick = (pair) => (zh ? pair[0] : pair[1]);
  return {
    kind,
    title: pick(entry.title),
    body: pick(entry.body),
    ctaLabel: pick(entry.cta),
    href: entry.href,
  };
}

/**
 * 读取当前会话的邮箱验证状态。
 * 返回 null 表示「未知」而不是 false —— 这是本模块唯一的诚实性约束：把失败折叠成
 * false 会让每个拉取失败的用户都看到「去验证邮箱」，包括刚刚验证完的人。
 */
export async function fetchVerificationStatus(apiBase, accessToken, fetchImpl = globalThis.fetch) {
  if (!accessToken) return null;
  try {
    const base = String(apiBase || '').replace(/\/+$/, '');
    const res = await fetchImpl(`${base}/register/status`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!res.ok) return null;
    const body = await res.json();
    return typeof body?.email_verified === 'boolean' ? body.email_verified : null;
  } catch {
    return null;
  }
}

// -- 关闭状态持久化（storage 由调用方注入，方便测试与 SSR 环境缺 localStorage） --

export function readDismissed(storageLike) {
  try {
    const raw = storageLike?.getItem?.(DISMISS_STORE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function writeDismissed(storageLike, kind, nowMs = Date.now()) {
  try {
    // 顺手剪掉已过期的条目：不剪的话这个对象会随 kind 数量与时间单调增长。
    const previous = readDismissed(storageLike);
    const next = {};
    for (const [key, value] of Object.entries(previous)) {
      const at = Number(value);
      if (Number.isFinite(at) && nowMs - at < DISMISS_TTL_MS) next[key] = at;
    }
    next[kind] = nowMs;
    storageLike?.setItem?.(DISMISS_STORE_KEY, JSON.stringify(next));
    return next;
  } catch {
    return readDismissed(storageLike);
  }
}
