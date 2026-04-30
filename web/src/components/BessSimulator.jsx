import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Cell, ReferenceLine, LabelList,
} from 'recharts';
import { fetchJson } from '../lib/apiClient';

const DEFAULT_PARAMS = {
  capacityMw: 100,
  durationH: 2,
  rte: 85,
  auxPct: 2,
  mlf: 0.95,
  cyclesPerDay: 1,
  aemoFee: 0.5,
  degradationCost: 5,
};

export default function BessSimulator({ year, region, apiBase, t, networkFeeDefault, scopeNote }) {
  const [params, setParams] = useState({ ...DEFAULT_PARAMS });
  const [spread, setSpread] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);

    fetchJson(`${apiBase}/peak-analysis?year=${year}&region=${region}&aggregation=yearly`)
      .then((res) => {
        const summary = res?.summary;
        if (summary) {
          setSpread(summary.avg_spread_4h || 0);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, apiBase]);

  const netFee = networkFeeDefault || 40;

  const waterfallData = useMemo(() => {
    if (spread === null) return [];

    const p = params;
    const grossSpread = spread;
    const rteLoss = grossSpread * ((100 - p.rte) / 100);
    const afterRte = grossSpread - rteLoss;
    const auxLoss = grossSpread * (p.auxPct / 100);
    const afterAux = afterRte - auxLoss;
    const networkCost = netFee * 2;
    const afterNetwork = afterAux - networkCost;
    const mlfLoss = grossSpread * (1 - p.mlf);
    const afterMlf = afterNetwork - mlfLoss;
    const aemoFeeCost = p.aemoFee * 2;
    const afterAemo = afterMlf - aemoFeeCost;
    const degradation = p.degradationCost;
    const netProfit = afterAemo - degradation;

    let running = grossSpread;
    const items = [
      { name: t.wfGross, value: grossSpread, delta: grossSpread, type: 'positive' },
    ];

    const deductions = [
      { name: t.wfRte, loss: rteLoss },
      { name: t.wfAux, loss: auxLoss },
      { name: t.wfNetwork, loss: networkCost },
      { name: t.wfMlf, loss: mlfLoss },
      { name: t.wfAemoFee, loss: aemoFeeCost },
      { name: t.wfDegradation, loss: degradation },
    ];

    for (const deduction of deductions) {
      running -= deduction.loss;
      items.push({
        name: deduction.name,
        value: running,
        delta: -deduction.loss,
        type: 'negative',
        invisible: running + deduction.loss,
      });
    }

    items.push({
      name: t.wfNet,
      value: netProfit,
      delta: netProfit,
      type: netProfit >= 0 ? 'profit' : 'loss',
    });

    return items.map((item, index) => {
      if (index === 0 || index === items.length - 1) {
        return { ...item, base: 0, bar: item.value };
      }
      return { ...item, base: item.value, bar: -item.delta };
    });
  }, [spread, params, netFee, t]);

  const annualEstimate = useMemo(() => {
    if (!waterfallData.length) return null;
    const netPerMwh = waterfallData[waterfallData.length - 1]?.value || 0;
    const dailyRevenue = netPerMwh * params.capacityMw * params.durationH * params.cyclesPerDay;
    const annualRevenue = dailyRevenue * 365;
    return {
      perMwh: netPerMwh,
      daily: dailyRevenue,
      annual: annualRevenue,
    };
  }, [waterfallData, params]);

  const updateParam = (key, val) => {
    setParams((prev) => ({ ...prev, [key]: val }));
  };

  const sliders = [
    { key: 'rte', label: t.pRte, min: 70, max: 95, step: 1, unit: '%' },
    { key: 'auxPct', label: t.pAux, min: 0, max: 8, step: 0.5, unit: '%' },
    { key: 'mlf', label: t.pMlf, min: 0.7, max: 1.05, step: 0.01, unit: '' },
    { key: 'cyclesPerDay', label: t.pCycles, min: 0.5, max: 3, step: 0.5, unit: 'x' },
    { key: 'degradationCost', label: t.pDegradation, min: 0, max: 20, step: 1, unit: '$/MWh' },
    { key: 'aemoFee', label: t.pAemoFee, min: 0, max: 2, step: 0.1, unit: '$/MWh' },
  ];

  const barColor = (type) => {
    if (type === 'positive') return '#2563eb';
    if (type === 'negative') return '#ef4444';
    if (type === 'profit') return '#10b981';
    return '#ef4444';
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
      className="col-span-12 mt-16 pt-12 border-t-2 border-[var(--color-text)]"
    >
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-10">
        <div>
          <h2 className="text-3xl font-serif font-bold mb-1">{t.simTitle}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">{t.simSubtitle}</p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          {t.eyebrow}
        </div>
      </div>

      {scopeNote && (
        <div className="mb-8 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">
          {scopeNote}
        </div>
      )}

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 space-y-5">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
                {t.pCapacity}
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  value={params.capacityMw}
                  min={1}
                  step={10}
                  onChange={(e) => updateParam('capacityMw', parseFloat(e.target.value) || 100)}
                  className="w-20 px-2 py-1 text-sm font-mono border border-[var(--color-border)] bg-transparent rounded focus:outline-none"
                />
                <span className="text-xs text-[var(--color-muted)]">{t.capacityMwUnit}</span>
                <span className="text-[var(--color-muted)]">/</span>
                <input
                  type="number"
                  value={params.durationH}
                  min={1}
                  max={8}
                  step={1}
                  onChange={(e) => updateParam('durationH', parseFloat(e.target.value) || 2)}
                  className="w-16 px-2 py-1 text-sm font-mono border border-[var(--color-border)] bg-transparent rounded focus:outline-none"
                />
                <span className="text-xs text-[var(--color-muted)]">{t.durationHoursUnit}</span>
              </div>
            </div>

            {sliders.map((slider) => (
              <div key={slider.key} className="flex flex-col gap-1.5">
                <div className="flex justify-between items-center">
                  <label className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">{slider.label}</label>
                  <span className="text-sm font-mono font-bold">{params[slider.key]}{slider.unit}</span>
                </div>
                <input
                  type="range"
                  min={slider.min}
                  max={slider.max}
                  step={slider.step}
                  value={params[slider.key]}
                  onChange={(e) => updateParam(slider.key, parseFloat(e.target.value))}
                  className="w-full accent-[var(--color-text)] h-1.5 bg-[var(--color-border)] rounded-full appearance-none cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-[var(--color-muted)]">
                  <span>{slider.min}{slider.unit}</span>
                  <span>{slider.max}{slider.unit}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="lg:col-span-2">
            {annualEstimate && (
              <div className="grid grid-cols-3 gap-3 mb-6">
                <div className={`border p-3 rounded ${annualEstimate.perMwh >= 0 ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
                  <div className="text-xs tracking-widest uppercase text-[var(--color-muted)] mb-1">{t.netPerMwh}</div>
                  <div className={`text-2xl font-mono font-bold ${annualEstimate.perMwh >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                    ${annualEstimate.perMwh.toFixed(1)}
                  </div>
                </div>
                <div className="border border-[var(--color-border)] p-3 rounded">
                  <div className="text-xs tracking-widest uppercase text-[var(--color-muted)] mb-1">{t.dailyRev}</div>
                  <div className="text-2xl font-mono font-bold">${(annualEstimate.daily / 1000).toFixed(1)}k</div>
                </div>
                <div className="border border-[var(--color-text)] bg-[var(--color-inverted)] p-3 rounded">
                  <div className="text-xs tracking-widest uppercase text-[var(--color-inverted-text)] opacity-70 mb-1">{t.annualRev}</div>
                  <div className="text-2xl font-mono font-bold text-[var(--color-inverted-text)]">
                    ${(annualEstimate.annual / 1000000).toFixed(2)}M
                  </div>
                </div>
              </div>
            )}

            <div className="h-[400px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={waterfallData} margin={{ top: 20, right: 20, left: 10, bottom: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                    tickLine={false}
                    angle={-25}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value) => `$${value}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 12,
                    }}
                    formatter={(value, name) => {
                      if (name === 'base') return [null, null];
                      return [`$${Number(value).toFixed(1)}/MWh`, ''];
                    }}
                  />
                  <ReferenceLine y={0} stroke="var(--color-text)" strokeWidth={1} />
                  <Bar dataKey="base" stackId="stack" fill="transparent" />
                  <Bar dataKey="bar" stackId="stack" radius={[3, 3, 0, 0]}>
                    {waterfallData.map((entry, index) => (
                      <Cell key={index} fill={barColor(entry.type)} fillOpacity={0.85} />
                    ))}
                    <LabelList
                      dataKey="delta"
                      position="top"
                      formatter={(value) => `${value >= 0 ? '+' : ''}$${Number(value).toFixed(1)}`}
                      style={{ fontSize: 10, fill: 'var(--color-muted)', fontFamily: 'monospace' }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
}
