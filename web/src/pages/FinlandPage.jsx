import { useEffect, useMemo, useState } from 'react';
import PageWorkspaceNav from '../components/PageWorkspaceNav';
import FinlandBoardHeader from '../components/finland/FinlandBoardHeader';
import FinlandDataTable from '../components/finland/FinlandDataTable';
import FinlandFieldDetailPanel from '../components/finland/FinlandFieldDetailPanel';
import FinlandLinkedChart from '../components/finland/FinlandLinkedChart';
import FinlandOverviewCards from '../components/finland/FinlandOverviewCards';
import FinlandWorkbenchTabs from '../components/finland/FinlandWorkbenchTabs';
import { fetchJson } from '../lib/apiClient';
import {
  buildFinlandBoardOverviewUrl,
  buildFinlandBoardReadinessUrl,
} from '../lib/finlandApi';
import { translations } from '../translations.js';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';
const LANG_STORAGE_KEY = 'app_lang';

function readPreferredLang() {
  try {
    return globalThis.localStorage?.getItem(LANG_STORAGE_KEY) || 'zh';
  } catch {
    return 'zh';
  }
}

function readPath(source, path, fallback = null) {
  return path.split('.').reduce((value, key) => value?.[key], source) ?? fallback;
}

function formatCoverageWindow(overviewPayload, readinessPayload, copy) {
  const start = readPath(overviewPayload, 'window.start')
    || readPath(overviewPayload, 'data.window.start')
    || readPath(readinessPayload, 'coverage.start');
  const end = readPath(overviewPayload, 'window.end')
    || readPath(overviewPayload, 'data.window.end')
    || readPath(readinessPayload, 'coverage.end');

  if (start && end) {
    return `${start} -> ${end}`;
  }
  return start || end || copy.notAvailable;
}

function buildOverviewCards(copy, overviewPayload, readinessPayload) {
  const sourceCount = readPath(overviewPayload, 'summary.source_count')
    || readPath(overviewPayload, 'data.summary.source_count')
    || readPath(readinessPayload, 'sources.ready')
    || readPath(readinessPayload, 'sources.total')
    || 0;
  const readinessValue = readPath(readinessPayload, 'summary.status')
    || readPath(readinessPayload, 'status')
    || readPath(readinessPayload, 'readiness.status')
    || copy.pending;
  const traceValue = readPath(overviewPayload, 'meta.trace_id')
    || readPath(readinessPayload, 'meta.trace_id')
    || copy.notAvailable;

  return [
    {
      id: 'coverage-window',
      label: copy.cards.coverageWindow.label,
      value: formatCoverageWindow(overviewPayload, readinessPayload, copy),
      description: copy.cards.coverageWindow.description,
    },
    {
      id: 'source-count',
      label: copy.cards.sourceCount.label,
      value: sourceCount,
      description: copy.cards.sourceCount.description,
    },
    {
      id: 'readiness',
      label: copy.cards.readiness.label,
      value: readinessValue,
      description: copy.cards.readiness.description,
    },
    {
      id: 'trace',
      label: copy.cards.trace.label,
      value: traceValue,
      description: copy.cards.trace.description,
    },
  ];
}

function buildHeaderMetrics(copy, overviewPayload, readinessPayload) {
  return {
    overviewCount: Object.keys(overviewPayload || {}).length,
    readinessCount: Object.keys(readinessPayload || {}).length,
    deliveryValue: copy.deliveryValue,
  };
}

function summarizeValue(value, fallback) {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  if (typeof value === 'object') {
    return Array.isArray(value) ? `${value.length} items` : `${Object.keys(value).length} keys`;
  }
  return String(value);
}

function buildFieldDescriptors(copy, overviewPayload, readinessPayload) {
  return copy.fieldCatalog.map((descriptor) => {
    const payload = descriptor.source === 'overview' ? overviewPayload : readinessPayload;
    const rawValue = readPath(payload, descriptor.path);

    return {
      id: descriptor.id,
      label: descriptor.label,
      unit: descriptor.unit,
      source: descriptor.source,
      readiness: rawValue === null || rawValue === undefined ? copy.pending : copy.tableShell.ready,
      value: summarizeValue(rawValue, copy.notAvailable),
    };
  });
}

export default function FinlandPage() {
  const [lang, setLang] = useState(() => readPreferredLang());
  const [overviewPayload, setOverviewPayload] = useState(null);
  const [readinessPayload, setReadinessPayload] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedFieldIds, setSelectedFieldIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const copy = useMemo(
    () => translations[lang]?.finlandBoard || translations.en.finlandBoard,
    [lang],
  );
  const navCopy = translations[lang]?.nav || translations.en.nav;
  const cards = useMemo(
    () => buildOverviewCards(copy, overviewPayload, readinessPayload),
    [copy, overviewPayload, readinessPayload],
  );
  const headerMetrics = useMemo(
    () => buildHeaderMetrics(copy, overviewPayload, readinessPayload),
    [copy, overviewPayload, readinessPayload],
  );
  const fieldDescriptors = useMemo(
    () => buildFieldDescriptors(copy, overviewPayload, readinessPayload),
    [copy, overviewPayload, readinessPayload],
  );
  const selectedFields = useMemo(
    () => fieldDescriptors.filter((field) => selectedFieldIds.includes(field.id)),
    [fieldDescriptors, selectedFieldIds],
  );
  const tabs = useMemo(
    () => [
      {
        id: 'overview',
        label: copy.tabs.overview.label,
        panelTitle: copy.tabs.overview.panelTitle,
        panelDescription: copy.tabs.overview.panelDescription,
      },
      {
        id: 'table',
        label: copy.tabs.table.label,
        panelTitle: copy.tabs.table.panelTitle,
        panelDescription: copy.tabs.table.panelDescription,
      },
      {
        id: 'analysis',
        label: copy.tabs.analysis.label,
        panelTitle: copy.tabs.analysis.panelTitle,
        panelDescription: copy.tabs.analysis.panelDescription,
      },
    ],
    [copy],
  );
  const workspaceLinks = [
    { key: 'home', href: '/', label: navCopy.brand },
    { key: 'finland', href: '/finland', label: navCopy.finland },
    { key: 'fingrid', href: '/fingrid', label: navCopy.fingrid },
    { key: 'developer', href: '/developer', label: navCopy.developerPortal },
  ];

  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(LANG_STORAGE_KEY, lang);
    } catch {
      // Ignore localStorage write failures in restricted environments.
    }
  }, [lang]);

  useEffect(() => {
    let cancelled = false;

    const loadBoard = async () => {
      setLoading(true);
      setError('');

      try {
        const [nextOverviewPayload, nextReadinessPayload] = await Promise.all([
          fetchJson(buildFinlandBoardOverviewUrl(API_BASE)),
          fetchJson(buildFinlandBoardReadinessUrl(API_BASE)),
        ]);

        if (cancelled) {
          return;
        }

        setOverviewPayload(nextOverviewPayload);
        setReadinessPayload(nextReadinessPayload);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || String(err));
          setOverviewPayload(null);
          setReadinessPayload(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadBoard();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen bg-[var(--color-background)] px-6 py-8 text-[var(--color-text)]">
      <div className="mx-auto grid max-w-7xl gap-6">
        <PageWorkspaceNav
          brand={copy.brand}
          title={copy.title}
          subtitle={copy.subtitle}
          current="finland"
          links={workspaceLinks}
          languageLabel={copy.toggleLanguage}
          languageAriaLabel={copy.toggleLanguageAriaLabel}
          onToggleLanguage={() => setLang((current) => (current === 'zh' ? 'en' : 'zh'))}
          meta={(
            <>
              <span>{copy.meta.scope}</span>
              <span className="h-1 w-1 rounded-full bg-[var(--color-muted)]/60" />
              <span>{loading ? copy.status.loading : error ? copy.status.error : copy.status.ready}</span>
            </>
          )}
        />

        <FinlandBoardHeader
          copy={copy}
          loading={loading}
          error={error}
          headerMetrics={headerMetrics}
        />

        <FinlandOverviewCards cards={cards} copy={copy} />

        {error ? (
          <section className="rounded-lg border border-[var(--color-error)]/35 bg-[var(--color-panel)] p-5 text-sm text-[var(--color-error)]">
            <div className="font-semibold">{copy.errorTitle}</div>
            <div className="mt-2 leading-6">{error}</div>
          </section>
        ) : null}

        <FinlandWorkbenchTabs
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          panelCopy={copy.workbenchPanel}
        />

        {activeTab === 'table' ? (
          <FinlandDataTable
            fields={fieldDescriptors}
            selectedFieldIds={selectedFieldIds}
            onSelectField={setSelectedFieldIds}
            copy={copy.tableShell}
          />
        ) : null}

        {activeTab === 'analysis' ? (
          <section className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(20rem,1fr)]">
            <FinlandLinkedChart
              selectedFields={selectedFields}
              copy={copy.linkedChart}
            />
            <FinlandFieldDetailPanel selectedFields={selectedFields} copy={copy.fieldDetailPanel} />
          </section>
        ) : null}
      </div>
    </main>
  );
}
