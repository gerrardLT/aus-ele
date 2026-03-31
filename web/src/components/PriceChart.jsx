import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function PriceChart({ data, t }) {
  if (!data || data.length === 0 || !t) {
    return <div className="h-full w-full flex items-center justify-center text-gray-300 font-sans">{t?.noRecords}</div>;
  }

  // Format the time label for minimal tooltip / axis
  const formatTime = (timeStr) => {
    // Expected 'YYYY-MM-DD HH:MM:SS'
    // Let's just return MM-DD for x-axis to keep it clean, and HH:MM for tooltip
    try {
      const parts = timeStr.split(' ');
      const dateParts = parts[0].split('-'); // [YYYY, MM, DD]
      return `${dateParts[1]}/${dateParts[2]} ${parts[1].substring(0, 5)}`;
    } catch {
      return timeStr;
    }
  };

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload;
      return (
        <div className="bg-white border border-gray-200 p-3 shadow-md font-sans rounded-md">
          <p className="text-xs text-gray-500 mb-1 tracking-wider uppercase">{formatTime(point.time)}</p>
          <p className="text-xl font-semibold"><span className="text-xs font-normal text-gray-400 mr-1">A$</span>{point.price}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <XAxis 
            dataKey="time" 
            tickFormatter={(val) => val.substring(5, 10)} // just show MM-DD
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
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'var(--color-border)', strokeWidth: 1, strokeDasharray: '4 4' }} />
          <Line 
            type="monotone" 
            dataKey="price" 
            stroke="#0047FF" 
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 4, fill: "#0047FF", stroke: "white", strokeWidth: 2 }}
            isAnimationActive={true}
            animationDuration={800}
            animationEasing="ease-out"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
