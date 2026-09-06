// web/src/lib/oauthReturn.js
// 社交登录回调落地（R1.2，2026-09-06）。
//
// 后端 /api/v1/auth/oauth/{provider}/callback 完成 code exchange 后用 302 把会话凭据
// 放在 URL **fragment** 里送回 /login。选 fragment 而不是 query 是 OAuth 的既有标准做
// 法：query 会进服务端访问日志、反代日志与 Referer，fragment 从不出浏览器。
//
// 但「不出浏览器」不等于安全：它会留在浏览器会话历史里，并且任何人都能在地址栏粘贴
// 一个伪造的 #oauth_access_token=... 来触发这里的逻辑。因此本模块承担三件事：
// 1. 读一次就抹（consumeOAuthHash：replaceState 清历史，避免令牌留在前进/后退里）；
// 2. 只接受后端确实会写出的键，其余一律忽略（不给未知键赋予语义）；
// 3. return_to **再校验一次**：后端已做站内外判定，但这一值最终会变成前端跳转目标，
//    而跳转目标校验属于「谁使用谁负责」——客户端不能因为上游做过检查就省掉自己的门。

const FRAGMENT_PREFIX = 'oauth_';

/** 后端 callback 写出的错误码 → 文案。未知码走兜底，不给「未知错误码」编造原因。 */
const ERROR_COPY = {
  state_invalid: ['登录请求已过期，请重新发起', 'Login request expired, please try again'],
  provider_denied: ['已取消社交登录授权', 'Social login authorization was cancelled'],
  email_unverified: ['该社交账号的邮箱未经提供方验证，无法用于登录',
    'The email on that social account is not verified by the provider'],
  upstream_unavailable: ['社交登录服务暂时不可用，请稍后重试',
    'Social login provider is temporarily unavailable, please retry'],
  provider_misconfigured: ['社交登录入口配置有误，请联系管理员',
    'Social login is misconfigured, please contact support'],
  no_workspace: ['该账号尚未加入任何工作空间，请通过邀请链接加入',
    'This account has no workspace yet. Please join via an invitation link'],
  account_unavailable: ['该账号不可用，请联系管理员',
    'This account is unavailable, please contact support'],
};

const FALLBACK_COPY = ['社交登录失败，请改用邮箱登录', 'Social login failed, please sign in with email'];

function decodeHash(rawHash) {
  const raw = String(rawHash || '').replace(/^#/, '');
  if (!raw) return {};
  const params = new URLSearchParams(raw);
  const out = {};
  for (const [key, value] of params) out[key] = value;
  return out;
}

/**
 * 站内相对路径校验：拒绝 `//host`（协议相对）、带 scheme、反斜杠、CR/LF。
 * 规则与后端 ``oauth_routes._sanitize_return_to`` 同源 —— 两端各留一份是刻意的，
 * 因为它们在不同位置生效（服务端在写入前、客户端在跳转前），任何一端被绕过
 * 都不应该让另一端跟着失守。
 */
export function sanitizeReturnTo(value) {
  const input = String(value || '').trim();
  if (!input) return '';
  if (!input.startsWith('/')) return '';
  if (input.startsWith('//')) return '';
  if (input.includes('\\') || /[\r\n]/.test(input)) return '';
  try {
    // 以浏览器自己的解析语义再判一次：只有仍落在同一个占位 origin 上的值才算站内路径。
    // 上面几条是给人看的规则，这一条是给规则兜底的（规则漏了哪种写法，origin 都会发现）。
    if (new URL(input, 'https://in-app.invalid').origin !== 'https://in-app.invalid') return '';
  } catch {
    return '';
  }
  return input.slice(0, 200);
}

/**
 * 解析回调 fragment（纯函数，不碰全局对象）。
 * @returns {{kind:'session',...}|{kind:'error',code:string,provider:string}|null}
 */
export function parseOAuthHash(rawHash) {
  const params = decodeHash(rawHash);
  // 连一个 oauth_ 键都没有 → 这个 fragment 与本模块无关（例如页面自己的锚点）。
  const touched = Object.keys(params).some((key) => key.startsWith(FRAGMENT_PREFIX));
  if (!touched) return null;

  const provider = String(params[`${FRAGMENT_PREFIX}provider`] || '').slice(0, 40);
  const errorCode = String(params[`${FRAGMENT_PREFIX}error`] || '').slice(0, 60);
  if (errorCode) return { kind: 'error', code: errorCode, provider };

  const accessToken = String(params[`${FRAGMENT_PREFIX}access_token`] || '');
  const sessionToken = String(params[`${FRAGMENT_PREFIX}session_token`] || '');
  const workspaceId = String(params[`${FRAGMENT_PREFIX}workspace_id`] || '');
  // 三者缺一即视为无效：一个「像 token 的字符串」不构成会话（后端签发的会话必然三者齐全）。
  if (!accessToken || !sessionToken || !workspaceId) return null;

  const expiresIn = Number.parseInt(params[`${FRAGMENT_PREFIX}access_token_expires_in`], 10);
  return {
    kind: 'session',
    accessToken,
    sessionToken,
    workspaceId,
    provider,
    expiresIn: Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn : 3600,
    returnTo: sanitizeReturnTo(params[`${FRAGMENT_PREFIX}return_to`]),
  };
}

/**
 * 读取并立即从历史中抹掉回调凭据。
 * @param {{hash:string}} locationLike
 * @param {{replaceState?:Function}} historyLike
 */
export function consumeOAuthHash(locationLike = globalThis.location, historyLike = globalThis.history) {
  const parsed = parseOAuthHash(locationLike?.hash);
  if (!parsed) return null;
  try {
    const base = `${locationLike.pathname || '/'}${locationLike.search || ''}`;
    // 失败分支同样要抹：错误码虽不敏感，但「点后退又看到一次报错」是可感知的毛病。
    historyLike?.replaceState?.(null, '', base);
  } catch {
    /* replaceState 在个别沙箱环境会抛；抹不掉也不能让登录中断 */
  }
  return parsed;
}

/** 发起授权：一个 <a href> 即可，无需 JS（后端 GET + 302）。 */
export function socialStartUrl(apiBase, providerKey, returnTo) {
  const base = String(apiBase || '').replace(/\/+$/, '');
  const key = encodeURIComponent(String(providerKey || '').slice(0, 40));
  const target = sanitizeReturnTo(returnTo);
  return `${base}/auth/oauth/${key}/start${target ? `?next=${encodeURIComponent(target)}` : ''}`;
}

export function oauthErrorCopy(code, zh) {
  const entry = ERROR_COPY[String(code || '')];
  const [zhText, enText] = entry || FALLBACK_COPY;
  return zh ? zhText : enText;
}

/**
 * 拉取已配置的社交登录入口。
 * 失败一律返回空数组：这是个渐进增强入口，网络异常时按钮不出现即可，
 * 绝不能让登录页本身报错（邮箱登录必须永远可用）。
 */
export async function fetchSocialProviders(apiBase, fetchImpl = globalThis.fetch) {
  try {
    const base = String(apiBase || '').replace(/\/+$/, '');
    const res = await fetchImpl(`${base}/auth/oauth/providers`);
    if (!res.ok) return [];
    const body = await res.json();
    const providers = Array.isArray(body?.providers) ? body.providers : [];
    return providers
      .filter((item) => item && typeof item.key === 'string' && typeof item.label === 'string')
      .slice(0, 10);
  } catch {
    return [];
  }
}
