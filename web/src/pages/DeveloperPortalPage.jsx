import { useEffect, useMemo, useState } from 'react';
import { fetchJson } from '../lib/apiClient';
import PageSection from '../components/PageSection';
import PageWorkspaceNav from '../components/PageWorkspaceNav';
import { translations } from '../translations.js';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';
const LANG_STORAGE_KEY = 'app_lang';
const API_KEY_STORAGE_KEY = 'developer_portal_api_key';

function readPreferredLang() {
  try {
    return globalThis.localStorage?.getItem(LANG_STORAGE_KEY) || 'zh';
  } catch {
    return 'zh';
  }
}

function readStoredApiKey() {
  try {
    return globalThis.localStorage?.getItem(API_KEY_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

function formatValue(value) {
  return value ?? '-';
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
        {label}
      </div>
      <div className="mt-3 text-lg font-semibold text-[var(--color-text)]">
        {value}
      </div>
    </div>
  );
}

export default function DeveloperPortalPage() {
  const [lang, setLang] = useState(() => readPreferredLang());
  const [apiKey, setApiKey] = useState(() => readStoredApiKey());
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const copy = useMemo(
    () => translations[lang]?.developerPortal || translations.zh.developerPortal,
    [lang],
  );
  const toggleLanguageLabel = copy.toggleLanguage || translations.zh.developerPortal.toggleLanguage;
  const client = payload?.data?.client || {};
  const quota = payload?.data?.quota || {};
  const billing = payload?.data?.billing || {};
  const ledger = payload?.data?.ledger || {};
  const portalStatusValue = error
    ? copy.error
    : payload
      ? copy.portalStatusReady
      : copy.portalStatusPendingShort;
  const readoutMetrics = [
    { label: copy.readoutClient, value: formatValue(client.client_id) },
    { label: copy.readoutPlan, value: formatValue(client.plan || quota.plan) },
    { label: copy.readoutQuota, value: formatValue(quota.remaining_units) },
    { label: copy.readoutTrace, value: formatValue(payload?.meta?.trace_id) },
  ];
  const navCopy = translations[lang]?.nav || translations.zh.nav;
  const workspaceLinks = [
    { key: 'home', href: '/', label: navCopy.brand },
    { key: 'fingrid', href: '/fingrid', label: navCopy.fingrid },
    { key: 'developer', href: '/developer', label: copy.title },
  ];

  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(LANG_STORAGE_KEY, lang);
    } catch {
      // Ignore localStorage write failures in restricted environments.
    }
  }, [lang]);

  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(API_KEY_STORAGE_KEY, apiKey);
    } catch {
      // Ignore localStorage write failures in restricted environments.
    }
  }, [apiKey]);

  const loadPortal = async () => {
    const trimmedApiKey = apiKey.trim();
    if (!trimmedApiKey) {
      setPayload(null);
      setError('');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const data = await fetchJson(`${API_BASE}/v1/developer/portal`, {
        headers: {
          'X-API-Key': trimmedApiKey,
        },
      });
      setPayload(data);
    } catch (err) {
      setPayload(null);
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (apiKey.trim()) {
      loadPortal();
    }
  }, []);

  return (
    <main className="min-h-screen bg-[var(--color-background)] px-6 py-8 text-[var(--color-text)]">
      <div className="mx-auto grid max-w-6xl gap-6">
        <PageWorkspaceNav
          brand="API v1"
          title={copy.title}
          subtitle={copy.subtitle}
          current="developer"
          links={workspaceLinks}
          languageLabel={toggleLanguageLabel}
          onToggleLanguage={() => setLang((current) => (current === 'zh' ? 'en' : 'zh'))}
        />

        <section className="grid gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {copy.portalReadoutTitle}
              </div>
              <h2 className="mt-2 text-2xl font-semibold text-[var(--color-text)]">
                {payload ? copy.portalReadoutReady : copy.portalReadoutPending}
              </h2>
              <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">
                {copy.portalReadoutSubtitle}
              </p>
            </div>
            {payload?.meta?.trace_id ? (
              <div className="rounded-full border border-[var(--color-border)] px-3 py-1 text-xs text-[var(--color-muted)]">
                {copy.readoutTrace}: {payload.meta.trace_id}
              </div>
            ) : null}
          </div>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px]">
            <label className="grid gap-2">
              <span className="text-sm font-medium">{copy.apiKey}</span>
              <input
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={copy.apiKeyPlaceholder}
                className="min-h-[44px] rounded border border-[var(--color-border)] bg-transparent px-3 py-2 outline-none transition-colors focus:border-[var(--color-text)]"
              />
            </label>
            <button
              onClick={loadPortal}
              disabled={loading}
              className="inline-flex min-h-[44px] items-center justify-center rounded border border-[var(--color-border)] px-4 py-2 transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)] disabled:cursor-not-allowed disabled:opacity-60 lg:mt-[30px]"
            >
              {loading ? copy.loading : copy.load}
            </button>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {readoutMetrics.map((item) => (
              <MetricCard key={item.label} label={item.label} value={item.value} />
            ))}
          </div>

          {!apiKey.trim() ? (
            <div className="text-sm text-[var(--color-muted)]">{copy.empty}</div>
          ) : null}
          {error ? (
            <div className="text-sm text-[var(--color-error)]">
              {copy.error}: {error}
            </div>
          ) : null}
        </section>

        <PageSection
          id="stage-access"
          title={copy.stageAccess}
          description={copy.stageAccessDesc}
        >
          <section className="grid gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5 lg:grid-cols-2">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {copy.client}
              </div>
              <div className="mt-4 grid gap-2 text-sm leading-6">
                <div>{copy.clientId}: {formatValue(client.client_id)}</div>
                <div>{copy.plan}: {formatValue(client.plan)}</div>
                <div>{copy.organization}: {formatValue(client.organization_id)}</div>
                <div>{copy.workspace}: {formatValue(client.workspace_id)}</div>
                <div>{copy.createdAt}: {formatValue(client.created_at)}</div>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {copy.apiKey}
              </div>
              <div className="mt-4 grid gap-2 text-sm leading-6">
                <div>{copy.organization}: {formatValue(client.organization_id)}</div>
                <div>{copy.workspace}: {formatValue(client.workspace_id)}</div>
                <div>{copy.status}: {portalStatusValue}</div>
                <div>{copy.readoutTrace}: {formatValue(payload?.meta?.trace_id)}</div>
              </div>
            </div>
          </section>
        </PageSection>

        <PageSection
          id="stage-economics"
          title={copy.stageEconomics}
          description={copy.stageEconomicsDesc}
        >
          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {copy.quota}
              </div>
              <div className="mt-4 grid gap-2 text-sm leading-6">
                <div>{copy.plan}: {formatValue(quota.plan)}</div>
                <div>{copy.dailyLimit}: {formatValue(quota.daily_unit_limit)}</div>
                <div>{copy.usedUnits}: {formatValue(quota.used_units)}</div>
                <div>{copy.remainingUnits}: {formatValue(quota.remaining_units)}</div>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {copy.billing}
              </div>
              <div className="mt-4 grid gap-2 text-sm leading-6">
                <div>{copy.requestCount}: {formatValue(billing.totals?.request_count)}</div>
                <div>{copy.requestUnits}: {formatValue(billing.totals?.request_units)}</div>
                <div>{copy.estimatedCost}: {formatValue(billing.totals?.estimated_cost_usd)}</div>
              </div>
            </div>
          </section>
        </PageSection>

        <PageSection
          id="stage-ledger"
          title={copy.stageLedger}
          description={copy.stageLedgerDesc}
        >
          <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {copy.ledger}
              </div>
              <div className="text-xs text-[var(--color-muted)]">
                {payload?.meta?.trace_id || ''}
              </div>
            </div>
            <div className="mt-4 overflow-x-auto">
              {ledger.items?.length ? (
                <table className="min-w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-[var(--color-muted)]">
                      <th className="px-3 py-2">{copy.endpoint}</th>
                      <th className="px-3 py-2">{copy.method}</th>
                      <th className="px-3 py-2">{copy.status}</th>
                      <th className="px-3 py-2">{copy.requestUnits}</th>
                      <th className="px-3 py-2">{copy.estimatedCost}</th>
                      <th className="px-3 py-2">{copy.createdAt}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.items.map((item) => (
                      <tr key={item.usage_id} className="border-b border-[var(--color-border)]">
                        <td className="px-3 py-2">{item.endpoint}</td>
                        <td className="px-3 py-2">{item.http_method}</td>
                        <td className="px-3 py-2">{item.status_code}</td>
                        <td className="px-3 py-2">{item.request_units}</td>
                        <td className="px-3 py-2">{item.estimated_cost_usd}</td>
                        <td className="px-3 py-2">{item.created_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-sm text-[var(--color-muted)]">{copy.noLedger}</div>
              )}
            </div>
          </section>
        </PageSection>
      </div>
    </main>
  );
}
