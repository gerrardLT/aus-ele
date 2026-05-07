export default function FinlandPrimaryPriceSelector({
  options = [],
  selectedFieldKey = '',
  onChange,
  copy,
}) {
  return (
    <section className="grid gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
      <div className="grid gap-1">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
          {copy.label}
        </div>
        <p className="text-sm leading-6 text-[var(--color-muted)]">
          {copy.helper}
        </p>
      </div>

      {options.length ? (
        <div className="flex flex-wrap gap-2">
          {options.map((option) => {
            const isActive = option.field_key === selectedFieldKey;
            return (
              <button
                key={option.field_key}
                type="button"
                onClick={() => onChange?.(option.field_key)}
                aria-pressed={isActive}
                className={`min-h-[44px] rounded-full border px-4 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_oklab,var(--color-primary)_36%,transparent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-panel)] ${
                  isActive
                    ? 'border-[var(--color-inverted)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                    : 'border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]'
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="text-sm text-[var(--color-muted)]">{copy.empty}</div>
      )}
    </section>
  );
}
