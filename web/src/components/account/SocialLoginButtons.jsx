// web/src/components/account/SocialLoginButtons.jsx
// 社交登录入口（R1.2，2026-09-06）。
//
// 三条刻意的取舍：
// 1. **未配置的提供方不渲染**：判据来自后端 ``GET /auth/oauth/providers``，即「服务端 env
//    里有没有 client_id/secret」。前端因此不需要（也不允许）知道任何 client_id —— 环境
//    开关只有一处真值，前端不会出现「按钮在但点了 404」。
// 2. **用 <a href> 而不是 JS 跳转**：后端 /start 是 GET + 302，无 JS、脚本被拦、或网络
//    扩展改写 fetch 的环境下依然能登录。
// 3. **不放品牌图标**：官方 logo 有商标使用规范，且这里没有内嵌 SVG 的必要；文字按钮
//    「使用 Google 继续」在可读性和点击目标上都更稳。

import { useEffect, useState } from 'react';
import { getApiBase } from '../../lib/apiBase.js';
import { fetchSocialProviders, socialStartUrl } from '../../lib/oauthReturn.js';

const API_BASE = getApiBase();

export default function SocialLoginButtons({ zh = true, returnTo = '', disabled = false }) {
  const [providers, setProviders] = useState([]);

  useEffect(() => {
    let cancelled = false;
    fetchSocialProviders(API_BASE).then((list) => {
      if (!cancelled) setProviders(list);
    });
    return () => { cancelled = true; };
  }, []);

  if (providers.length === 0) return null;

  return (
    <div className="space-y-2 border-t border-[var(--color-border)] pt-3">
      <p className="text-center text-[11px] text-[var(--color-muted)]">
        {zh ? '或使用社交账号' : 'Or continue with'}
      </p>
      {providers.map((provider) => (
        <a
          key={provider.key}
          href={disabled ? undefined : socialStartUrl(API_BASE, provider.key, returnTo)}
          aria-disabled={disabled ? true : undefined}
          onClick={disabled ? (event) => event.preventDefault() : undefined}
          className={`block w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-center text-xs font-semibold text-[var(--color-text)] transition-opacity hover:opacity-80 ${disabled ? 'pointer-events-none opacity-50' : ''}`}
        >
          {zh
            ? `使用 ${provider.label} 继续`
            : `Continue with ${provider.label}`}
        </a>
      ))}
    </div>
  );
}
