import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchJson } from '../../lib/apiClient';
import { buildFinlandBoardChartUrl } from '../../lib/finlandApi';

const SERIES_COLORS = ['#5eead4', '#f59e0b', '#38bdf8', '#fb7185'];

function FinlandLinkedChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-sm shadow-lg">
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
    <section className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
        {copy.eyebrow}
      </div>
      <div className="mt-3 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[linear-gradient(160deg,rgba(15,23,42,0.86),rgba(18,24,38,0.92))]">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <h3 className="text-base font-semibold text-[var(--color-text)]">
            {copy.title}
          </h3>
          <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-2 py-1 text-[11px] font-semibold text-cyan-200">
            {selectedFields.length} {copy.selectionCountSuffix}
          </span>
        </div>
        <div className="grid gap-4 p-4">
          {!hasSelection ? (
            <div className="grid h-52 place-items-center rounded-md border border-dashed border-cyan-300/25 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_55%),linear-gradient(180deg,rgba(15,23,42,0.65),rgba(15,23,42,0.92))] text-center">
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
            <div className="grid h-52 place-items-center rounded-md border border-dashed border-cyan-300/25 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_55%),linear-gradient(180deg,rgba(15,23,42,0.65),rgba(15,23,42,0.92))] text-sm text-[var(--color-muted)]">
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
              <div className="h-72 min-w-0 rounded-md border border-cyan-300/20 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.12),transparent_55%),linear-gradient(180deg,rgba(15,23,42,0.72),rgba(15,23,42,0.94))] p-3">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={240}>
                  <LineChart data={chartData}>
                    <CartesianGrid stroke="rgba(148,163,184,0.16)" strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" minTickGap={36} stroke="rgba(148,163,184,0.72)" />
                    <YAxis stroke="rgba(148,163,184,0.72)" />
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
                </ResponsiveContainer>
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
