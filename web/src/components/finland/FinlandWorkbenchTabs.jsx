export default function FinlandWorkbenchTabs({
  tabs = [],
  activeTab,
  onTabChange,
  panelCopy,
}) {
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
              className={`min-h-[40px] rounded-full border px-4 py-2 text-sm transition-colors ${
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
        className="mt-5 grid gap-3 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-5"
      >
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
          {panelCopy.eyebrow}
        </div>
        <h3 className="text-lg font-semibold text-[var(--color-text)]">
          {tabs.find((tab) => tab.id === activeTab)?.panelTitle || panelCopy.defaultTitle}
        </h3>
        <p className="text-sm leading-6 text-[var(--color-muted)]">
          {tabs.find((tab) => tab.id === activeTab)?.panelDescription || panelCopy.defaultDescription}
        </p>
      </div>
    </section>
  );
}
