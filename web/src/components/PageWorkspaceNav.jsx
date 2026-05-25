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
  compact = false,
  buttonOnly = false,
}) {
  const hasLeadContent = Boolean(brand || title || subtitle || meta);

  return (
    <section
      className={buttonOnly
        ? 'bg-transparent p-0'
        : `rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] ${
            compact ? 'px-3 py-2 sm:px-4 sm:py-2.5' : 'px-4 py-4 sm:px-5'
          }`}
    >
      <div className={`flex flex-col ${compact ? 'gap-2' : 'gap-4'} md:flex-row md:justify-between ${hasLeadContent ? 'md:items-start' : 'md:items-center'}`}>
        {hasLeadContent ? (
          <div className="min-w-0 flex-1">
            {brand ? (
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {brand}
              </div>
            ) : null}
            {title ? (
              <h1 className={`${brand ? 'mt-2 ' : ''}text-2xl font-semibold text-[var(--color-text)] md:text-3xl`}>
                {title}
              </h1>
            ) : null}
            {subtitle ? (
              <p className={`${title || brand ? 'mt-2 ' : ''}max-w-3xl text-sm leading-6 text-[var(--color-muted)]`}>
                {subtitle}
              </p>
            ) : null}
            {meta ? (
              <div className={`${title || subtitle || brand ? 'mt-3 ' : ''}flex flex-wrap items-center gap-2 text-xs text-[var(--color-muted)]`}>
                {meta}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className={`flex w-full flex-wrap items-center ${compact ? 'gap-1.5' : 'gap-2'} ${hasLeadContent ? 'justify-start md:w-auto md:justify-end' : 'justify-end'}`}>
          {links.map((link) => {
            const isActive = link.key === current;
            return (
              <a
                key={link.key}
                href={link.href}
                className={`inline-flex min-h-[44px] items-center justify-center rounded border ${
                  compact ? 'px-2.5 py-1 text-[13px]' : 'px-3 py-1.5 text-sm'
                } transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_oklab,var(--color-primary)_36%,transparent)] focus-visible:ring-offset-2 ${
                  buttonOnly ? 'focus-visible:ring-offset-transparent' : 'focus-visible:ring-offset-[var(--color-panel)]'
                } max-sm:flex-1 ${
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
            className={`inline-flex min-h-[44px] items-center justify-center rounded border border-[var(--color-border)] ${
              compact ? 'px-2.5 py-1 text-[13px]' : 'px-3 py-1.5 text-sm'
            } transition-colors hover:bg-[var(--color-inverted)] hover:text-[var(--color-inverted-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_oklab,var(--color-primary)_36%,transparent)] focus-visible:ring-offset-2 ${buttonOnly ? 'focus-visible:ring-offset-transparent' : 'focus-visible:ring-offset-[var(--color-panel)]'} max-sm:flex-1`}
          >
            {languageLabel}
          </button>
        </div>
      </div>
    </section>
  );
}
