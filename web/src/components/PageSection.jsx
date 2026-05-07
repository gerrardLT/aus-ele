export default function PageSection({
  id,
  title,
  description,
  children,
  fullWidthInGrid = true,
  showHeader = true,
  showDivider = true,
}) {
  return (
    <section
      id={id}
      className={`${fullWidthInGrid ? 'col-span-12 ' : ''}grid gap-4 ${showDivider ? 'border-t border-[var(--color-border)] pt-8' : ''} scroll-mt-24`}
    >
      {showHeader ? (
        <div className="max-w-3xl">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
            {title}
          </div>
          {description ? (
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-muted)]">
              {description}
            </p>
          ) : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
