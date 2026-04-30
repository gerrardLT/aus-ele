export default function PageSection({ id, title, description, children }) {
  return (
    <section id={id} className="grid gap-4 border-t border-[var(--color-border)] pt-8 scroll-mt-24">
      <div className="max-w-3xl">
        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
          {title}
        </div>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-muted)]">
          {description}
        </p>
      </div>
      {children}
    </section>
  );
}
