export default function PageWorkspaceNav({
  brand,
  subtitle,
  current = 'home',
  links,
  languageLabel,
  languageAriaLabel,
  onToggleLanguage,
  title,
  meta,
  actions,
}) {
  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-4 sm:px-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
            {brand}
          </div>
          {title ? (
            <h1 className="mt-2 text-2xl font-semibold text-[var(--color-text)] md:text-3xl">
              {title}
            </h1>
          ) : null}
          {subtitle ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-muted)]">
              {subtitle}
            </p>
          ) : null}
          {meta ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--color-muted)]">
              {meta}
            </div>
          ) : null}
        </div>

        <div className="flex w-full flex-wrap items-center gap-2 md:w-auto md:justify-end">
          {links.map((link) => {
            const isActive = link.key === current;
            return (
              <a
                key={link.key}
                href={link.href}
                className={`inline-flex min-h-[40px] items-center justify-center rounded border px-3 py-1.5 text-sm transition-colors max-sm:flex-1 ${
                  isActive
                    ? 'border-[var(--color-inverted)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                    : 'border-[var(--color-border)] hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)]'
                }`}
              >
                {link.label}
              </a>
            );
          })}
          {actions}
          <button
            onClick={onToggleLanguage}
            aria-label={languageAriaLabel || languageLabel}
            title={languageAriaLabel || languageLabel}
            className="inline-flex min-h-[40px] items-center justify-center rounded border border-[var(--color-border)] px-3 py-1.5 text-sm transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)] max-sm:flex-1"
          >
            {languageLabel}
          </button>
        </div>
      </div>
    </section>
  );
}
