import {
  Line,
  LineChart,
  Tooltip,
} from 'recharts';
import { isFinlandBoardSelectableColumn } from '../../lib/finlandApi';
import { useMeasuredElement } from '../../lib/useMeasuredElement';

function formatValue(value, fallback = '--') {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  return typeof value === 'number' ? value.toFixed(2) : String(value);
}

function buildFieldCards(columns = [], rows = []) {
  return columns
    .filter((column) => isFinlandBoardSelectableColumn(column))
    .map((column) => {
      const chartPoints = rows
        .map((row, index) => ({
          index,
          value: row?.[column.field_key],
          timestamp: row?.timestamp_helsinki || row?.timestamp_utc || row?.date || String(index),
        }))
        .filter((point) => typeof point.value === 'number' && Number.isFinite(point.value));

      const latestValue = chartPoints.at(-1)?.value ?? null;
      const values = chartPoints.map((point) => point.value);

      return {
        ...column,
        chartPoints,
        latestValue,
        highValue: values.length ? Math.max(...values) : null,
        lowValue: values.length ? Math.min(...values) : null,
      };
    })
    .filter((item) => item.chartPoints.length);
}

function GalleryTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-[var(--color-text)]">{label}</div>
      <div className="mt-1 text-[var(--color-muted)]">{formatValue(payload[0]?.value)}</div>
    </div>
  );
}

export default function FinlandSeriesGallery({
  columns = [],
  rows = [],
  selectedFieldIds = [],
  onPromoteField,
  copy,
}) {
  const cards = buildFieldCards(columns, rows);

  return (
    <section className="grid gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
      <div className="grid gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-primary)]/78">
          {copy.eyebrow}
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <h3 className="text-xl font-semibold text-[var(--color-text)]">{copy.title}</h3>
            <p className="max-w-3xl text-sm leading-6 text-[var(--color-muted)]">{copy.description}</p>
          </div>
          <div className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs text-[var(--color-muted)] tabular-nums">
            {cards.length} {copy.countSuffix}
          </div>
        </div>
      </div>

      {cards.length ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {cards.map((card) => (
            <SeriesCard
              key={card.field_key}
              card={card}
              selected={selectedFieldIds.includes(card.field_key)}
              onPromoteField={onPromoteField}
              copy={copy}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-8 text-sm text-[var(--color-muted)]">
          {copy.empty}
        </div>
      )}
    </section>
  );
}

function SeriesCard({ card, selected, onPromoteField, copy }) {
  const [chartRef, chartSize] = useMeasuredElement();

  return (
    <button
      type="button"
      onClick={() => onPromoteField?.(card.field_key)}
      className={`grid min-h-[20rem] min-w-0 gap-4 rounded-lg border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_oklab,var(--color-primary)_36%,transparent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-panel)] ${
        selected
          ? 'border-[color:color-mix(in_oklab,var(--color-primary)_34%,var(--color-border))] bg-[color:color-mix(in_oklab,var(--color-primary)_10%,var(--color-surface))] shadow-[0_16px_30px_color-mix(in_oklab,var(--color-primary)_10%,transparent)]'
          : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[color:color-mix(in_oklab,var(--color-primary)_22%,var(--color-border))] hover:bg-[color:color-mix(in_oklab,var(--color-primary)_4%,var(--color-surface))]'
      }`}
    >
      <div className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="grid gap-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
              {card.granularity || copy.fallback}
            </div>
            <div className="text-base font-semibold text-[var(--color-text)]">{card.label}</div>
          </div>
          <span className="rounded-full border border-[var(--color-border)] px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-[var(--color-muted)]">
            {card.unit || copy.fallback}
          </span>
        </div>

        <div className="flex items-end justify-between gap-4 tabular-nums">
          <div className="text-3xl font-semibold text-[var(--color-text)]">
            {formatValue(card.latestValue, copy.fallback)}
          </div>
          <div className="grid gap-1 text-xs text-[var(--color-muted)]">
            <div>{copy.highLabel}: {formatValue(card.highValue, copy.fallback)}</div>
            <div>{copy.lowLabel}: {formatValue(card.lowValue, copy.fallback)}</div>
          </div>
        </div>
      </div>

      <div ref={chartRef} className="h-40 min-w-0 rounded-md border border-[var(--color-border)] bg-[color:color-mix(in_oklab,var(--color-primary)_4%,var(--color-surface))] p-2">
        {chartSize.width > 0 && chartSize.height > 0 ? (
          <LineChart width={chartSize.width} height={chartSize.height} data={card.chartPoints}>
            <Tooltip content={<GalleryTooltip />} />
            <Line
              type="monotone"
              dataKey="value"
              stroke={selected ? '#355f9c' : '#2d7b72'}
              strokeWidth={2.25}
              dot={false}
            />
          </LineChart>
        ) : null}
      </div>

      <div className="flex items-center justify-between gap-3 text-xs text-[var(--color-muted)]">
        <span>{copy.actionHint}</span>
        <span className="tabular-nums">{card.chartPoints.length}</span>
      </div>
    </button>
  );
}
