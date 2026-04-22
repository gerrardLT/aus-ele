import React, { useMemo } from 'react';
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

function HourlyDistributionTooltip({ active, payload, label, t }) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  return (
    <div className="bg-white border border-gray-200 p-3 shadow-md font-sans rounded-md">
      <p className="text-xs text-gray-500 mb-1 tracking-wider uppercase">{t.hourLabel} {label}:00</p>
      <p className="text-xl font-semibold">
        {payload[0].value} <span className="text-xs font-normal text-gray-400">{t.events}</span>
      </p>
    </div>
  );
}

const HourlyDistributionChart = ({ data, t }) => {
  const safeData = useMemo(() => (Array.isArray(data) ? data : []), [data]);

  const threshold = useMemo(() => {
    const sortedCounts = [...safeData].map((item) => item.count).sort((left, right) => right - left);
    return sortedCounts[2] || 0;
  }, [safeData]);

  if (!safeData.length || !t) {
    return null;
  }

  return (
    <div className="w-full flex justify-between h-[300px] mt-6">
      <div className="hidden md:flex flex-col justify-end pb-8 mr-4 w-16 items-end text-xs font-serif text-[var(--color-muted)] tracking-wider">
        <span>{t.incidents}</span>
        <span>{t.count}</span>
      </div>

      <div className="w-full h-full border-b border-[var(--color-border)]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={safeData}
            margin={{ top: 20, right: 0, left: 0, bottom: 5 }}
            barCategoryGap={4}
          >
            <XAxis
              dataKey="hour"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fill: 'var(--color-muted)', fontFamily: 'Inter, sans-serif' }}
              dy={10}
            />
            <Tooltip
              content={<HourlyDistributionTooltip t={t} />}
              cursor={{ fill: 'rgba(0,0,0,0.02)' }}
            />
            <Bar
              dataKey="count"
              radius={[2, 2, 0, 0]}
              animationDuration={1000}
            >
              {safeData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.count >= threshold && entry.count > 0 ? 'var(--color-primary)' : 'var(--color-border)'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default React.memo(HourlyDistributionChart);
