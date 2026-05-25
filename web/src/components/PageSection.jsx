export default function PageSection({
  id,
  title,
  description,
  children,
  fullWidthInGrid = true,
  showHeader = true,
  showDivider = true,
  compactHeader = false,
}) {
  return (
    <section
      id={id}
      className={`${
        fullWidthInGrid ? 'col-span-12 ' : ''
      }${
        showDivider
          ? 'grid gap-4 border-t border-[var(--color-border)] pt-8 scroll-mt-24'
          : 'grid gap-4 scroll-mt-24'
      }`}
    >
      {showHeader ? (
        <div className={compactHeader ? 'flex flex-col gap-1 md:flex-row md:items-baseline md:gap-3' : 'max-w-3xl'}>
          <div className="shrink-0 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
            {title}
          </div>
          {description ? (
            <p className={compactHeader
              ? 'max-w-4xl text-xs leading-5 text-[var(--color-muted)] md:overflow-hidden md:text-ellipsis md:whitespace-nowrap'
              : 'mt-2 max-w-2xl text-sm leading-6 text-[var(--color-muted)]'}
            >
              {description}
            </p>
          ) : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
