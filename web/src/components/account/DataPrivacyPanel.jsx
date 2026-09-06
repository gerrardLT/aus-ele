// web/src/components/account/DataPrivacyPanel.jsx
// R1.7 账户数据权利面板（2026-09-06）：自助导出 + 删除账户（软删除 + 宽限期撤销）。
//
// 三处不是「风格」而是必须这么做的实现决定：
//
// 1. **下载走 fetch + Blob，不走 <a href download>**。导出端点要求 Bearer 头，而浏览器
//    对 <a> 导航不会带 Authorization —— 用 <a> 的结果是一个必然 401 的下载链接，点了
//    什么也不会发生（并且多数浏览器不会报错）。
// 2. **入口的存在性由端点自己回答**（探测请求 404 → 收起），flag 只是必要条件。
//    后端 route 模块走 ROUTE_MODULES 尾部追加、单模块 import 失败不阻断其余模块
//    （Spec §234 点名这是「静默不上线」风险源）。只看 flag 会把界面铺在一个 404 上。
// 3. **删除受理后必须立刻落地到登录页**。后端受理成功的同时撤销全部会话与令牌，
//    不照这个位走，用户看到的就是一堵莫名其妙的登录墙，并会当成失败反复点。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getApiBase } from '../../lib/apiBase.js';
import { getValidAccessToken, tryRefreshToken } from '../../lib/authStore.js';
import { isDataRightsEnabled, supportEmail } from '../../lib/dataRights.js';
import {
  dataRightsEndpoints,
  deletionUiState,
  endpointUnavailable,
  exportUiState,
  graceDaysRemaining,
  mustReauthenticateAfterDeletion,
  ownershipBlockCopy,
  shouldPollExport,
} from '../../lib/dataRightsApi.js';

const API_BASE = getApiBase();
const POLL_INTERVAL_MS = 4000;
// 轮询上限：导出扫 17 张表，正常在几十秒内完成。设上限是因为无上限的轮询在作业永久
// 停在 queued（作业名漏注册）时会把账户页变成一个持续打 API 的机器。
const POLL_LIMIT = 40;

export default function DataPrivacyPanel({ lang = 'zh', onSessionEnded, env = import.meta.env }) {
  const zh = lang === 'zh';
  const endpoints = useMemo(() => dataRightsEndpoints(API_BASE), []);
  const flagOn = isDataRightsEnabled(env);
  const email = supportEmail(env);

  const [probe, setProbe] = useState(null);
  const [exportRow, setExportRow] = useState(null);
  const [deletionRow, setDeletionRow] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [block, setBlock] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const polls = useRef(0);

  const authHeaders = useCallback(async () => {
    const token = (await getValidAccessToken()) || (await tryRefreshToken());
    return token ? { Authorization: `Bearer ${token}` } : null;
  }, []);

  // 一次探测同时拿到「端点在不在线」与两份当前状态，省掉三次往返。
  const load = useCallback(async () => {
    if (!flagOn) return;
    const headers = await authHeaders();
    if (!headers) { setProbe(401); return; }
    try {
      const [exp, del] = await Promise.all([
        fetch(endpoints.exportStatus, { headers }),
        fetch(endpoints.deletionStatus, { headers }),
      ]);
      setProbe(exp.status);
      if (endpointUnavailable(exp.status)) return;
      const expBody = exp.ok ? await exp.json() : null;
      setExportRow(expBody && expBody.status === 'none' ? null : expBody);
      if (del.ok) {
        const delBody = await del.json();
        setDeletionRow(delBody && delBody.status === 'none' ? null : delBody);
      }
    } catch {
      setError(zh ? '网络错误' : 'Network error');
    }
  }, [flagOn, authHeaders, endpoints, zh]);

  useEffect(() => { load(); }, [load]);

  const exportState = exportUiState({ flagOn, probeStatusCode: probe, row: exportRow });
  const deletionState = deletionUiState(deletionRow);
  const remaining = graceDaysRemaining(deletionRow);

  // 完成后自动停止：超过上限就停下来让用户手动重试，而不是无声地一直转。
  useEffect(() => {
    if (exportState !== 'inflight') { polls.current = 0; return undefined; }
    const timer = setTimeout(async () => {
      polls.current += 1;
      if (polls.current > POLL_LIMIT) { setBusy(null); setError(zh ? '导出仍在进行，稍后刷新查看' : 'Export still running; refresh later'); return; }
      await load();
    }, POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [exportState, load, zh]);

  const startExport = useCallback(async () => {
    setBusy('export');
    setError(null);
    try {
      const headers = await authHeaders();
      if (!headers) { setError(zh ? '登录状态已失效' : 'Session expired'); return; }
      const res = await fetch(endpoints.exportSubmit, { method: 'POST', headers });
      if (!res.ok) { setError(`HTTP ${res.status}`); return; }
      const body = await res.json();
      if (!shouldPollExport(body)) { setError(body?.message || 'HTTP 200'); return; }
      await load();
    } catch {
      setError(zh ? '网络错误' : 'Network error');
    } finally {
      setBusy(null);
    }
  }, [authHeaders, endpoints, load, zh]);

  const downloadExport = useCallback(async () => {
    if (!exportRow?.export_id) return;
    setBusy('download');
    setError(null);
    try {
      const headers = await authHeaders();
      const res = await fetch(endpoints.exportDownload(exportRow.export_id), { headers });
      if (res.status === 410) { setError(zh ? '导出文件已过期，请重新生成' : 'Export file expired'); return; }
      if (!res.ok) { setError(`HTTP ${res.status}`); return; }
      // 带 Bearer 的下载只能自己拼一条 blob 链接：见文件头第 1 点。
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `account-export-${exportRow.export_id}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError(zh ? '网络错误' : 'Network error');
    } finally {
      setBusy(null);
    }
  }, [authHeaders, endpoints, exportRow, zh]);

  const requestDeletion = useCallback(async () => {
    setBusy('delete');
    setError(null);
    setBlock(null);
    try {
      const headers = await authHeaders();
      const res = await fetch(endpoints.deletionSubmit, { method: 'POST', headers });
      if (res.status === 409) {
        const detail = (await res.json().catch(() => ({})))?.detail;
        setBlock(detail?.code === 'ownership_transfer_required' ? ownershipBlockCopy(detail, zh) : (detail?.message || 'HTTP 409'));
        setConfirming(false);
        return;
      }
      if (!res.ok) { setError(`HTTP ${res.status}`); return; }
      const body = await res.json();
      if (mustReauthenticateAfterDeletion(body)) {
        // 令牌已经作废，把成功做成一个能读懂的界面：先交给上层跳登录页。
        onSessionEnded?.({ reason: 'deletion_pending', scheduled: body.scheduled_delete_at });
        return;
      }
      await load();
    } catch {
      setError(zh ? '网络错误' : 'Network error');
    } finally {
      setBusy(null);
    }
  }, [authHeaders, endpoints, load, onSessionEnded, zh]);

  const cancelDeletion = useCallback(async () => {
    setBusy('cancel');
    setError(null);
    try {
      const headers = await authHeaders();
      const res = await fetch(endpoints.deletionCancel, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(headers || {}) },
        body: JSON.stringify({ reason: 'user_cancelled' }),
      });
      if (!res.ok) { setError(`HTTP ${res.status}`); return; }
      setDeletionRow(await res.json());
      setConfirming(false);
    } catch {
      setError(zh ? '网络错误' : 'Network error');
    } finally {
      setBusy(null);
    }
  }, [authHeaders, endpoints, zh]);

  // hooks 全部在上游调用完毕才早退：条件渲染不能把 useEffect 分到 return 之后。
  if (!flagOn || exportState === 'unavailable') return null;

  const busyAny = Boolean(busy);

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h3 className="mb-1 text-sm font-semibold text-[var(--color-text)]">
          {zh ? '导出我的账户数据' : 'Export my account data'}
        </h3>
        <p className="mb-3 text-[10px] leading-relaxed text-[var(--color-muted)]">
          {zh
            ? 'JSON 格式，含账户资料、成员关系、Agent 查询记录、通知、订阅与审计流水。出于安全，导出文件不含任何登录令牌、会话凭据或密码材料。'
            : 'JSON, covering your profile, memberships, agent query history, notifications, subscriptions and audit trail. For security it never contains access tokens, session credentials or password material.'}
        </p>

        {error && <p className="mb-2 text-xs text-[var(--color-status-error)]" role="alert">{error}</p>}

        {exportState === 'idle' && (
          <button
            type="button"
            onClick={startExport}
            disabled={busyAny}
            className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:opacity-80 disabled:opacity-50"
          >
            {zh ? '生成导出' : 'Generate export'}
          </button>
        )}
        {exportState === 'inflight' && (
          <p className="text-xs text-[var(--color-muted)]">
            {zh ? '正在生成，通常需要几十秒…' : 'Generating; usually takes under a minute…'}
            <button type="button" onClick={load} className="ml-2 underline">{zh ? '刷新' : 'Refresh'}</button>
          </p>
        )}
        {exportState === 'failed' && (
          <div className="space-y-2">
            <p className="text-xs text-[var(--color-status-error)]">
              {zh ? '导出失败' : 'Export failed'}
              {exportRow?.error ? `：${exportRow.error}` : ''}
            </p>
            <button type="button" onClick={startExport} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:opacity-80">
              {zh ? '重试' : 'Retry'}
            </button>
          </div>
        )}
        {(exportState === 'ready' || exportState === 'expired') && (
          <div className="flex flex-wrap items-center gap-2">
            {exportState === 'ready' ? (
              <button
                type="button"
                onClick={downloadExport}
                disabled={busyAny}
                className="rounded-lg bg-[var(--color-inverted)] px-3 py-1.5 text-xs text-[var(--color-inverted-text)] hover:opacity-90 disabled:opacity-50"
              >
                {busy === 'download' ? (zh ? '下载中…' : 'Downloading…') : (zh ? '下载 JSON' : 'Download JSON')}
              </button>
            ) : (
              <span className="text-[10px] text-[var(--color-muted)]">
                {zh ? '导出文件已过期' : 'Export file expired'}
              </span>
            )}
            <button type="button" onClick={startExport} disabled={busyAny} className="text-[10px] underline text-[var(--color-muted)] disabled:opacity-50">
              {zh ? '重新生成' : 'Regenerate'}
            </button>
            {exportRow?.requested_at && (
              <span className="text-[10px] text-[var(--color-muted)]">
                {zh ? '生成于 ' : 'Generated '}
                {new Date(exportRow.requested_at).toLocaleString(lang)}
              </span>
            )}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-[var(--color-status-error)]/40 bg-[var(--color-surface)] p-4">
        <h3 className="mb-1 text-sm font-semibold text-[var(--color-text)]">
          {zh ? '删除账户' : 'Delete account'}
        </h3>

        {deletionState === 'pending' ? (
          <>
            <p className="mb-2 text-xs text-[var(--color-muted)]">
              {zh
                ? `删除请求已提交，将于 ${deletionRow?.scheduled_delete_at?.slice(0, 10)} 执行${remaining ? `（还剩 ${remaining} 天）` : ''}。当前所有会话已登出。`
                : `Deletion scheduled for ${deletionRow?.scheduled_delete_at?.slice(0, 10)}${remaining ? ` (${remaining} days left)` : ''}. All sessions were signed out.`}
            </p>
            <p className="mb-3 text-[10px] text-[var(--color-muted)]">
              {zh ? '宽限期内可撤销：重新登录并点下方的撤销。' : 'You can cancel within the grace period by signing in again.'}
            </p>
            <button
              type="button"
              onClick={cancelDeletion}
              disabled={busyAny}
              className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:opacity-80 disabled:opacity-50"
            >
              {busy === 'cancel' ? (zh ? '撤销中…' : 'Cancelling…') : (zh ? '撤销删除请求' : 'Cancel deletion')}
            </button>
          </>
        ) : (
          <>
            <p className="mb-2 text-xs text-[var(--color-muted)]">
              {zh
                ? '提交后账户进入 30 天宽限期，期内重新登录即可撤销；宽限期结束后账户及其全部数据被物理删除。'
                : 'Submitting starts a 30-day grace period during which you can cancel by signing in again; after it, the account and all of its data are erased.'}
            </p>
            {block && <p className="mb-2 text-xs text-[var(--color-status-error)]" role="alert">{block}</p>}
            {error && <p className="mb-2 text-xs text-[var(--color-status-error)]" role="alert">{error}</p>}
            {!confirming ? (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                disabled={busyAny}
                className="rounded-lg border border-[var(--color-status-error)]/50 px-3 py-1.5 text-xs text-[var(--color-status-error)] hover:opacity-80 disabled:opacity-50"
              >
                {zh ? '删除账户…' : 'Delete account…'}
              </button>
            ) : (
              <div className="space-y-2">
                <label className="flex items-start gap-2 text-[11px] text-[var(--color-text)]">
                  <input type="checkbox" className="mt-0.5" onChange={(e) => setConfirming(e.target.checked)} defaultChecked />
                  <span>
                    {zh
                      ? '我已阅读并同意：30 天后本账户及其全部数据将被永久删除，且无法恢复。'
                      : 'I understand that in 30 days this account and all of its data will be permanently erased.'}
                  </span>
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={requestDeletion}
                    disabled={busyAny}
                    className="rounded-lg bg-[var(--color-status-error)] px-3 py-1.5 text-xs text-white hover:opacity-90 disabled:opacity-50"
                  >
                    {busy === 'delete' ? (zh ? '提交中…' : 'Submitting…') : (zh ? '确认删除' : 'Confirm deletion')}
                  </button>
                  <button type="button" onClick={() => setConfirming(false)} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:opacity-80">
                    {zh ? '取消' : 'Keep my account'}
                  </button>
                </div>
              </div>
            )}
            {!email && (
              <p className="mt-2 text-[10px] text-[var(--color-muted)]">
                {zh ? '如需人工协助，请在「帮助与反馈」页提交请求。' : 'Need a human? Submit a request on the Help & feedback page.'}
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
