import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchJson } from '../../lib/apiClient';
import { buildFinlandBoardChartUrl } from '../../lib/finlandApi';
import { useMeasuredElement } from '../../lib/useMeasuredElement';

const SERIES_COLORS = ['#355f9c', '#8b6a1f', '#2d7b72', '#9c5266'];

function FinlandLinkedChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm shadow-lg">
      <div className="font-medium text-[var(--color-text)]">{label}</div>
      <div className="mt-2 grid gap-1">
        {payload.map((entry) => (
          <div key={entry.dataKey} className="flex items-center justify-between gap-4 text-[var(--color-muted)]">
            <span style={{ color: entry.color }}>{entry.name}</span>
            <span className="text-[var(--color-text)]">{entry.value ?? '--'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function buildChartData(series = []) {
  const pointsByTimestamp = new Map();

  for (const item of series) {
    for (const point of item.points || []) {
      const timestamp = point.timestamp_local || point.timestamp_utc;
      const existing = pointsByTimestamp.get(timestamp) || { timestamp };
      existing[item.field_key] = point.value;
      pointsByTimestamp.set(timestamp, existing);
    }
  }

  return [...pointsByTimestamp.values()];
}

export default function FinlandLinkedChart({
  apiBase,
  chartRequest,
  selectedFields = [],
  copy,
}) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const hasSelection = selectedFields.length > 0;
  const [chartFrameRef, chartFrameSize] = useMeasuredElement();

  useEffect(() => {
    let cancelled = false;

    if (!chartRequest) {
      setPayload(null);
      setLoading(false);
      setError('');
      return () => {
        cancelled = true;
      };
    }

    const loadChart = async () => {
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

    loadChart();

    return () => {
      cancelled = true;
    };
  }, [apiBase, chartRequest]);

  const chartData = useMemo(() => buildChartData(payload?.series), [payload]);

  return (
    <section className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5 lg:p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
        {copy.eyebrow}
      </div>
      <div className="mt-3 overflow-hidden rounded-lg border border-[color:color-mix(in_oklab,var(--color-border)_82%,var(--color-primary)_18%)] bg-[var(--color-panel)] shadow-[0_12px_28px_color-mix(in_oklab,var(--color-primary)_7%,transparent)]">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <h3 className="text-base font-semibold text-[var(--color-text)]">
            {copy.title}
          </h3>
          <span className="rounded-full border border-[color:color-mix(in_oklab,var(--color-primary)_28%,var(--color-border))] bg-[color:color-mix(in_oklab,var(--color-primary)_10%,var(--color-surface))] px-2 py-1 text-[11px] font-semibold text-[var(--color-primary)]">
            {selectedFields.length} {copy.selectionCountSuffix}
          </span>
        </div>
        <div className="grid gap-4 p-4">
          {!hasSelection ? (
            <div className="grid h-52 place-items-center rounded-md border border-dashed border-[color:color-mix(in_oklab,var(--color-primary)_24%,var(--color-border))] bg-[color:color-mix(in_oklab,var(--color-surface)_92%,var(--color-primary)_8%)] text-center">
              <div className="grid max-w-md gap-2">
                <div className="text-base font-semibold text-[var(--color-text)]">
                  {copy.emptyTitle}
                </div>
                <p className="text-sm leading-6 text-[var(--color-muted)]">
                  {copy.emptyDescription}
                </p>
              </div>
            </div>
          ) : null}

          {hasSelection && loading ? (
            <div className="grid h-52 place-items-center rounded-md border border-dashed border-[color:color-mix(in_oklab,var(--color-primary)_24%,var(--color-border))] bg-[color:color-mix(in_oklab,var(--color-surface)_92%,var(--color-primary)_8%)] text-sm text-[var(--color-muted)]">
              {copy.loading}
            </div>
          ) : null}

          {hasSelection && error ? (
            <div className="rounded-md border border-[var(--color-error)]/35 bg-[var(--color-panel)] px-4 py-6 text-sm text-[var(--color-error)]">
              {error}
            </div>
          ) : null}

          {hasSelection && !loading && !error && payload?.series?.length ? (
            <>
              <div
                ref={chartFrameRef}
                className="h-80 min-w-0 rounded-md border border-[color:color-mix(in_oklab,var(--color-primary)_16%,var(--color-border))] bg-[color:color-mix(in_oklab,var(--color-surface)_96%,var(--color-primary)_4%)] p-3"
              >
                {chartFrameSize.width > 0 && chartFrameSize.height > 0 ? (
                  <LineChart width={chartFrameSize.width} height={chartFrameSize.height} data={chartData}>
                    <CartesianGrid stroke="rgba(148, 163, 184, 0.18)" strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" minTickGap={36} stroke="rgba(102, 112, 133, 0.84)" />
                    <YAxis stroke="rgba(102, 112, 133, 0.84)" />
                    <Tooltip content={<FinlandLinkedChartTooltip />} />
                    {payload.series.map((series, index) => (
                      <Line
                        key={series.field_key}
                        type="monotone"
                        dataKey={series.field_key}
                        name={series.label}
                        stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                ) : null}
              </div>
              <p className="text-sm leading-6 text-[var(--color-muted)]">
                {copy.populatedDescription}
              </p>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
