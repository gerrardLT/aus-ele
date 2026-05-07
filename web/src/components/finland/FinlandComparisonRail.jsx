import { useEffect, useMemo, useState } from 'react';
import {
  Line,
  LineChart,
  Tooltip,
} from 'recharts';
import { fetchJson } from '../../lib/apiClient';
import { buildFinlandBoardChartUrl } from '../../lib/finlandApi';
import { useMeasuredElement } from '../../lib/useMeasuredElement';

const SERIES_COLORS = ['#8b6a1f', '#2d7b72', '#355f9c'];

function buildSeriesCards(series = []) {
  return series.map((item) => {
    const points = Array.isArray(item.points) ? item.points : [];
    const latestPoint = points.at(-1) || null;
    const previousPoint = points.at(-2) || null;

    return {
      ...item,
      latestValue: latestPoint?.value ?? null,
      deltaValue:
        latestPoint && previousPoint && typeof latestPoint.value === 'number' && typeof previousPoint.value === 'number'
          ? latestPoint.value - previousPoint.value
          : null,
      chartPoints: points.map((point) => ({
        timestamp: point.timestamp_local || point.timestamp_utc,
        value: point.value,
      })),
    };
  });
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') {
    return '--';
  }
  if (typeof value === 'number') {
    return value.toFixed(2);
  }
  return String(value);
}

function CompactTooltip({ active, payload, label }) {
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

export default function FinlandComparisonRail({
  apiBase,
  chartRequest,
  items = [],
  copy,
}) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    if (!apiBase || !chartRequest) {
      setPayload(null);
      setLoading(false);
      setError('');
      return () => {
        cancelled = true;
      };
    }

    const loadRail = async () => {
      setLoading(true);
      setError('');

      try {
        const nextPayload = await fetchJson(buildFinlandBoardChartUrl(apiBase, chartRequest));
        if (!cancelled) {
          setPayload(nextPayload);
        }
      } catch (err) {
        if (!cancelled) {
          setPayload(null);
          setError(err?.message || String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadRail();

    return () => {
      cancelled = true;
    };
  }, [apiBase, chartRequest]);

  const seriesCards = useMemo(
    () => buildSeriesCards(payload?.series).filter((item) => item.chartPoints.length),
    [payload],
  );

  return (
    <section className="grid gap-3">
      <div className="grid gap-1">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-primary)]/78">
          {copy.title}
        </div>
        <p className="max-w-3xl text-sm leading-6 text-[var(--color-muted)]">
          {copy.description}
        </p>
      </div>

      {loading ? (
        <div className="grid min-h-[9rem] place-items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm text-[var(--color-muted)]">
          {copy.loading || copy.empty}
        </div>
      ) : null}

      {!loading && error ? (
        <div className="rounded-lg border border-[var(--color-error)]/35 bg-[var(--color-surface)] px-4 py-5 text-sm text-[var(--color-error)]">
          {error}
        </div>
      ) : null}

      {!loading && !error && seriesCards.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {seriesCards.map((item, index) => (
            <CompactSeriesCard
              key={item.field_key}
              item={item}
              color={SERIES_COLORS[index % SERIES_COLORS.length]}
            />
          ))}
        </div>
      ) : null}

      {!loading && !error && !seriesCards.length ? (
        items.length ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <article
                key={item.field_key || item.id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
              >
                <div className="text-sm font-semibold text-[var(--color-text)]">{item.label}</div>
                <div className="mt-2 text-sm text-[var(--color-muted)]">
                  {item.description || item.unit || item.field_key}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="text-sm text-[var(--color-muted)]">{copy.empty}</div>
        )
      ) : null}
    </section>
  );
}

function CompactSeriesCard({ item, color }) {
  const [chartFrameRef, chartFrameSize] = useMeasuredElement();

  return (
    <article className="grid min-w-0 gap-3 rounded-lg border border-[color:color-mix(in_oklab,var(--color-border)_86%,var(--color-primary)_14%)] bg-[color:color-mix(in_oklab,var(--color-surface)_95%,var(--color-primary)_5%)] p-4">
      <div className="grid gap-1">
        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
          {item.label}
        </div>
        <div className="flex items-end justify-between gap-3">
          <div className="text-2xl font-semibold text-[var(--color-text)]">
            {formatValue(item.latestValue)}
          </div>
          <div className="text-xs text-[var(--color-muted)]">
            {item.deltaValue === null ? '--' : `${item.deltaValue >= 0 ? '+' : ''}${formatValue(item.deltaValue)}`}
          </div>
        </div>
      </div>

      <div ref={chartFrameRef} className="h-24 min-w-0">
        {chartFrameSize.width > 0 && chartFrameSize.height > 0 ? (
          <LineChart width={chartFrameSize.width} height={chartFrameSize.height} data={item.chartPoints}>
            <Tooltip content={<CompactTooltip />} />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        ) : null}
      </div>
    </article>
  );
}
