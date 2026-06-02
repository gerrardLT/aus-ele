/**
 * formatters.js — 通用格式化工具函数
 * 从 InvestmentAnalysis.jsx 提取，供所有投资子组件复用
 */

/**
 * 格式化货币/数值为简写形式 (B/M/K)
 * @param {number|null|undefined} value - 数值
 * @param {string} prefix - 前缀，默认 '$'
 * @returns {string}
 */
export function fmt(value, prefix = '$') {
  if (value === null || value === undefined) return '-';
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${prefix}${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${prefix}${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${prefix}${(value / 1e3).toFixed(0)}K`;
  return `${prefix}${Number(value).toLocaleString()}`;
}
