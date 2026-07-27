/**
 * ChartRenderer — Pure SVG chart component (zero external dependencies).
 * Renders line/bar/scatter/area charts from JSON spec returned by generate_chart tool.
 */

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];
const WIDTH = 600;
const HEIGHT = 280;
const PAD = { top: 30, right: 20, bottom: 40, left: 60 };

export default function ChartRenderer({ chart }) {
  if (!chart || !chart.data || chart.data.length === 0) return null;

  const { type = 'line', title = '', data, x_label = '', y_label = '' } = chart;
  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;

  // Extract numeric values
  const points = data.map((d, i) => ({
    x: d.x !== undefined ? d.x : d.label !== undefined ? d.label : i,
    y: parseFloat(d.y !== undefined ? d.y : d.value !== undefined ? d.value : 0) || 0,
  }));

  const yValues = points.map((p) => p.y);
  const yMin = Math.min(0, ...yValues);
  const yMax = Math.max(...yValues);
  const yRange = yMax - yMin || 1;

  // Scale functions
  const scaleX = (i) => PAD.left + (i / Math.max(points.length - 1, 1)) * plotW;
  const scaleY = (v) => PAD.top + plotH - ((v - yMin) / yRange) * plotH;

  // Y-axis ticks (5 ticks)
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const val = yMin + (yRange * i) / 4;
    return { val, y: scaleY(val) };
  });

  // X-axis labels (max 8)
  const xStep = Math.max(1, Math.floor(points.length / 8));
  const xLabels = points.filter((_, i) => i % xStep === 0);

  // Build path for line/area
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${scaleX(i).toFixed(1)},${scaleY(p.y).toFixed(1)}`).join(' ');
  const areaPath = linePath + ` L${scaleX(points.length - 1).toFixed(1)},${scaleY(yMin).toFixed(1)} L${scaleX(0).toFixed(1)},${scaleY(yMin).toFixed(1)} Z`;

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      {title && <div className="mb-2 text-[12px] font-medium text-[var(--color-text)]">{title}</div>}
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" style={{ maxHeight: 300 }}>
        {/* Grid lines */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} y1={t.y} x2={WIDTH - PAD.right} y2={t.y} stroke="var(--color-border)" strokeWidth="0.5" />
            <text x={PAD.left - 8} y={t.y + 4} textAnchor="end" fontSize="9" fill="var(--color-muted)">
              {t.val >= 1000 ? `${(t.val / 1000).toFixed(0)}k` : t.val.toFixed(0)}
            </text>
          </g>
        ))}

        {/* X labels */}
        {xLabels.map((p, i) => {
          const idx = points.indexOf(p);
          return (
            <text key={i} x={scaleX(idx)} y={HEIGHT - 8} textAnchor="middle" fontSize="8" fill="var(--color-muted)">
              {String(p.x).slice(0, 10)}
            </text>
          );
        })}

        {/* Chart body */}
        {type === 'bar' ? (
          points.map((p, i) => {
            const barW = Math.max(2, plotW / points.length - 2);
            const barH = ((p.y - yMin) / yRange) * plotH;
            return (
              <rect
                key={i}
                x={scaleX(i) - barW / 2}
                y={scaleY(p.y)}
                width={barW}
                height={Math.max(0, barH)}
                fill={COLORS[i % COLORS.length]}
                opacity="0.8"
                rx="1"
              />
            );
          })
        ) : type === 'scatter' ? (
          points.map((p, i) => (
            <circle key={i} cx={scaleX(i)} cy={scaleY(p.y)} r="3" fill={COLORS[0]} opacity="0.6" />
          ))
        ) : (
          <g>
            {type === 'area' && <path d={areaPath} fill={COLORS[0]} opacity="0.1" />}
            <path d={linePath} fill="none" stroke={COLORS[0]} strokeWidth="1.5" />
          </g>
        )}

        {/* Axis labels */}
        {y_label && (
          <text x={12} y={PAD.top + plotH / 2} textAnchor="middle" fontSize="9" fill="var(--color-muted)" transform={`rotate(-90, 12, ${PAD.top + plotH / 2})`}>
            {y_label}
          </text>
        )}
        {x_label && (
          <text x={PAD.left + plotW / 2} y={HEIGHT - 0} textAnchor="middle" fontSize="9" fill="var(--color-muted)">
            {x_label}
          </text>
        )}
      </svg>
    </div>
  );
}
