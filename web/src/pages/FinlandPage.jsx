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
  FINLAND_DAILY_BOARD_VIEWS,
  FINLAND_PRIMARY_BOARD_TABS,
  buildFinlandBoardChartRequest,
  buildFinlandBoardDictionaryRows,
  buildFinlandBoardFieldCatalogUrl,
  buildFinlandBoardOverviewUrl,
  buildFinlandBoardReadinessUrl,
  buildFinlandBoardSelectedFields,
  buildFinlandBoardTableUrl,
  getFinlandBoardOverviewCards,
  getFinlandBoardTableColumns,
  getFinlandBoardTableRows,
  normalizeFinlandDictionaryJumpTarget,
  resolveFinlandBoardView,
} from '../lib/finlandApi';
import { translations } from '../translations.js';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';
const BOARD_TIMEZONE = 'Europe/Helsinki';
const LANG_STORAGE_KEY = 'app_lang';
const TABULAR_TABS = new Set(FINLAND_PRIMARY_BOARD_TABS);

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

function buildHeaderMetrics(copy, overviewPayload, readinessPayload) {
  return {
    overviewCount: Array.isArray(overviewPayload?.cards) ? overviewPayload.cards.length : Object.keys(overviewPayload || {}).length,
    readinessCount: Array.isArray(readinessPayload?.sources) ? readinessPayload.sources.length : Object.keys(readinessPayload || {}).length,
    deliveryValue: copy.deliveryValue,
  };
}

export default function FinlandPage() {
  const [lang, setLang] = useState(() => readPreferredLang());
  const [overviewPayload, setOverviewPayload] = useState(null);
  const [readinessPayload, setReadinessPayload] = useState(null);
  const [tablePayload, setTablePayload] = useState(null);
  const [fieldCatalogPayload, setFieldCatalogPayload] = useState(null);
  const [activeTab, setActiveTab] = useState('capacity_hourly');
  const [dailyMode, setDailyMode] = useState('daily_capacity');
  const [selectedFieldIds, setSelectedFieldIds] = useState([]);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [boardLoading, setBoardLoading] = useState(true);
  const [error, setError] = useState('');
  const loading = overviewLoading || boardLoading;
  const copy = useMemo(
    () => translations[lang]?.finlandBoard || translations.en.finlandBoard,
    [lang],
  );
  const navCopy = translations[lang]?.nav || translations.en.nav;
  const activeBoardView = activeTab === 'daily' ? dailyMode : activeTab;
  const resolvedBoardView = resolveFinlandBoardView(activeTab, dailyMode);
  const overviewCards = useMemo(
    () => getFinlandBoardOverviewCards(overviewPayload),
    [overviewPayload],
  );
  const headerMetrics = useMemo(
    () => buildHeaderMetrics(copy, overviewPayload, readinessPayload),
    [copy, overviewPayload, readinessPayload],
  );
  const fieldCatalogItems = useMemo(
    () => (Array.isArray(fieldCatalogPayload?.items) ? fieldCatalogPayload.items : []),
    [fieldCatalogPayload],
  );
  const tableColumns = useMemo(
    () => getFinlandBoardTableColumns(tablePayload),
    [tablePayload],
  );
  const tableRows = useMemo(
    () => getFinlandBoardTableRows(tablePayload),
    [tablePayload],
  );
  const dictionaryRows = useMemo(
    () => buildFinlandBoardDictionaryRows(fieldCatalogItems),
    [fieldCatalogItems],
  );
  const selectedFields = useMemo(
    () => buildFinlandBoardSelectedFields({ selectedFieldIds, tablePayload, fieldCatalogItems }),
    [selectedFieldIds, tablePayload, fieldCatalogItems],
  );
  const chartRequest = useMemo(
    () => buildFinlandBoardChartRequest({ selectedFields, viewGranularity: tablePayload?.granularity }),
    [selectedFields, tablePayload],
  );
  const workbenchCopy = useMemo(
    () => ({
      ...copy.workbenchPanel,
      dailyModesLabel: copy.task7.dailyModesLabel,
      dictionaryTitle: copy.task7.dictionary.title,
      dictionaryDescription: copy.task7.dictionary.description,
      dictionaryFieldLabel: copy.task7.dictionary.fieldLabel,
      dictionarySourceLabel: copy.task7.dictionary.sourceLabel,
      dictionaryMethodLabel: copy.task7.dictionary.methodLabel,
      dictionaryJumpLabel: copy.task7.dictionary.jumpLabel,
      dictionaryEmpty: copy.task7.dictionary.empty,
    }),
    [copy],
  );
  const tabs = useMemo(
    () => [
      {
        id: 'capacity_hourly',
        label: copy.task7.tabs.capacity.label,
        panelTitle: copy.task7.tabs.capacity.panelTitle,
        panelDescription: copy.task7.tabs.capacity.panelDescription,
      },
      {
        id: 'activation_15m',
        label: copy.task7.tabs.activation.label,
        panelTitle: copy.task7.tabs.activation.panelTitle,
        panelDescription: copy.task7.tabs.activation.panelDescription,
      },
      {
        id: 'daily',
        label: copy.task7.tabs.daily.label,
        panelTitle: copy.task7.tabs.daily.panelTitle,
        panelDescription: copy.task7.tabs.daily.panelDescription,
      },
      {
        id: 'field_dictionary',
        label: copy.task7.tabs.dictionary.label,
        panelTitle: copy.task7.tabs.dictionary.panelTitle,
        panelDescription: copy.task7.tabs.dictionary.panelDescription,
      },
      {
        id: 'analysis',
        label: copy.task7.tabs.analysis.label,
        panelTitle: copy.task7.tabs.analysis.panelTitle,
        panelDescription: copy.task7.tabs.analysis.panelDescription,
      },
    ],
    [copy],
  );
  const dailyModes = useMemo(
    () => [
      { id: 'daily_capacity', label: copy.task7.dailyModes.capacity },
      { id: 'daily_activation', label: copy.task7.dailyModes.activation },
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

    const loadBoardOverview = async () => {
      setOverviewLoading(true);
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
          setOverviewLoading(false);
        }
      }
    };

    loadBoardOverview();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const shouldLoadTable = TABULAR_TABS.has(activeTab);

    const loadBoardWorkbench = async () => {
      setBoardLoading(true);
      setError('');

      try {
        const [nextTablePayload, nextFieldCatalogPayload] = await Promise.all(
          shouldLoadTable
            ? [
              fetchJson(buildFinlandBoardTableUrl(API_BASE, { view: activeBoardView, tz: BOARD_TIMEZONE })),
              fetchJson(buildFinlandBoardFieldCatalogUrl(API_BASE)),
            ]
            : [
              Promise.resolve(tablePayload),
              fetchJson(buildFinlandBoardFieldCatalogUrl(API_BASE)),
            ],
        );

        if (cancelled) {
          return;
        }

        setTablePayload(nextTablePayload);
        setFieldCatalogPayload(nextFieldCatalogPayload);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || String(err));
          setTablePayload(null);
          setFieldCatalogPayload(null);
        }
      } finally {
        if (!cancelled) {
          setBoardLoading(false);
        }
      }
    };

    loadBoardWorkbench();

    return () => {
      cancelled = true;
    };
  }, [activeBoardView, activeTab]);

  const handleDictionaryJump = (fieldKey, preferredView) => {
    if (FINLAND_DAILY_BOARD_VIEWS.includes(preferredView)) {
      setDailyMode(preferredView);
    }
    const nextActiveTab = normalizeFinlandDictionaryJumpTarget(preferredView);
    setActiveTab(nextActiveTab);
    setSelectedFieldIds([fieldKey]);
  };

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

        <FinlandOverviewCards cards={overviewCards} copy={copy} />

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
          panelCopy={workbenchCopy}
          dailyModes={dailyModes}
          dailyMode={dailyMode}
          onDailyModeChange={setDailyMode}
          dictionaryRows={dictionaryRows}
          onDictionaryJump={handleDictionaryJump}
        />

        {TABULAR_TABS.has(activeTab) ? (
          <FinlandDataTable
            columns={tableColumns}
            rows={tableRows}
            selectedFieldIds={selectedFieldIds}
            onSelectField={setSelectedFieldIds}
            copy={{
              ...copy.tableShell,
              notAvailable: copy.notAvailable,
              description: `${copy.task7.tableDescriptionPrefix} ${tabs.find((tab) => tab.id === activeTab)?.label || activeBoardView} (${resolvedBoardView})`,
            }}
          />
        ) : null}

        {activeTab === 'analysis' ? (
          <section className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(20rem,1fr)]">
            <FinlandLinkedChart
              apiBase={API_BASE}
              chartRequest={chartRequest}
              selectedFields={selectedFields}
              copy={copy.linkedChart}
            />
            <FinlandFieldDetailPanel
              selectedFields={selectedFields}
              copy={{ ...copy.fieldDetailPanel, notAvailable: copy.notAvailable }}
            />
          </section>
        ) : null}
      </div>
    </main>
  );
}
