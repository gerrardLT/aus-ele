export default function FinlandWorkbenchTabs({
  tabs = [],
  activeTab,
  onTabChange,
  panelCopy,
  dailyModes = [
    { id: 'daily_capacity', label: 'Daily Capacity' },
    { id: 'daily_activation', label: 'Daily Activation' },
  ],
  dailyMode,
  onDailyModeChange,
  dictionaryRows = [],
  onDictionaryJump,
}) {
  const activePanel = tabs.find((tab) => tab.id === activeTab);

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label={panelCopy.tabListLabel}>
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={`finland-tab-panel-${tab.id}`}
              onClick={() => onTabChange(tab.id)}
              className={`min-h-[44px] rounded-full border px-4 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_oklab,var(--color-primary)_36%,transparent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-panel)] ${
                isActive
                  ? 'border-[var(--color-inverted)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                  : 'border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        id={`finland-tab-panel-${activeTab}`}
        role="tabpanel"
        className="mt-5 grid gap-4 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-5"
      >
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
          {panelCopy.eyebrow}
        </div>
        <h3 className="text-lg font-semibold text-[var(--color-text)]">
          {activePanel?.panelTitle || panelCopy.defaultTitle}
        </h3>
        <p className="text-sm leading-6 text-[var(--color-muted)]">
          {activePanel?.panelDescription || panelCopy.defaultDescription}
        </p>

        {activeTab === 'daily' ? (
          <div className="grid gap-3">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
              {panelCopy.dailyModesLabel}
            </div>
            <div className="inline-flex w-fit rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] p-1">
              {dailyModes.map((mode) => {
                const isActive = mode.id === dailyMode;
                return (
                  <button
                    key={mode.id}
                    type="button"
                    aria-pressed={isActive}
                    onClick={() => onDailyModeChange?.(mode.id)}
                    className={`min-h-[44px] min-w-[9rem] rounded-full px-4 py-2 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_oklab,var(--color-primary)_36%,transparent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-panel)] ${
                      isActive
                        ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                        : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                    }`}
                  >
                    {mode.label}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {activeTab === 'field_dictionary' ? (
          dictionaryRows.length ? (
            <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
              <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(10rem,0.9fr)_minmax(0,1.6fr)_auto] gap-3 border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                <div>{panelCopy.dictionaryFieldLabel}</div>
                <div>{panelCopy.dictionarySourceLabel}</div>
                <div>{panelCopy.dictionaryMethodLabel}</div>
                <div>{panelCopy.dictionaryJumpLabel}</div>
              </div>
              <div className="max-h-[24rem] overflow-auto">
                {dictionaryRows.map((row, index) => (
                  <div
                    key={row.field_key}
                    className={`grid grid-cols-[minmax(0,1.4fr)_minmax(10rem,0.9fr)_minmax(0,1.6fr)_auto] gap-3 border-b border-[var(--color-border)] px-4 py-3 text-sm ${
                      index % 2 === 0 ? 'bg-[var(--color-panel)]' : 'bg-[var(--color-surface)]/45'
                    }`}
                  >
                    <div className="font-medium text-[var(--color-text)]">{row.label}</div>
                    <div className="text-[var(--color-muted)]">{row.source_name || row.source_type}</div>
                    <div className="line-clamp-2 text-[var(--color-muted)]">{row.methodology_note}</div>
                    <div>
                      <button
                        type="button"
                        onClick={() => onDictionaryJump?.(row.field_key, row.preferredView)}
                        className="min-h-[44px] rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-text)] transition hover:border-[var(--color-inverted)] hover:text-[var(--color-inverted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_oklab,var(--color-primary)_36%,transparent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-panel)]"
                      >
                        {panelCopy.dictionaryJumpLabel}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-sm text-[var(--color-muted)]">{panelCopy.dictionaryEmpty}</div>
          )
        ) : null}
      </div>
    </section>
  );
}
