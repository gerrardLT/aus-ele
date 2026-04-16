import { metaForState } from '../lib/eventOverlays';

export default function EventBadgeList({ states = [], size = 'sm', locale = 'en' }) {
  if (!states.length) return null;

  const className = size === 'xs'
    ? 'px-2 py-1 text-[10px]'
    : 'px-2.5 py-1 text-xs';

  return (
    <div className="flex flex-wrap gap-2">
      {states.map((state) => {
        const meta = metaForState(state.key, locale);
        return (
          <span
            key={`${state.key}-${state.severity}`}
            className={`inline-flex items-center gap-1 rounded-full font-medium ${className}`}
            style={{
              color: meta.color,
              backgroundColor: meta.softColor,
              border: `1px solid ${meta.color}33`,
            }}
            title={`${meta.label}${state.count ? ` x${state.count}` : ''}`}
          >
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} />
            {meta.label}
          </span>
        );
      })}
    </div>
  );
}
