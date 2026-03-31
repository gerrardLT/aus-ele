import React, { useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const HourlyDistributionChart = ({ data, t }) => {
  if (!data || data.length === 0 || !t) return null;

  // Find the threshold for the top 3 hours to highlight them
  const threshold = useMemo(() => {
    const sortedCounts = [...data].map(d => d.count).sort((a, b) => b - a);
    return sortedCounts[2] || 0; // The count of the 3rd highest bar
  }, [data]);

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white border border-gray-200 p-3 shadow-md font-sans rounded-md">
          <p className="text-xs text-gray-500 mb-1 tracking-wider uppercase">{t.hourLabel} {label}:00</p>
          <p className="text-xl font-semibold">
            {payload[0].value} <span className="text-xs font-normal text-gray-400">{t.events}</span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full flex justify-between h-[300px] mt-6">
      
      {/* Left Axis Info (Minimal) */}
      <div className="hidden md:flex flex-col justify-end pb-8 mr-4 w-16 items-end text-xs font-serif text-[var(--color-muted)] tracking-wider">
        <span>{t.incidents}</span>
        <span>{t.count}</span>
      </div>

      <div className="w-full h-full border-b border-[var(--color-border)]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 20, right: 0, left: 0, bottom: 5 }}
            barCategoryGap={4}
          >
            <XAxis 
              dataKey="hour" 
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fill: "var(--color-muted)", fontFamily: "Inter, sans-serif" }}
              dy={10}
            />
            <Tooltip 
              content={<CustomTooltip />}
              cursor={{ fill: 'rgba(0,0,0,0.02)' }}
            />
            <Bar 
              dataKey="count" 
              radius={[2, 2, 0, 0]}
              animationDuration={1000}
            >
              {data.map((entry, index) => (
                <Cell 
                  key={`cell-${index}`} 
                  fill={entry.count >= threshold && entry.count > 0 ? '#0047FF' : '#E5E7EB'} 
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

    </div>
  );
};

export default HourlyDistributionChart;
