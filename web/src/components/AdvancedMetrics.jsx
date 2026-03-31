import React from 'react';

const MetricBlock = ({ label, value, unit, emphasis = false, color = "var(--color-text)" }) => (
  <div className={`py-4 border-b border-[var(--color-border)] flex flex-col justify-between h-full`}>
    <div className="text-[10px] font-bold tracking-widest text-[var(--color-muted)] uppercase mb-2">
      {label}
    </div>
    <div className="flex items-baseline">
      <span 
        className={`font-serif ${emphasis ? 'text-4xl' : 'text-3xl'} tracking-tight`}
        style={{ color: color }}
      >
        {value !== undefined && value !== null ? value : '--'}
      </span>
      {unit && (
        <span className="ml-1 text-sm font-sans text-[var(--color-muted)]">{unit}</span>
      )}
    </div>
  </div>
);

const AdvancedMetrics = ({ advancedStats, t }) => {
  if (!advancedStats || !t) return null;

  return (
    <div className="w-full h-full flex flex-col">
      <h3 className="text-xl font-serif mb-6 italic text-[var(--color-muted)]">
        {t.title}
      </h3>
      
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-2">
        
        {/* Negative Pricing Section */}
        <MetricBlock 
          label={t.negFreq} 
          value={advancedStats.neg_ratio} 
          unit="%" 
          color="#0047FF"
          emphasis={true}
        />
        <MetricBlock 
          label={t.negMean} 
          value={advancedStats.neg_avg} 
          unit="A$" 
        />
        <MetricBlock 
          label={t.negFloor} 
          value={advancedStats.neg_min} 
          unit="A$" 
        />

        {/* Positive Pricing Section */}
        <MetricBlock 
          label={t.posDays} 
          value={advancedStats.days_above_300} 
          unit="Days" 
        />
        <MetricBlock 
          label={t.posMean} 
          value={advancedStats.pos_avg} 
          unit="A$" 
        />
        <MetricBlock 
          label={t.posCeiling} 
          value={advancedStats.pos_max} 
          unit="A$" 
        />

        {/* Floor Days below -100 */}
        <div className="col-span-2 md:col-span-3 mt-4">
            <MetricBlock 
              label={t.floorDays} 
              value={advancedStats.days_below_100} 
              unit={t.uniqueDays} 
              emphasis={true}
            />
        </div>

      </div>
    </div>
  );
};

export default AdvancedMetrics;
