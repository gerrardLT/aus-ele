/**
 * NarrativeLayer 组件集成测试
 *
 * 覆盖 investment-narrative-layer 的所有前端组件：
 * 1. ForwardSpreadCurve — 前瞻价差曲线
 * 2. RevenueStratificationChart — 收入分层图
 * 3. EventAnnotationOverlay — 事件标注叠加层
 * 4. AssumptionPanel — 假设透明面板
 * 5. AssetConfigPanel — 资产配置面板
 * 6. CrossValidationTable — 交叉验证表
 * 7. NarrativeTooltip — 因果归因提示
 * 8. FuelSensitivityTable — 燃料敏感性表
 * 9. NetworkImpactDisplay — 网络增强对比
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// ─── Mock 依赖 ───────────────────────────────────────────────────────────────

vi.mock('../../../lib/apiClient', () => ({
  fetchJson: vi.fn(),
}));

vi.mock('../../../lib/apiBase', () => ({
  getApiBase: vi.fn(() => '/api'),
}));

vi.mock('../../../contexts/FilterContext', () => ({
  useFilters: vi.fn(() => ({
    filters: { region: 'NSW1', year: 2025, market: 'NEM' },
    setFilter: vi.fn(),
    resetFilters: vi.fn(),
  })),
}));

// Mock recharts 以避免 SVG 渲染问题
vi.mock('recharts', () => {
  const MockResponsiveContainer = ({ children }) => <div data-testid="responsive-container">{children}</div>;
  const MockAreaChart = ({ children }) => <div data-testid="area-chart">{children}</div>;
  const MockComposedChart = ({ children }) => <div data-testid="composed-chart">{children}</div>;
  const MockArea = () => <div data-testid="area" />;
  const MockLine = () => <div data-testid="line" />;
  const MockXAxis = () => <div data-testid="x-axis" />;
  const MockYAxis = () => <div data-testid="y-axis" />;
  const MockCartesianGrid = () => <div data-testid="cartesian-grid" />;
  const MockTooltip = () => <div data-testid="tooltip" />;
  const MockLegend = () => <div data-testid="legend" />;

  return {
    ResponsiveContainer: MockResponsiveContainer,
    AreaChart: MockAreaChart,
    ComposedChart: MockComposedChart,
    Area: MockArea,
    Line: MockLine,
    XAxis: MockXAxis,
    YAxis: MockYAxis,
    CartesianGrid: MockCartesianGrid,
    Tooltip: MockTooltip,
    Legend: MockLegend,
  };
});

import { fetchJson } from '../../../lib/apiClient';
import ForwardSpreadCurve from '../ForwardSpreadCurve';
import RevenueStratificationChart from '../RevenueStratificationChart';
import EventAnnotationOverlay from '../EventAnnotationOverlay';
import AssumptionPanel from '../AssumptionPanel';
import AssetConfigPanel from '../AssetConfigPanel';
import CrossValidationTable from '../CrossValidationTable';
import NarrativeTooltip from '../NarrativeTooltip';
import FuelSensitivityTable from '../FuelSensitivityTable';
import NetworkImpactDisplay from '../NetworkImpactDisplay';

beforeEach(() => {
  vi.clearAllMocks();
});


// ═══════════════════════════════════════════════════════════════════════════════
// 1. ForwardSpreadCurve 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('ForwardSpreadCurve', () => {
  it('组件渲染不崩溃', () => {
    fetchJson.mockResolvedValue(null);
    const { container } = render(<ForwardSpreadCurve lang="zh" />);
    expect(container).toBeTruthy();
  });

  it('显示标题文本', async () => {
    fetchJson.mockResolvedValue({
      historical_available: true,
      historical: [{ year: 2020, spread: 100 }, { year: 2021, spread: 110 }],
      projection: [{ year: 2025, central_spread: 120, high_spread: 150, low_spread: 90 }],
    });

    render(<ForwardSpreadCurve lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('前瞻价差曲线')).toBeInTheDocument();
    });
  });

  it('加载状态显示', () => {
    fetchJson.mockReturnValue(new Promise(() => {})); // 永不 resolve
    render(<ForwardSpreadCurve lang="zh" />);
    expect(screen.getByText('加载前瞻价差数据...')).toBeInTheDocument();
  });

  it('API 数据加载后渲染图表区域', async () => {
    fetchJson.mockResolvedValue({
      historical_available: true,
      historical: [{ year: 2020, spread: 100 }],
      projection: [{ year: 2025, central_spread: 120, high_spread: 150, low_spread: 90 }],
    });

    render(<ForwardSpreadCurve lang="zh" />);
    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  it('错误状态显示重试按钮', async () => {
    fetchJson.mockRejectedValue(new Error('Network error'));
    render(<ForwardSpreadCurve lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('重试')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 2. RevenueStratificationChart 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('RevenueStratificationChart', () => {
  const mockData = {
    annual_layers: [
      {
        year: 2025,
        layer1: { amount: 50000, percentage: 50 },
        layer2: { amount: 30000, percentage: 30 },
        layer3: { amount: 20000, percentage: 20 },
        total_revenue: 100000,
      },
    ],
    layer_weighted_npv: 1200000,
    standard_npv: 1000000,
    npv_difference: 200000,
    discount_rates: { layer1: 0.06, layer2: 0.08, layer3: 0.12 },
  };

  it('组件渲染不崩溃', () => {
    fetchJson.mockResolvedValue(null);
    const { container } = render(<RevenueStratificationChart lang="zh" />);
    expect(container).toBeTruthy();
  });

  it('显示标题文本', async () => {
    fetchJson.mockResolvedValue(mockData);
    render(<RevenueStratificationChart lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('收入风险分层')).toBeInTheDocument();
    });
  });

  it('NPV 对比卡片渲染', async () => {
    fetchJson.mockResolvedValue(mockData);
    render(<RevenueStratificationChart lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('分层加权 NPV')).toBeInTheDocument();
      expect(screen.getByText('标准 NPV')).toBeInTheDocument();
      expect(screen.getByText('NPV 差异')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 3. EventAnnotationOverlay 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('EventAnnotationOverlay', () => {
  const mockAnnotations = [
    { event_type: 'coal_closure', event_name: 'Eraring', date: '2025-08-01', region: 'NSW1', capacity_mw: 2880, confidence: 'high', spread_impact_factor: 1.2 },
    { event_type: 'bess_commissioning', event_name: 'Waratah', date: '2026-03-01', region: 'NSW1', capacity_mw: 850, confidence: 'medium', spread_impact_factor: 0.8 },
    { event_type: 'network_augmentation', event_name: 'HumeLink', date: '2027-06-01', region: 'NSW1', capacity_mw: 2000, confidence: 'high', spread_impact_factor: 0.6 },
  ];

  it('组件渲染不崩溃', () => {
    const { container } = render(
      <EventAnnotationOverlay
        annotations={[]}
        chartWidth={800}
        chartHeight={400}
      />
    );
    expect(container).toBeTruthy();
  });

  it('传入 annotations 数据时渲染标记', () => {
    const { container } = render(
      <EventAnnotationOverlay
        annotations={mockAnnotations}
        chartWidth={800}
        chartHeight={400}
        xScale={(year) => (year - 2025) * 100}
      />
    );
    // 应该渲染 SVG 标记
    const svgElement = container.querySelector('svg');
    expect(svgElement).toBeTruthy();
    // 应该有 3 个事件标记（polygon 元素）
    const polygons = container.querySelectorAll('polygon');
    expect(polygons.length).toBe(3);
  });

  it('空 annotations 不渲染任何标记', () => {
    const { container } = render(
      <EventAnnotationOverlay
        annotations={[]}
        chartWidth={800}
        chartHeight={400}
      />
    );
    const polygons = container.querySelectorAll('polygon');
    expect(polygons.length).toBe(0);
  });

  it('图例显示三种事件类型', () => {
    render(
      <EventAnnotationOverlay
        annotations={mockAnnotations}
        chartWidth={800}
        chartHeight={400}
        xScale={(year) => (year - 2025) * 100}
        lang="en"
      />
    );
    expect(screen.getByText('Coal Closure')).toBeInTheDocument();
    expect(screen.getByText('BESS Commissioning')).toBeInTheDocument();
    expect(screen.getByText('Network Augmentation')).toBeInTheDocument();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 4. AssumptionPanel 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('AssumptionPanel', () => {
  it('组件渲染不崩溃', () => {
    const { container } = render(<AssumptionPanel lang="zh" />);
    expect(container).toBeTruthy();
  });

  it('显示所有 5 个类别', () => {
    render(<AssumptionPanel lang="zh" />);
    expect(screen.getByText('电池参数')).toBeInTheDocument();
    expect(screen.getByText('成本参数')).toBeInTheDocument();
    expect(screen.getByText('税务参数')).toBeInTheDocument();
    expect(screen.getByText('前瞻电价假设')).toBeInTheDocument();
    expect(screen.getByText('情景选择')).toBeInTheDocument();
  });

  it('重置按钮存在（修改值后显示）', () => {
    render(<AssumptionPanel lang="zh" />);
    // 修改一个值以触发重置按钮显示
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[0], { target: { value: '200' } });
    expect(screen.getByText('重置全部')).toBeInTheDocument();
  });

  it('修改值后显示修改标记', () => {
    const { container } = render(<AssumptionPanel lang="zh" />);
    const inputs = screen.getAllByRole('spinbutton');
    // 修改第一个输入框的值
    fireEvent.change(inputs[0], { target: { value: '200' } });
    // 应该显示修改标记（amber 圆点）
    const modifiedDots = container.querySelectorAll('.bg-amber-500');
    expect(modifiedDots.length).toBeGreaterThan(0);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 5. AssetConfigPanel 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('AssetConfigPanel', () => {
  beforeEach(() => {
    // Mock 加载配置 API
    fetchJson.mockResolvedValue({
      region: 'NSW1',
      power_mw: 100,
      duration_hours: 4,
      round_trip_efficiency: 0.85,
      mlf: 0.99,
      connection_point: '',
    });
  });

  it('组件渲染不崩溃', async () => {
    const { container } = render(<AssetConfigPanel lang="zh" />);
    await waitFor(() => {
      expect(container).toBeTruthy();
    });
  });

  it('显示所有 6 个配置字段', async () => {
    render(<AssetConfigPanel lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('区域')).toBeInTheDocument();
      expect(screen.getByText(/额定功率/)).toBeInTheDocument();
      expect(screen.getByText(/储能时长/)).toBeInTheDocument();
      expect(screen.getByText(/往返效率/)).toBeInTheDocument();
      expect(screen.getByText(/边际损耗因子/)).toBeInTheDocument();
      expect(screen.getByText('接入点标识')).toBeInTheDocument();
    });
  });

  it('资产标签显示正确格式', async () => {
    render(<AssetConfigPanel lang="en" />);
    await waitFor(() => {
      const labels = screen.getAllByText(/For YOUR 100MW\/4h BESS at NSW1/);
      expect(labels.length).toBeGreaterThanOrEqual(1);
      // 主标签应该在 Asset Label 区域
      expect(labels[0]).toBeInTheDocument();
    });
  });

  it('保存按钮存在', async () => {
    render(<AssetConfigPanel lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('保存配置')).toBeInTheDocument();
    });
  });

  it('无效值显示错误提示', async () => {
    render(<AssetConfigPanel lang="en" />);
    await waitFor(() => {
      expect(screen.getByText('Save Configuration')).toBeInTheDocument();
    });
    // 输入超出范围的值
    const powerInput = screen.getAllByRole('spinbutton')[0];
    fireEvent.change(powerInput, { target: { value: '99999' } });
    await waitFor(() => {
      expect(screen.getByText(/Valid range/)).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 6. CrossValidationTable 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('CrossValidationTable', () => {
  const mockCrossValidationData = {
    entries: [
      { data_point: 'Eraring Closure', source_name: 'AEMO ISP', source_date: '2024-06', reported_value: '2027', discrepancy_pct: 5.2, is_stale: false },
      { data_point: 'Bayswater Closure', source_name: 'Origin Energy', source_date: '2023-01', reported_value: '2033', discrepancy_pct: 15.3, is_stale: true },
      { data_point: 'Liddell Closure', source_name: 'AGL', source_date: '2023-04', reported_value: '2023', discrepancy_pct: 0, is_stale: false },
    ],
    last_updated: '2024-12-01',
  };

  it('组件渲染不崩溃', async () => {
    fetchJson.mockResolvedValue(mockCrossValidationData);
    const { container } = render(<CrossValidationTable lang="zh" />);
    await waitFor(() => {
      expect(container).toBeTruthy();
    });
  });

  it('显示类别切换标签', async () => {
    fetchJson.mockResolvedValue(mockCrossValidationData);
    render(<CrossValidationTable lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('煤电退役日期')).toBeInTheDocument();
      expect(screen.getByText('收入基准')).toBeInTheDocument();
      expect(screen.getByText('价格预测')).toBeInTheDocument();
    });
  });

  it('差异超过 10% 的行高亮', async () => {
    fetchJson.mockResolvedValue(mockCrossValidationData);
    const { container } = render(<CrossValidationTable lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('Bayswater Closure')).toBeInTheDocument();
    });
    // 差异 15.3% 的行应该有红色高亮背景
    const highDiscrepancyRow = screen.getByText('+15.3%').closest('tr');
    expect(highDiscrepancyRow.className).toContain('bg-red-50');
  });

  it('过期数据显示警告标志', async () => {
    fetchJson.mockResolvedValue(mockCrossValidationData);
    render(<CrossValidationTable lang="zh" />);
    await waitFor(() => {
      expect(screen.getByText('⚠️')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 7. NarrativeTooltip 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('NarrativeTooltip', () => {
  it('组件渲染不崩溃', () => {
    const { container } = render(
      <NarrativeTooltip module="forward_price" lang="zh">
        <span>$120/MWh</span>
      </NarrativeTooltip>
    );
    expect(container).toBeTruthy();
  });

  it('包裹子元素正确渲染', () => {
    render(
      <NarrativeTooltip module="forward_price" lang="zh">
        <span>$120/MWh</span>
      </NarrativeTooltip>
    );
    expect(screen.getByText('$120/MWh')).toBeInTheDocument();
  });

  it('hover 前不显示提示面板', () => {
    const { container } = render(
      <NarrativeTooltip module="forward_price" lang="zh">
        <span>$120/MWh</span>
      </NarrativeTooltip>
    );
    // 提示面板使用 absolute z-50 类名，hover 前不应存在
    const tooltipPanel = container.querySelector('.z-50');
    expect(tooltipPanel).toBeNull();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 8. FuelSensitivityTable 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('FuelSensitivityTable', () => {
  const mockFuelData = {
    sensitivity_coefficient: 3.5,
    base_revenue: 850000,
    scenario: 'central',
    scenarios: [
      { gas_price_change_pct: -20, gas_price: 8.0, peak_price_impact: -19.0, revenue_impact: -59500, revenue_change_pct: -7.0 },
      { gas_price_change_pct: -10, gas_price: 9.0, peak_price_impact: -9.5, revenue_impact: -29750, revenue_change_pct: -3.5 },
      { gas_price_change_pct: 0, gas_price: 10.0, peak_price_impact: 0, revenue_impact: 0, revenue_change_pct: 0 },
      { gas_price_change_pct: 10, gas_price: 11.0, peak_price_impact: 9.5, revenue_impact: 29750, revenue_change_pct: 3.5 },
      { gas_price_change_pct: 20, gas_price: 12.0, peak_price_impact: 19.0, revenue_impact: 59500, revenue_change_pct: 7.0 },
    ],
  };

  it('组件渲染不崩溃', async () => {
    fetchJson.mockResolvedValue(mockFuelData);
    const { container } = render(<FuelSensitivityTable lang="zh" region="NSW1" />);
    await waitFor(() => {
      expect(container).toBeTruthy();
    });
  });

  it('显示标题文本', async () => {
    fetchJson.mockResolvedValue(mockFuelData);
    render(<FuelSensitivityTable lang="zh" region="NSW1" />);
    await waitFor(() => {
      expect(screen.getByText('燃料成本敏感性分析')).toBeInTheDocument();
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// 9. NetworkImpactDisplay 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('NetworkImpactDisplay', () => {
  const mockNetworkData = {
    project_name: 'HumeLink',
    region: 'NSW1',
    reduction_pct: 12.5,
    spread_before: [
      { year: 2025, spread: 120 },
      { year: 2026, spread: 125 },
    ],
    spread_after: [
      { year: 2025, spread: 105 },
      { year: 2026, spread: 109 },
    ],
  };

  it('组件渲染不崩溃', async () => {
    fetchJson.mockResolvedValue(mockNetworkData);
    const { container } = render(<NetworkImpactDisplay lang="zh" region="NSW1" />);
    await waitFor(() => {
      expect(container).toBeTruthy();
    });
  });

  it('显示标题文本', async () => {
    fetchJson.mockResolvedValue(mockNetworkData);
    render(<NetworkImpactDisplay lang="zh" region="NSW1" />);
    await waitFor(() => {
      expect(screen.getByText('网络增强影响分析')).toBeInTheDocument();
    });
  });
});
