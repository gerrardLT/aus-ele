import { memo, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceArea } from 'recharts';
import { getEventText, metaForState } from '../lib/eventOverlays';

function formatPriceChartTime(timeStr) {
  try {
    const parts = timeStr.split(' ');
    const dateParts = parts[0].split('-');
    return `${dateParts[1]}/${dateParts[2]} ${parts[1].substring(0, 5)}`;
  } catch {
    return timeStr;
  }
}

function PriceChartTooltip({ active, payload, locale = 'en', eventContextLabel }) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 p-3 shadow-md font-sans rounded-md">
      <p className="text-xs text-gray-500 mb-1 tracking-wider uppercase">{formatPriceChartTime(point.time)}</p>
      <p className="text-xl font-semibold"><span className="text-xs font-normal text-gray-400 mr-1">A$</span>{point.price}</p>
      {point.event_rollup?.top_states?.length > 0 && (
        <div className="mt-3 border-t border-gray-100 pt-2">
          <div className="text-[10px] tracking-widest uppercase text-gray-400">{eventContextLabel}</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {point.event_rollup.top_states.slice(0, 3).map((state) => {
              const meta = metaForState(state.key, locale);
              return (
                <span
                  key={state.key}
                  className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium"
                  style={{ color: meta.color, backgroundColor: meta.softColor }}
                >
                  {meta.label}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const PriceChart = ({ data, t, overlay, locale = 'en' }) => {
  const safeData = useMemo(() => (Array.isArray(data) ? data : []), [data]);
  const eventText = getEventText(locale);

  const eventRollupByDate = useMemo(
    () => new Map((overlay?.daily_rollup || []).map((row) => [row.date, row])),
    [overlay],
  );

  const decoratedData = useMemo(
    () => safeData.map((point) => ({
      ...point,
      event_rollup: eventRollupByDate.get(point.time?.slice(0, 10)) || null,
    })),
    [safeData, eventRollupByDate],
  );

  const referenceAreas = useMemo(() => {
    const states = overlay?.states || [];
    return states.slice(0, 12).map((state) => {
      const matching = decoratedData.filter((point) => point.time >= state.start_time && point.time <= state.end_time);
      if (!matching.length) return null;
      return {
        stateId: state.state_id,
        x1: matching[0].time,
        x2: matching[matching.length - 1].time,
        stateType: state.state_type,
      };
    }).filter(Boolean);
  }, [overlay, decoratedData]);

  if (!safeData.length || !t) {
    return <div className="h-full w-full flex items-center justify-center text-gray-300 font-sans">{t?.noRecords}</div>;
  }

  return (
    <div className="w-full h-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={decoratedData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          {referenceAreas.map((area) => {
            const meta = metaForState(area.stateType, locale);
            return (
              <ReferenceArea
                key={area.stateId}
                x1={area.x1}
                x2={area.x2}
                strokeOpacity={0}
                fill={meta.softColor}
                fillOpacity={0.45}
              />
            );
          })}
          <XAxis
            dataKey="time"
            tickFormatter={(val) => val.substring(5, 10)}
            tick={{ fill: '#8E8E8E', fontSize: 11, fontFamily: 'var(--font-sans)' }}
            axisLine={false}
            tickLine={false}
            minTickGap={60}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fill: '#8E8E8E', fontSize: 11, fontFamily: 'var(--font-sans)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(val) => `$${val}`}
          />
          <Tooltip
            content={<PriceChartTooltip locale={locale} eventContextLabel={eventText.eventContext} />}
            cursor={{ stroke: 'var(--color-border)', strokeWidth: 1, strokeDasharray: '4 4' }}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="var(--color-primary)"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 4, fill: 'var(--color-primary)', stroke: 'var(--color-bg)', strokeWidth: 2 }}
            isAnimationActive
            animationDuration={800}
            animationEasing="ease-out"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default memo(PriceChart);
