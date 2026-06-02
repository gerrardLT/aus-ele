/**
 * EventAnnotationOverlay — 可复用的 Recharts 事件标注叠加层组件
 *
 * 在任意时间序列图表上叠加事件标记，支持三种事件类型的视觉区分：
 * - 煤电退役 (coal_closure): 红色倒三角 ▼
 * - BESS 投运 (bess_commissioning): 蓝色正三角 ▲
 * - 网络增强 (network_augmentation): 绿色菱形 ◆
 *
 * 支持事件聚类（圆形 + 数字计数）和点击详情面板。
 * 调用 GET /api/v1/narrative/events/{region} 获取数据。
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 11.1, 11.2, 11.3, 11.4
 */

import { useEffect, useState, useCallback } from 'react';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

// ---------------------------------------------------------------------------
// 事件类型视觉配置
// ---------------------------------------------------------------------------

const EVENT_STYLES = {
  coal_closure: { color: '#ef4444', label: '煤电退役', labelEn: 'Coal Closure' },
  bess_commissioning: { color: '#3b82f6', label: 'BESS 投运', labelEn: 'BESS Commissioning' },
  network_augmentation: { color: '#22c55e', label: '网络增强', labelEn: 'Network Augmentation' },
};

const CLUSTER_COLOR = '#6b7280';

// ---------------------------------------------------------------------------
// SVG 标记渲染函数
// ---------------------------------------------------------------------------

/** 煤电退役：红色倒三角 ▼ */
function CoalClosureMarker({ x, y, size = 10 }) {
  const half = size / 2;
  const points = `${x},${y + half} ${x - half},${y - half} ${x + half},${y - half}`;
  return <polygon points={points} fill={EVENT_STYLES.coal_closure.color} stroke="none" />;
}

/** BESS 投运：蓝色正三角 ▲ */
function BessCommissioningMarker({ x, y, size = 10 }) {
  const half = size / 2;
  const points = `${x},${y - half} ${x - half},${y + half} ${x + half},${y + half}`;
  return <polygon points={points} fill={EVENT_STYLES.bess_commissioning.color} stroke="none" />;
}

/** 网络增强：绿色菱形 ◆ */
function NetworkAugmentationMarker({ x, y, size = 10 }) {
  const half = size / 2;
  const points = `${x},${y - half} ${x + half},${y} ${x},${y + half} ${x - half},${y}`;
  return <polygon points={points} fill={EVENT_STYLES.network_augmentation.color} stroke="none" />;
}

/** 聚类标记：圆形 + 数字计数 */
function ClusterMarker({ x, y, count, size = 14 }) {
  return (
    <g>
      <circle cx={x} cy={y} r={size} fill={CLUSTER_COLOR} opacity={0.85} />
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="central"
        fill="#fff"
        fontSize={count > 9 ? 9 : 10}
        fontWeight="bold"
      >
        {count}
      </text>
    </g>
  );
}

/** 根据事件类型渲染对应标记 */
function EventMarker({ eventType, x, y, size = 10 }) {
  switch (eventType) {
    case 'coal_closure':
      return <CoalClosureMarker x={x} y={y} size={size} />;
    case 'bess_commissioning':
      return <BessCommissioningMarker x={x} y={y} size={size} />;
    case 'network_augmentation':
      return <NetworkAugmentationMarker x={x} y={y} size={size} />;
    default:
      return <circle cx={x} cy={y} r={size / 2} fill="#9ca3af" />;
  }
}

// ---------------------------------------------------------------------------
// 聚类辅助函数
// ---------------------------------------------------------------------------

function buildGroupItem(group) {
  if (group.length === 1) {
    return { type: 'single', data: group[0] };
  }
  // 聚类
  const dates = group.map((e) => new Date(e.date).getTime());
  const centerTime = (Math.min(...dates) + Math.max(...dates)) / 2;
  const centerDate = new Date(centerTime).toISOString().split('T')[0];

  // 确定主导类型
  const typeCounts = {};
  group.forEach((e) => {
    typeCounts[e.event_type] = (typeCounts[e.event_type] || 0) + 1;
  });
  const dominantType = Object.entries(typeCounts).sort((a, b) => b[1] - a[1])[0][0];

  return {
    type: 'cluster',
    data: {
      center_date: centerDate,
      event_count: group.length,
      events: group,
      dominant_type: dominantType,
    },
  };
}

// ---------------------------------------------------------------------------
// 详情面板组件
// ---------------------------------------------------------------------------

function EventDetailPanel({ event, onClose, lang = 'zh' }) {
  if (!event) return null;

  const style = EVENT_STYLES[event.event_type] || {};
  const isZh = lang === 'zh';

  return (
    <div className="absolute z-50 bg-[var(--color-bg,#fff)] border border-[var(--color-border,#e5e7eb)] rounded-lg shadow-lg p-4 min-w-[260px] max-w-[340px]">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="inline-block w-3 h-3 rounded-sm"
            style={{ backgroundColor: style.color }}
          />
          <span className="text-sm font-serif font-bold">
            {event.event_name}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--color-muted,#9ca3af)] hover:text-[var(--color-text,#111)] text-lg leading-none"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {/* 详情字段 */}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
        <dt className="text-[var(--color-muted,#9ca3af)]">{isZh ? '类型' : 'Type'}</dt>
        <dd className="font-mono">{isZh ? style.label : style.labelEn}</dd>

        <dt className="text-[var(--color-muted,#9ca3af)]">{isZh ? '区域' : 'Region'}</dt>
        <dd className="font-mono">{event.region}</dd>

        <dt className="text-[var(--color-muted,#9ca3af)]">{isZh ? '容量' : 'Capacity'}</dt>
        <dd className="font-mono">{event.capacity_mw} MW</dd>

        <dt className="text-[var(--color-muted,#9ca3af)]">{isZh ? '日期' : 'Date'}</dt>
        <dd className="font-mono">{event.date}</dd>

        <dt className="text-[var(--color-muted,#9ca3af)]">{isZh ? '置信度' : 'Confidence'}</dt>
        <dd className="font-mono capitalize">{event.confidence}</dd>

        <dt className="text-[var(--color-muted,#9ca3af)]">{isZh ? '影响因子' : 'Impact Factor'}</dt>
        <dd className="font-mono">{event.spread_impact_factor?.toFixed(3)}</dd>
      </dl>
    </div>
  );
}

/** 聚类展开面板 - 显示聚类内所有事件 */
function ClusterDetailPanel({ cluster, onEventClick, onClose, lang = 'zh' }) {
  if (!cluster) return null;
  const isZh = lang === 'zh';

  return (
    <div className="absolute z-50 bg-[var(--color-bg,#fff)] border border-[var(--color-border,#e5e7eb)] rounded-lg shadow-lg p-4 min-w-[280px] max-w-[360px]">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-serif font-bold">
          {isZh ? `${cluster.event_count} 个事件` : `${cluster.event_count} Events`}
        </span>
        <button
          onClick={onClose}
          className="text-[var(--color-muted,#9ca3af)] hover:text-[var(--color-text,#111)] text-lg leading-none"
          aria-label="Close"
        >
          ×
        </button>
      </div>
      <ul className="space-y-1.5 max-h-[200px] overflow-y-auto">
        {cluster.events.map((evt, idx) => {
          const style = EVENT_STYLES[evt.event_type] || {};
          return (
            <li
              key={idx}
              className="flex items-center gap-2 text-xs cursor-pointer hover:bg-[var(--color-border,#f3f4f6)] rounded px-1.5 py-1"
              onClick={() => onEventClick(evt)}
            >
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm flex-shrink-0"
                style={{ backgroundColor: style.color }}
              />
              <span className="font-mono truncate">{evt.event_name}</span>
              <span className="text-[var(--color-muted,#9ca3af)] ml-auto flex-shrink-0">
                {evt.date}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主组件：EventAnnotationOverlay
// ---------------------------------------------------------------------------

/**
 * EventAnnotationOverlay — Recharts 自定义叠加层组件
 *
 * 用法：作为 Recharts 图表的子组件使用，或独立使用并传入 xScale 函数。
 *
 * Props:
 * - region: 区域代码（可选，默认从 FilterContext 获取）
 * - startYear / endYear: 时间范围（可选）
 * - annotations: 外部传入的标注数据（可选，传入则跳过 API 调用）
 * - xScale: x 轴比例尺函数 year → pixel x 坐标
 * - chartWidth / chartHeight: 图表尺寸
 * - yOffset: 标记 y 坐标偏移（默认 20，从顶部算起）
 * - onEventClick: 外部事件点击回调（可选）
 * - lang: 语言 'zh' | 'en'
 */
export default function EventAnnotationOverlay({
  region: regionProp,
  startYear,
  endYear,
  annotations: externalAnnotations,
  xScale,
  chartWidth,
  chartHeight,
  yOffset = 20,
  onEventClick: externalOnEventClick,
  lang = 'zh',
}) {
  const { filters } = useFilters();
  const region = regionProp || filters.region;

  const [annotations, setAnnotations] = useState(externalAnnotations || []);
  const [loading, setLoading] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [selectedCluster, setSelectedCluster] = useState(null);
  const [panelPosition, setPanelPosition] = useState({ x: 0, y: 0 });

  // 确定时间范围
  const currentYear = new Date().getFullYear();
  const effectiveStartYear = startYear || currentYear;
  const effectiveEndYear = endYear || currentYear + 20;

  // ---------------------------------------------------------------------------
  // 数据获取
  // ---------------------------------------------------------------------------

  useEffect(() => {
    // 如果外部传入了 annotations，直接使用
    if (externalAnnotations) {
      setAnnotations(externalAnnotations);
      return;
    }

    if (!region) return;

    setLoading(true);
    const params = new URLSearchParams({
      start_year: String(effectiveStartYear),
      end_year: String(effectiveEndYear),
    });

    fetchJson(`${API_BASE}/v1/narrative/events/${region}?${params}`)
      .then((res) => {
        setAnnotations(res.annotations || []);
        setLoading(false);
      })
      .catch(() => {
        setAnnotations([]);
        setLoading(false);
      });
  }, [region, effectiveStartYear, effectiveEndYear, externalAnnotations]);

  // ---------------------------------------------------------------------------
  // 事件聚类逻辑（前端简化版）
  // ---------------------------------------------------------------------------

  const clusteredItems = useCallback(() => {
    if (!annotations.length || !xScale) return [];

    // 按日期排序
    const sorted = [...annotations].sort(
      (a, b) => new Date(a.date) - new Date(b.date)
    );

    const PIXEL_THRESHOLD = 20;
    const items = [];
    let currentGroup = [sorted[0]];

    for (let i = 1; i < sorted.length; i++) {
      const prevYear = new Date(currentGroup[0].date).getFullYear();
      const currYear = new Date(sorted[i].date).getFullYear();
      const prevX = xScale(prevYear);
      const currX = xScale(currYear);

      if (Math.abs(currX - prevX) <= PIXEL_THRESHOLD) {
        currentGroup.push(sorted[i]);
      } else {
        items.push(buildGroupItem(currentGroup));
        currentGroup = [sorted[i]];
      }
    }
    items.push(buildGroupItem(currentGroup));

    return items;
  }, [annotations, xScale]);

  // ---------------------------------------------------------------------------
  // 交互处理
  // ---------------------------------------------------------------------------

  function handleMarkerClick(item, pixelX) {
    if (item.type === 'cluster') {
      setSelectedCluster(item.data);
      setSelectedEvent(null);
    } else {
      setSelectedEvent(item.data);
      setSelectedCluster(null);
      if (externalOnEventClick) externalOnEventClick(item.data);
    }
    // 面板定位：标记右侧偏移
    setPanelPosition({ x: pixelX + 16, y: yOffset + 24 });
  }

  function handleClusterEventClick(evt) {
    setSelectedCluster(null);
    setSelectedEvent(evt);
    if (externalOnEventClick) externalOnEventClick(evt);
  }

  function closePanel() {
    setSelectedEvent(null);
    setSelectedCluster(null);
  }

  // ---------------------------------------------------------------------------
  // 默认 xScale（如果未提供，基于 chartWidth 和时间范围线性映射）
  // ---------------------------------------------------------------------------

  const effectiveXScale = xScale || ((year) => {
    if (!chartWidth) return 0;
    const range = effectiveEndYear - effectiveStartYear;
    if (range <= 0) return 0;
    return ((year - effectiveStartYear) / range) * chartWidth;
  });

  // ---------------------------------------------------------------------------
  // 渲染
  // ---------------------------------------------------------------------------

  if (loading) return null;
  if (!annotations.length) return null;

  const items = clusteredItems();

  return (
    <div className="relative" style={{ width: chartWidth, height: chartHeight }}>
      {/* SVG 叠加层 */}
      <svg
        className="absolute inset-0 pointer-events-none"
        width={chartWidth}
        height={chartHeight}
        style={{ overflow: 'visible' }}
      >
        {items.map((item, idx) => {
          if (item.type === 'cluster') {
            const year = new Date(item.data.center_date).getFullYear();
            const x = effectiveXScale(year);
            return (
              <g
                key={`cluster-${idx}`}
                className="pointer-events-auto cursor-pointer"
                onClick={() => handleMarkerClick(item, x)}
              >
                <ClusterMarker x={x} y={yOffset} count={item.data.event_count} />
              </g>
            );
          } else {
            const year = new Date(item.data.date).getFullYear();
            const x = effectiveXScale(year);
            return (
              <g
                key={`event-${idx}`}
                className="pointer-events-auto cursor-pointer"
                onClick={() => handleMarkerClick(item, x)}
              >
                <EventMarker eventType={item.data.event_type} x={x} y={yOffset} />
              </g>
            );
          }
        })}
      </svg>

      {/* 详情面板 */}
      {selectedEvent && (
        <div style={{ position: 'absolute', left: panelPosition.x, top: panelPosition.y }}>
          <EventDetailPanel event={selectedEvent} onClose={closePanel} lang={lang} />
        </div>
      )}

      {selectedCluster && (
        <div style={{ position: 'absolute', left: panelPosition.x, top: panelPosition.y }}>
          <ClusterDetailPanel
            cluster={selectedCluster}
            onEventClick={handleClusterEventClick}
            onClose={closePanel}
            lang={lang}
          />
        </div>
      )}

      {/* 图例 */}
      <div className="absolute bottom-2 right-2 flex items-center gap-3 text-[10px] text-[var(--color-muted,#9ca3af)]">
        {Object.entries(EVENT_STYLES).map(([type, style]) => (
          <span key={type} className="flex items-center gap-1">
            <span
              className="inline-block w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: style.color }}
            />
            {lang === 'zh' ? style.label : style.labelEn}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 导出辅助：Recharts CustomizedDot 兼容接口
// ---------------------------------------------------------------------------

/**
 * EventAnnotationDot — 可作为 Recharts <Line dot={...} /> 使用的标记渲染器
 *
 * 用法示例：
 * <Line dot={<EventAnnotationDot annotations={annotations} />} />
 */
export function EventAnnotationDot({ cx, cy, payload, annotations = [] }) {
  if (!payload || !annotations.length) return null;

  const year = payload.year;
  const matchingEvents = annotations.filter(
    (a) => new Date(a.date).getFullYear() === year
  );

  if (!matchingEvents.length) return null;

  if (matchingEvents.length > 1) {
    return <ClusterMarker x={cx} y={cy - 16} count={matchingEvents.length} size={10} />;
  }

  return (
    <EventMarker
      eventType={matchingEvents[0].event_type}
      x={cx}
      y={cy - 16}
      size={8}
    />
  );
}
