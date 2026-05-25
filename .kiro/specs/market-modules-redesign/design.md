# Design Document: Market Modules Redesign

## Overview

本设计文档定义 AEMO Intelligence 平台市场分析模块的全面重新设计架构。核心变更包括：将现有 4 阶段分析流程升级为 5-6 阶段的 2025 BESS 投资决策流程，新增 7 个专属分析模块，引入 LP/MILP 联合优化引擎替代现有单一套利回测，以及升级 marketConfig 架构以支持动态模块注册。

## Architecture

### 系统架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React 19)                       │
├─────────────────────────────────────────────────────────────────┤
│  MarketPage (编排器)                                             │
│    ├── ExecutiveSummary                                          │
│    ├── Stage 1: MarketScreeningStage                            │
│    ├── Stage 2: RevenueDeepDiveStage                            │
│    ├── Stage 3: SaturationCompetitionStage                      │
│    ├── Stage 4: CoOptimizedBacktestStage                        │
│    ├── Stage 5: FinancialModelingStage                          │
│    └── Stage 6: InvestmentDecisionStage                         │
├─────────────────────────────────────────────────────────────────┤
│  marketConfig.js (阶段/模块注册表)                                │
├─────────────────────────────────────────────────────────────────┤
│                        Backend (FastAPI)                          │
│    ├── routes/spike_routes.py                                    │
│    ├── routes/saturation_routes.py                               │
│    ├── routes/ranking_routes.py                                  │
│    ├── routes/coopt_routes.py                                    │
│    ├── routes/wem_modules_routes.py                              │
│    └── engines/co_optimization_engine.py                         │
├─────────────────────────────────────────────────────────────────┤
│  Data Layer                                                      │
│    ├── SQLite/PostgreSQL (价格数据)                               │
│    ├── capacity_data.json (容量数据源)                            │
│    └── PuLP MILP Solver (CBC)                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. 阶段结构重新设计

#### NEM 6 阶段结构

| 阶段 | ID | 核心问题 (zh) | 核心问题 (en) | 模块 |
|------|-----|--------------|---------------|------|
| 1 | `market-screening` | 哪个区域最值得深入分析？ | Which region deserves deeper analysis? | PriceChart, SummaryStats, RegionalRanking, GridForecast |
| 2 | `revenue-deep-dive` | 收入来源的结构和集中度如何？ | What's the revenue structure and concentration? | SpikeProfitAnalysis, PeakAnalysis, FcasAnalysis, ChargingWindow |
| 3 | `saturation-competition` | 市场饱和风险有多大？ | How significant is market saturation risk? | SaturationTracker |
| 4 | `co-optimized-backtest` | 联合优化后的真实收入是多少？ | What's the real revenue after co-optimization? | CoOptimizedBacktest |
| 5 | `financial-modeling` | 项目财务指标是否达标？ | Do financial metrics meet thresholds? | InvestmentAnalysis, CycleCost |
| 6 | `investment-decision` | 最终投资建议是什么？ | What's the final investment recommendation? | ReportPreview |

#### WEM 5 阶段结构

| 阶段 | ID | 核心问题 (zh) | 核心问题 (en) | 模块 |
|------|-----|--------------|---------------|------|
| 1 | `market-screening` | WEM 市场整体机会如何？ | What's the overall WEM market opportunity? | PriceChart, SummaryStats, StemBalancingSpread |
| 2 | `revenue-deep-dive` | 容量信用和能量市场收入潜力？ | Capacity credit and energy market revenue potential? | CapacityCreditsAnalysis, WemEssAnalysis, FiveMinSettlementImpact |
| 3 | `saturation-competition` | WEM 饱和风险和容量信用压力？ | WEM saturation risk and capacity credit pressure? | SaturationTracker |
| 4 | `co-optimized-backtest` | 联合优化后的 WEM 收入？ | WEM revenue after co-optimization? | CoOptimizedBacktest |
| 5 | `investment-decision` | WEM 投资是否可行？ | Is WEM investment viable? | InvestmentAnalysis |

#### 设计决策说明

- **ChargingWindow** 放入 NEM Stage 2（收入深潜）：充电窗口识别是收入结构分析的一部分
- **GridForecast** 放入 NEM Stage 1（市场筛选）：短期预测辅助区域选择
- **InvestmentAnalysis + CycleCost** 放入 Stage 5（财务建模）：NPV/IRR 和循环成本是财务指标
- **ReportPreview** 单独放入 Stage 6（投资决策）：最终报告输出
- **Co_Optimization_Engine** 作为平台默认回测方法，但保留旧 DispatchOptimizer 作为 energy-only 对比基准（不删除，降级为内部参考）

### 2. 新增模块组件

#### 2.1 SpikeProfitAnalysis (NEM)

**职责：** 分析极端价格事件（>$3000/MWh）对 BESS 年收入的贡献。

**数据依赖：** `/api/v1/nem/spike-profit`

**输入：** region, year, threshold (默认 3000)

**输出：** 事件统计、收入贡献百分比、月度/时段分布

#### 2.2 SaturationTracker (NEM + WEM)

**职责：** 追踪各区域已注册和管道中的 BESS 容量，评估饱和风险。

**数据依赖：** `/api/v1/saturation`

**输入：** market, region (可选)

**输出：** 容量数据、饱和度指标、收入稀释曲线

#### 2.3 RegionalRanking (NEM)

**职责：** 基于多维度指标对 NEM 五个区域进行投资吸引力排序。

**数据依赖：** `/api/v1/nem/regional-ranking`

**输入：** weights (各维度权重), year

**输出：** 排名结果、各维度得分、雷达图数据

#### 2.4 CoOptimizedBacktest (NEM + WEM)

**职责：** 使用 LP/MILP 联合优化能量套利和辅助服务调度。

**数据依赖：** `/api/v1/co-optimization/backtest`

**输入：** BessParams, region, year, optimization_config

**输出：** 分项收入明细、约束绑定报告、optimality_gap

#### 2.5 CapacityCreditsAnalysis (WEM)

**职责：** 分析 WEM 容量信用机制对 BESS 项目的收入贡献。

**数据依赖：** `/api/v1/wem/capacity-credits`

**输入：** power_mw, duration_hours

**输出：** 年度容量信用收入、资格系数、历史价格趋势

#### 2.6 StemBalancingSpread (WEM)

**职责：** 分析 STEM 与 Balancing 市场价差套利机会。

**数据依赖：** `/api/v1/wem/stem-balancing`

**输入：** date_range, bess_params

**输出：** 价差统计、时段分布、理论套利收入

#### 2.7 FiveMinSettlementImpact (WEM)

**职责：** 评估 5 分钟结算对储能收入的影响。

**数据依赖：** `/api/v1/wem/five-min-settlement`

**输入：** year, bess_params

**输出：** 波动性变化、收入变化百分比、对比视图数据

### 3. 更新后的 marketConfig 结构

```javascript
// web/src/lib/marketConfig.js

export const MARKET_CONFIGS = {
  NEM: {
    id: 'NEM',
    label: '国家电力市场 (NEM)',
    regions: ['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1'],
    settlementIntervalMinutes: 5,
    timezone: 'Australia/Sydney',
    timezoneLabel: 'AEST',
    currency: 'AUD',
    ancillaryServiceType: 'FCAS',
    ancillaryServices: [
      'raise1sec', 'raise6sec', 'raise60sec', 'raise5min', 'raisereg',
      'lower1sec', 'lower6sec', 'lower60sec', 'lower5min', 'lowerreg',
    ],
    defaultRegion: 'NSW1',
    path: '/',
    stages: [
      {
        id: 'market-screening',
        title: { zh: '市场筛选', en: 'Market Screening' },
        coreQuestion: { zh: '哪个区域最值得深入分析？', en: 'Which region deserves deeper analysis?' },
        modules: [
          {
            component: 'PriceChart',
            dataDependencies: ['/api/price-trend'],
            loadPriority: 1,
            enabled: true,
          },
          {
            component: 'SummaryStats',
            dataDependencies: ['/api/price-trend'],
            loadPriority: 1,
            enabled: true,
          },
          {
            component: 'RegionalRanking',
            dataDependencies: ['/api/v1/nem/regional-ranking'],
            loadPriority: 2,
            enabled: true,
          },
          {
            component: 'GridForecast',
            dataDependencies: ['/api/grid-forecast'],
            loadPriority: 3,
            enabled: true,
          },
        ],
      },
      {
        id: 'revenue-deep-dive',
        title: { zh: '收入深潜', en: 'Revenue Deep Dive' },
        coreQuestion: { zh: '收入来源的结构和集中度如何？', en: "What's the revenue structure and concentration?" },
        modules: [
          {
            component: 'SpikeProfitAnalysis',
            dataDependencies: ['/api/v1/nem/spike-profit'],
            loadPriority: 1,
            enabled: true,
          },
          {
            component: 'PeakAnalysis',
            dataDependencies: ['/api/peak-analysis'],
            loadPriority: 2,
            enabled: true,
          },
          {
            component: 'FcasAnalysis',
            dataDependencies: ['/api/fcas-analysis'],
            loadPriority: 2,
            enabled: true,
          },
          {
            component: 'ChargingWindow',
            dataDependencies: ['/api/peak-analysis'],
            loadPriority: 3,
            enabled: true,
          },
        ],
      },
      {
        id: 'saturation-competition',
        title: { zh: '饱和与竞争', en: 'Saturation & Competition' },
        coreQuestion: { zh: '市场饱和风险有多大？', en: 'How significant is market saturation risk?' },
        modules: [
          { component: 'SaturationTracker', dataDependencies: ['/api/v1/saturation'], loadPriority: 1, enabled: true },
        ],
      },
      {
        id: 'co-optimized-backtest',
        title: { zh: '联合优化回测', en: 'Co-Optimized Backtest' },
        coreQuestion: { zh: '联合优化后的真实收入是多少？', en: "What's the real revenue after co-optimization?" },
        modules: [
          { component: 'CoOptimizedBacktest', dataDependencies: ['/api/v1/co-optimization/backtest'], loadPriority: 1, enabled: true },
        ],
      },
      {
        id: 'financial-modeling',
        title: { zh: '财务建模', en: 'Financial Modeling' },
        coreQuestion: { zh: '项目财务指标是否达标？', en: 'Do financial metrics meet thresholds?' },
        modules: [
          { component: 'InvestmentAnalysis', dataDependencies: ['/api/investment-analysis'], loadPriority: 1, enabled: true },
          { component: 'CycleCost', dataDependencies: ['/api/price-trend'], loadPriority: 2, enabled: true },
        ],
      },
      {
        id: 'investment-decision',
        title: { zh: '投资决策', en: 'Investment Decision' },
        coreQuestion: { zh: '最终投资建议是什么？', en: "What's the final investment recommendation?" },
        modules: [
          { component: 'ReportPreview', dataDependencies: ['/api/reports'], loadPriority: 1, enabled: true },
        ],
      },
      // ... 后续阶段类似结构
    ],
  },
  // WEM 配置类似，使用 WEM 专属模块
};
```

### 模块条目接口

```typescript
interface ModuleEntry {
  component: string;           // 组件名称，对应 lazy import 的组件
  dataDependencies: string[];  // 所需的后端 API 端点列表
  loadPriority: number;        // 加载优先级 (1=最高, 数字越大越低)
  enabled: boolean;            // feature flag，false 时跳过渲染
  featureFlag?: string;        // 可选的外部 feature flag 名称
}

interface StageDefinition {
  id: string;                  // 阶段唯一标识 (kebab-case)
  title: { zh: string; en: string };
  coreQuestion: { zh: string; en: string };
  modules: ModuleEntry[];
}
```

### MarketPage 动态渲染接口

```jsx
// MarketPage 根据 config.stages 数组动态渲染
export default function MarketPage({ market }) {
  const config = getMarketConfig(market);

  return (
    <PageShell {...shellProps}>
      <ExecutiveSummary {...summaryProps} />
      {config.stages.map((stage, index) => (
        <DynamicStage
          key={stage.id}
          stageDefinition={stage}
          stageNumber={index + 1}
          config={config}
          lang={lang}
          onVisible={handleStageVisible}
        />
      ))}
    </PageShell>
  );
}
```

### DynamicStage 组件接口

```jsx
/**
 * DynamicStage — 通用阶段渲染器
 * 根据 stageDefinition.modules 动态加载并渲染模块组件。
 */
function DynamicStage({ stageDefinition, stageNumber, config, lang, onVisible }) {
  const enabledModules = stageDefinition.modules.filter(m => m.enabled);
  // 按 loadPriority 排序
  const sortedModules = [...enabledModules].sort((a, b) => a.loadPriority - b.loadPriority);

  return (
    <FunnelStage
      stageId={stageDefinition.id}
      stageNumber={stageNumber}
      title={stageDefinition.title[lang]}
      coreQuestion={stageDefinition.coreQuestion[lang]}
      onVisible={onVisible}
      lang={lang}
    >
      {sortedModules.map(moduleEntry => (
        <ModuleRenderer
          key={moduleEntry.component}
          moduleEntry={moduleEntry}
          config={config}
          lang={lang}
        />
      ))}
    </FunnelStage>
  );
}
```

### ModuleRenderer 组件接口

```jsx
/**
 * ModuleRenderer — 动态模块加载器
 * 使用 React.lazy + Suspense 按组件名称动态加载模块。
 * 如果组件不存在，捕获错误并跳过渲染，在控制台记录警告。
 */
import { lazy, Suspense } from 'react';

const MODULE_REGISTRY = {
  // 新增模块
  SpikeProfitAnalysis: lazy(() => import('../components/modules/SpikeProfitAnalysis')),
  SaturationTracker: lazy(() => import('../components/modules/SaturationTracker')),
  RegionalRanking: lazy(() => import('../components/modules/RegionalRanking')),
  CoOptimizedBacktest: lazy(() => import('../components/modules/CoOptimizedBacktest')),
  CapacityCreditsAnalysis: lazy(() => import('../components/modules/CapacityCreditsAnalysis')),
  StemBalancingSpread: lazy(() => import('../components/modules/StemBalancingSpread')),
  FiveMinSettlementImpact: lazy(() => import('../components/modules/FiveMinSettlementImpact')),
  // 现有模块（全部保留）
  PriceChart: lazy(() => import('../components/PriceChart')),
  SummaryStats: lazy(() => import('../components/SummaryStats')),
  PeakAnalysis: lazy(() => import('../components/PeakAnalysis')),
  FcasAnalysis: lazy(() => import('../components/FcasAnalysis')),
  ChargingWindow: lazy(() => import('../components/ChargingWindow')),
  GridForecast: lazy(() => import('../components/GridForecast')),
  InvestmentAnalysis: lazy(() => import('../components/InvestmentAnalysis')),
  CycleCost: lazy(() => import('../components/CycleCost')),
  ReportPreview: lazy(() => import('../components/ReportPreview')),
  WemEssAnalysis: lazy(() => import('../components/wem/WemEssAnalysis')),
};

function ModuleRenderer({ moduleEntry, config, lang }) {
  const Component = MODULE_REGISTRY[moduleEntry.component];

  if (!Component) {
    console.warn(`[MarketPage] Module component "${moduleEntry.component}" not found, skipping.`);
    return null;
  }

  return (
    <ErrorBoundary fallback={null} onError={(err) => {
      console.warn(`[MarketPage] Module "${moduleEntry.component}" failed to render:`, err);
    }}>
      <Suspense fallback={<ModuleLoadingSkeleton />}>
        <Component config={config} lang={lang} />
      </Suspense>
    </ErrorBoundary>
  );
}
```

## Data Models

### 容量数据源 Schema (Capacity_Data_Source)

```json
{
  "$schema": "capacity_data_v1",
  "metadata": {
    "last_updated": "2025-06-15T10:30:00+10:00",
    "source": "AEMO Generation Information Report Q2 2025",
    "version": 3
  },
  "projects": [
    {
      "region": "SA1",
      "project_name": "Hornsdale Power Reserve Expansion",
      "capacity_mw": 150,
      "duration_hours": 2,
      "energy_mwh": 300,
      "status": "registered",
      "expected_commissioning_date": "2024-03-01",
      "actual_commissioning_date": "2024-02-15",
      "owner": "Neoen",
      "technology": "Li-ion NMC"
    },
    {
      "region": "NSW1",
      "project_name": "Waratah Super Battery",
      "capacity_mw": 850,
      "duration_hours": 2,
      "energy_mwh": 1680,
      "status": "construction",
      "expected_commissioning_date": "2025-12-01",
      "actual_commissioning_date": null,
      "owner": "Akaysha Energy",
      "technology": "Li-ion LFP"
    }
  ]
}
```

#### 容量数据 Pydantic 模型

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date, datetime


class CapacityProject(BaseModel):
    region: str = Field(..., description="NEM region or 'WEM'")
    project_name: str
    capacity_mw: float = Field(gt=0)
    duration_hours: float = Field(gt=0)
    energy_mwh: Optional[float] = None
    status: Literal["registered", "construction", "planning", "committed"]
    expected_commissioning_date: Optional[date] = None
    actual_commissioning_date: Optional[date] = None
    owner: Optional[str] = None
    technology: Optional[str] = None

    def model_post_init(self, __context):
        if self.energy_mwh is None:
            self.energy_mwh = self.capacity_mw * self.duration_hours


class CapacityDataMetadata(BaseModel):
    last_updated: datetime
    source: str
    version: int = Field(ge=1)


class CapacityDataSource(BaseModel):
    metadata: CapacityDataMetadata
    projects: list[CapacityProject]

    def get_region_summary(self, region: str) -> dict:
        region_projects = [p for p in self.projects if p.region == region]
        registered = sum(p.capacity_mw for p in region_projects if p.status == "registered")
        pipeline = sum(p.capacity_mw for p in region_projects if p.status != "registered")
        return {
            "region": region,
            "registered_mw": registered,
            "pipeline_mw": pipeline,
            "total_mw": registered + pipeline,
            "project_count": len(region_projects),
        }
```

### 联合优化引擎数据模型

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class FcasService(str, Enum):
    RAISE_1SEC = "raise1sec"
    RAISE_6SEC = "raise6sec"
    RAISE_60SEC = "raise60sec"
    RAISE_5MIN = "raise5min"
    RAISE_REG = "raisereg"
    LOWER_1SEC = "lower1sec"
    LOWER_6SEC = "lower6sec"
    LOWER_60SEC = "lower60sec"
    LOWER_5MIN = "lower5min"
    LOWER_REG = "lowerreg"


class CoOptimizationParams(BaseModel):
    """联合优化请求参数"""
    market: Literal["NEM", "WEM"]
    region: str
    year: int
    month: Optional[int] = None  # None = 全年优化

    # BESS 参数
    power_mw: float = Field(default=100, gt=0)
    duration_hours: float = Field(default=4, gt=0)
    round_trip_efficiency: float = Field(default=0.87, gt=0, le=1)
    min_soc_pct: float = Field(default=5, ge=0, le=100)
    max_soc_pct: float = Field(default=95, ge=0, le=100)

    # FCAS 参数
    fcas_services: list[str] = Field(default_factory=lambda: ["raise6sec", "raise60sec", "raise5min"])
    fcas_max_capacity_pct: float = Field(default=0.5, ge=0, le=1, description="FCAS 最大预留比例")

    # 求解器参数
    time_limit_seconds: int = Field(default=60, ge=10, le=300)
    optimality_gap_tolerance: float = Field(default=0.01, ge=0, le=0.1)

    # 成本参数
    variable_om_per_mwh: float = Field(default=2.5, ge=0)
    network_fee_per_mwh: float = Field(default=0, ge=0)
    degradation_cost_per_mwh: float = Field(default=0, ge=0)


class CoOptimizationResult(BaseModel):
    """联合优化结果"""
    status: Literal["optimal", "feasible", "infeasible", "timeout"]
    optimality_gap: Optional[float] = None  # 仅当 status="feasible" 时有值

    # 收入分项
    energy_revenue: float
    fcas_revenue: float
    total_gross_revenue: float
    total_net_revenue: float

    # 对比基准
    energy_only_revenue: Optional[float] = None
    co_optimization_uplift: Optional[float] = None  # 联合优化增量收入

    # 详细时间线 (可选，大数据量时省略)
    timeline: Optional[list[dict]] = None

    # 约束绑定报告
    binding_constraints: list[dict] = Field(default_factory=list)

    # 月度分解
    monthly_breakdown: Optional[list[dict]] = None

    # 元数据
    solve_time_seconds: float = 0
    solver_status: str = ""
```

### API 响应模型

```python
class SpikeProfitResponse(BaseModel):
    """极端价格事件利润分析响应"""
    region: str
    year: int
    threshold: float

    # 事件统计
    spike_count: int
    total_spike_hours: float
    max_single_event_revenue: float

    # 收入贡献
    spike_revenue_total: float
    annual_arbitrage_revenue: float
    spike_revenue_pct: float  # spike_revenue_total / annual_arbitrage_revenue * 100

    # 分布数据
    monthly_distribution: list[dict]  # [{month: 1, count: 3, revenue: 12000}, ...]
    hourly_distribution: list[dict]   # [{hour: 14, count: 5, avg_price: 5200}, ...]
    duration_distribution: list[dict] # [{duration_min: 5, count: 10}, ...]

    # 年际趋势
    yearly_trend: list[dict]  # [{year: 2022, count: 15, revenue: 45000}, ...]


class SaturationResponse(BaseModel):
    """饱和度追踪响应"""
    market: str
    last_updated: str

    regions: list[dict]  # 各区域饱和度数据
    # 每个区域: {region, registered_mw, pipeline_mw, peak_load_mw,
    #            saturation_ratio, pipeline_ratio, dilution_estimate}

    timeline: list[dict]  # 容量增长时间线
    # [{date, region, cumulative_mw, project_name}, ...]


class RegionalRankingResponse(BaseModel):
    """区域排名响应"""
    rankings: list[dict]
    # [{rank, region, total_score, dimensions: {arbitrage: 0.8, spikes: 0.6, ...}}]

    weights_used: dict  # {arbitrage: 0.2, spikes: 0.2, fcas: 0.2, saturation: 0.2, constraints: 0.2}
    data_year: int
    methodology_notes: list[str]


class CapacityCreditsResponse(BaseModel):
    """WEM 容量信用分析响应"""
    power_mw: float
    duration_hours: float
    eligibility_coefficient: float
    credit_price_current: float  # $/MW/year
    annual_capacity_revenue: float
    energy_revenue_estimate: float
    capacity_revenue_share_pct: float

    historical_prices: list[dict]  # [{year, price_per_mw}, ...]


class StemBalancingResponse(BaseModel):
    """STEM/Balancing 价差分析响应"""
    date_range: dict  # {start, end}
    spread_stats: dict  # {mean, median, p10, p90, std}
    hourly_pattern: list[dict]  # [{hour, avg_spread, count}, ...]
    theoretical_revenue: float
    unconstrained_revenue: float
    constraint_impact_pct: float  # (unconstrained - theoretical) / unconstrained * 100


class FiveMinSettlementResponse(BaseModel):
    """5 分钟结算影响分析响应"""
    data_mode: Literal["simulated", "actual"]
    volatility_30min: float
    volatility_5min: float
    volatility_change_pct: float
    revenue_change_pct: float
    spread_distribution_comparison: dict
    spike_capture_rate_comparison: dict
```

### API 错误响应模型

```python
class ApiErrorResponse(BaseModel):
    """统一错误响应格式"""
    error_code: str  # e.g. "SPIKE_DATA_NOT_FOUND", "SOLVER_TIMEOUT"
    message: str     # 人类可读的错误描述
    suggested_action: str  # 建议的下一步操作
    details: Optional[dict] = None  # 可选的额外调试信息
```

## Backend API Schemas

### 新增 API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/nem/spike-profit` | GET | 极端价格事件利润分析 |
| `/api/v1/saturation` | GET | 饱和度追踪（NEM + WEM） |
| `/api/v1/nem/regional-ranking` | GET | NEM 区域排名 |
| `/api/v1/co-optimization/backtest` | POST | 联合优化回测 |
| `/api/v1/wem/capacity-credits` | GET | WEM 容量信用分析 |
| `/api/v1/wem/stem-balancing` | GET | WEM STEM/Balancing 价差 |
| `/api/v1/wem/five-min-settlement` | GET | WEM 5 分钟结算影响 |

### 端点详细定义

```python
# routes/spike_routes.py
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/v1/nem", tags=["NEM Modules"])

@router.get("/spike-profit")
async def get_spike_profit(
    region: str = Query(..., description="NEM region: NSW1, QLD1, VIC1, SA1, TAS1"),
    year: int = Query(..., description="Analysis year"),
    threshold: float = Query(default=3000, description="Price threshold $/MWh"),
) -> SpikeProfitResponse:
    """计算极端价格事件的利润贡献分析。"""
    ...


# routes/saturation_routes.py
router = APIRouter(prefix="/api/v1", tags=["Saturation"])

@router.get("/saturation")
async def get_saturation(
    market: str = Query(default="NEM", description="Market: NEM or WEM"),
    region: Optional[str] = Query(default=None, description="Specific region filter"),
) -> SaturationResponse:
    """获取 BESS 容量饱和度数据。"""
    ...


# routes/ranking_routes.py
router = APIRouter(prefix="/api/v1/nem", tags=["NEM Modules"])

@router.get("/regional-ranking")
async def get_regional_ranking(
    year: int = Query(...),
    weight_arbitrage: float = Query(default=0.2, ge=0, le=1),
    weight_spikes: float = Query(default=0.2, ge=0, le=1),
    weight_fcas: float = Query(default=0.2, ge=0, le=1),
    weight_saturation: float = Query(default=0.2, ge=0, le=1),
    weight_constraints: float = Query(default=0.2, ge=0, le=1),
) -> RegionalRankingResponse:
    """基于多维度权重计算 NEM 区域排名。"""
    ...


# routes/coopt_routes.py
router = APIRouter(prefix="/api/v1/co-optimization", tags=["Co-Optimization"])

@router.post("/backtest")
async def run_co_optimization(
    params: CoOptimizationParams,
) -> CoOptimizationResult:
    """执行联合优化回测。"""
    ...


# routes/wem_modules_routes.py
router = APIRouter(prefix="/api/v1/wem", tags=["WEM Modules"])

@router.get("/capacity-credits")
async def get_capacity_credits(
    power_mw: float = Query(default=100, gt=0),
    duration_hours: float = Query(default=4, gt=0),
) -> CapacityCreditsResponse:
    """计算 WEM 容量信用收入。"""
    ...

@router.get("/stem-balancing")
async def get_stem_balancing(
    start_date: str = Query(...),
    end_date: str = Query(...),
    power_mw: float = Query(default=100, gt=0),
    duration_hours: float = Query(default=4, gt=0),
) -> StemBalancingResponse:
    """分析 STEM/Balancing 价差套利机会。"""
    ...

@router.get("/five-min-settlement")
async def get_five_min_settlement(
    year: int = Query(...),
    power_mw: float = Query(default=100, gt=0),
    duration_hours: float = Query(default=4, gt=0),
) -> FiveMinSettlementResponse:
    """评估 5 分钟结算对储能收入的影响。"""
    ...
```

## Co-Optimization Engine Architecture

### 设计原则

联合优化引擎扩展现有 `DispatchOptimizer`（已使用 PuLP MILP），新增 FCAS 市场参与的联合决策变量和耦合约束。

### 数学模型

**决策变量（每个时间间隔 t）：**
- `charge[t]`: 充电功率 (MW), ≥ 0
- `discharge[t]`: 放电功率 (MW), ≥ 0
- `soc[t]`: 荷电状态 (MWh)
- `is_charging[t]`: 二进制，1=充电模式
- `fcas_raise[t][s]`: 各 FCAS Raise 服务预留容量 (MW)
- `fcas_lower[t][s]`: 各 FCAS Lower 服务预留容量 (MW)

**目标函数：**
```
maximize Σ_t [
  (discharge[t] - charge[t]) * Δt * energy_price[t]
  + Σ_s fcas_raise[t][s] * Δt * fcas_raise_price[t][s]
  + Σ_s fcas_lower[t][s] * Δt * fcas_lower_price[t][s]
  - costs
]
```

**约束条件：**

1. **充放电互斥：**
   ```
   charge[t] ≤ P_max * is_charging[t]
   discharge[t] ≤ P_max * (1 - is_charging[t])
   ```

2. **SOC 动态：**
   ```
   soc[t] = soc[t-1] + charge[t]*Δt*η - discharge[t]*Δt/η
   min_soc ≤ soc[t] ≤ max_soc
   ```

3. **FCAS 容量预留与能量调度耦合：**
   ```
   discharge[t] + Σ_s fcas_raise[t][s] ≤ P_max * (1 - is_charging[t])
   charge[t] + Σ_s fcas_lower[t][s] ≤ P_max * is_charging[t]
   ```

4. **FCAS 容量上限：**
   ```
   Σ_s fcas_raise[t][s] ≤ P_max * fcas_max_capacity_pct
   Σ_s fcas_lower[t][s] ≤ P_max * fcas_max_capacity_pct
   ```

5. **SOC 预留（确保 FCAS 可交付）：**
   ```
   soc[t] ≥ min_soc + Σ_s fcas_raise[t][s] * delivery_duration[s]
   soc[t] ≤ max_soc - Σ_s fcas_lower[t][s] * delivery_duration[s]
   ```

6. **终端 SOC 约束：**
   ```
   soc[T] = initial_soc
   ```

### 引擎实现架构

```python
# backend/engines/co_optimization_engine.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pulp
from models.financial_params import BatterySpecs


@dataclass
class CoOptConfig:
    """联合优化配置"""
    fcas_services: list[str]
    fcas_max_capacity_pct: float = 0.5
    time_limit_seconds: int = 60
    optimality_gap_tolerance: float = 0.01
    monthly_segmentation: bool = True


class CoOptimizationEngine:
    """
    LP/MILP 联合优化引擎。
    同时优化能量套利和 FCAS 市场参与。
    """

    def __init__(self, specs: BatterySpecs, config: CoOptConfig):
        self.specs = specs
        self.config = config

    def optimize(
        self,
        energy_prices: list[dict],
        fcas_prices: dict[str, list[float]],
    ) -> CoOptimizationResult:
        """
        执行联合优化。

        Args:
            energy_prices: [{timestamp, price, interval_hours}, ...]
            fcas_prices: {service_name: [price_per_interval, ...]}

        Returns:
            CoOptimizationResult with revenue breakdown.
        """
        if self.config.monthly_segmentation:
            return self._solve_monthly(energy_prices, fcas_prices)
        return self._solve_full(energy_prices, fcas_prices)

    def _solve_full(self, energy_prices, fcas_prices) -> CoOptimizationResult:
        """单次全量求解"""
        prob = pulp.LpProblem("BESS_CoOpt", pulp.LpMaximize)
        n = len(energy_prices)
        # ... 构建变量、约束、目标函数 ...
        solver = pulp.PULP_CBC_CMD(
            msg=False,
            timeLimit=self.config.time_limit_seconds,
            gapRel=self.config.optimality_gap_tolerance,
        )
        prob.solve(solver)
        # ... 提取结果 ...

    def _solve_monthly(self, energy_prices, fcas_prices) -> CoOptimizationResult:
        """按月分段求解，汇总年度结果"""
        monthly_results = []
        for month_data in self._segment_by_month(energy_prices, fcas_prices):
            result = self._solve_full(month_data["energy"], month_data["fcas"])
            monthly_results.append(result)
        return self._aggregate_monthly(monthly_results)

    def _segment_by_month(self, energy_prices, fcas_prices):
        """将年度数据按月分段"""
        ...

    def _aggregate_monthly(self, monthly_results) -> CoOptimizationResult:
        """汇总月度结果为年度结果"""
        ...
```

### 与现有引擎的关系

```
DispatchOptimizer (现有)          CoOptimizationEngine (新)
├── 仅能量套利                    ├── 能量套利 + FCAS 联合优化
├── 单一目标函数                  ├── 多收入源目标函数
├── 基础约束                      ├── 扩展约束 (FCAS 耦合)
└── 降级为 energy-only 对比基准   └── 替代为默认回测方法
```

`CoOptimizationEngine` 在内部调用 `DispatchOptimizer.run_hindsight_optimization` 作为 energy-only 基准，用于计算 `co_optimization_uplift`。旧引擎不删除，但不再作为用户面向的默认回测方法。

## Error Handling

### 前端错误处理策略

| 场景 | 处理方式 |
|------|---------|
| API 端点返回错误 | 显示结构化错误消息 + suggested_action |
| 模块组件不存在 | 跳过渲染，console.warn 记录 |
| 容量数据过期 | 显示数据时效性警告 |
| 联合优化超时 | 显示可行解 + optimality_gap 标注 |
| STEM/Balancing 数据缺失 | 显示数据不可用状态 |

### 后端错误处理策略

```python
# 统一错误处理中间件
from fastapi import Request
from fastapi.responses import JSONResponse

ERROR_CODES = {
    "DATA_NOT_FOUND": "请求的数据不存在",
    "SOLVER_TIMEOUT": "优化求解超时，返回当前最优可行解",
    "SOLVER_INFEASIBLE": "约束条件不可行，请调整参数",
    "CAPACITY_DATA_STALE": "容量数据已过期，请更新数据源",
    "CAPACITY_DATA_INVALID": "容量数据格式错误，已回退到上一有效版本",
    "REGION_NOT_FOUND": "指定区域不存在",
    "MARKET_DATA_UNAVAILABLE": "市场数据不可用",
}

async def market_module_error_handler(request: Request, exc: MarketModuleError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": ERROR_CODES.get(exc.error_code, str(exc)),
            "suggested_action": exc.suggested_action,
            "details": exc.details,
        },
    )
```

### 容量数据回退机制

```python
class CapacityDataLoader:
    """容量数据加载器，支持校验和回退"""

    def __init__(self, data_path: str, backup_path: str):
        self.data_path = data_path
        self.backup_path = backup_path

    def load(self) -> CapacityDataSource:
        try:
            data = self._read_and_validate(self.data_path)
            return data
        except (ValidationError, FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Capacity data invalid: {e}, falling back to backup")
            return self._read_and_validate(self.backup_path)

    def _read_and_validate(self, path: str) -> CapacityDataSource:
        with open(path) as f:
            raw = json.load(f)
        return CapacityDataSource.model_validate(raw)
```

## Integration with Existing Architecture

### MarketPage 迁移策略

现有 `MarketPage.jsx` 硬编码了 4 个 Stage 组件的导入和渲染。迁移为动态渲染：

1. **阶段一：** 将 `config.stages` 从对象格式改为数组格式（保持向后兼容）
2. **阶段二：** 引入 `DynamicStage` + `ModuleRenderer` 组件
3. **阶段三：** 将现有 Stage 组件拆分为独立模块组件
4. **阶段四：** 移除硬编码的 Stage 导入，完全由 config 驱动

### 路由注册

新增路由模块注册到 `routes/__init__.py`：

```python
ROUTE_MODULES = [
    # 现有模块...
    "routes.price_routes",
    "routes.revenue_routes",
    "routes.investment_routes",
    "routes.fcas_routes",
    "routes.data_quality_routes",
    "routes.finland_routes",
    "routes.admin_routes",
    "routes.external_api_routes",
    "routes.aggregation_routes",
    # 新增模块
    "routes.spike_routes",
    "routes.saturation_routes",
    "routes.ranking_routes",
    "routes.coopt_routes",
    "routes.wem_modules_routes",
]
```

### 数据流

```
用户交互 (筛选器)
    │
    ▼
FilterContext (region, year, bessParams)
    │
    ▼
DynamicStage → ModuleRenderer
    │
    ▼
各模块 Hook (useSpikeProfitData, useSaturationData, ...)
    │
    ▼
fetchJson(dataDependencies[0], params)
    │
    ▼
FastAPI 端点 → 引擎计算 → 响应
```

### STAGE_DEFINITIONS 迁移

现有 `STAGE_DEFINITIONS` 数组将被废弃，阶段定义内联到各市场的 `stages` 数组中。提供兼容层：

```javascript
// 兼容层：从新格式生成旧格式
export function getStageDefinitions(marketId) {
  const config = MARKET_CONFIGS[marketId];
  return config.stages.map((stage, index) => ({
    id: stage.id,
    number: index + 1,
    title: stage.title,
    coreQuestion: stage.coreQuestion,
  }));
}

// 废弃的全局 STAGE_DEFINITIONS，保留用于过渡期
export const STAGE_DEFINITIONS = getStageDefinitions('NEM');
```

## Testing Strategy

### 单元测试

- **容量数据校验：** 测试 `CapacityDataSource` 模型对有效/无效 JSON 的解析行为
- **饱和度计算：** 测试 `get_region_summary` 对已知数据集的计算结果
- **排名算法：** 测试特定权重配置下的排名输出
- **价差统计：** 测试 STEM/Balancing 价差计算的数学正确性
- **容量信用系数：** 测试不同 BESS 时长对应的资格系数

### 属性测试 (Property-Based Testing)

- **联合优化引擎：** 使用 Hypothesis 生成随机价格序列和 BESS 参数，验证约束满足和收入分解
- **Spike 检测：** 生成随机价格序列，验证检测逻辑的正确性
- **配置校验：** 生成随机 marketConfig 变体，验证结构完整性
- **排名一致性：** 生成随机权重和得分，验证排名与加权和的一致性

### 集成测试

- **API 端点：** 对每个新端点进行 1-2 个代表性请求的端到端测试
- **错误处理：** 验证各端点在异常输入下返回结构化错误响应
- **容量数据回退：** 验证损坏数据触发回退机制

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Stage config structural validity

*For any* market config (NEM or WEM), the `stages` array SHALL contain between 5 and 6 entries, each with a non-empty `id`, `title` (with both `zh` and `en` non-empty strings), and `coreQuestion` (with both `zh` and `en` non-empty strings).

**Validates: Requirements 1.1, 1.4, 1.5**

### Property 2: Dynamic stage rendering matches config

*For any* valid market config with N enabled stages, the MarketPage SHALL render exactly N stage components in the order defined by the config. *For any* module with `enabled: false`, that module SHALL NOT appear in the rendered output.

**Validates: Requirements 1.2, 1.3, 11.2, 11.3**

### Property 3: Spike detection correctness

*For any* price time series and threshold value T, all events identified by the Spike_Profit_Module SHALL have at least one interval with price ≥ T, and the reported spike_count SHALL equal the number of distinct contiguous intervals where price ≥ T.

**Validates: Requirements 2.1**

### Property 4: Spike revenue percentage invariant

*For any* price time series where annual_arbitrage_revenue > 0, the spike_revenue_pct SHALL equal (spike_revenue_total / annual_arbitrage_revenue) * 100, and 0 ≤ spike_revenue_pct ≤ 100.

**Validates: Requirements 2.2**

### Property 5: Capacity data validation round-trip

*For any* valid CapacityDataSource object, serializing to JSON and deserializing back SHALL produce an equivalent object with all required fields (region, project_name, capacity_mw, duration_hours, status) present and correctly typed.

**Validates: Requirements 4.1, 4.2**

### Property 6: Capacity data parsing correctness

*For any* valid capacity data JSON containing projects for a given region, the `get_region_summary(region)` function SHALL return `registered_mw` equal to the sum of `capacity_mw` for all projects with status "registered" in that region, and `pipeline_mw` equal to the sum for all other statuses.

**Validates: Requirements 3.1, 10.1**

### Property 7: Saturation ratio calculation

*For any* region with registered_capacity > 0 and peak_load > 0, the saturation_ratio SHALL equal registered_capacity / peak_load, and the pipeline_ratio SHALL equal pipeline_capacity / registered_capacity.

**Validates: Requirements 3.2, 10.2**

### Property 8: Revenue dilution monotonicity

*For any* two saturation levels s1 < s2 (with all other parameters equal), the estimated revenue at s1 SHALL be greater than or equal to the estimated revenue at s2 (monotonically non-increasing dilution curve).

**Validates: Requirements 3.4**

### Property 9: Regional ranking consistency

*For any* set of dimension scores for 5 regions and any valid weight configuration (all weights ≥ 0), the region ranked #1 SHALL have the highest weighted sum, and the ranking SHALL be a valid permutation of the 5 regions with no duplicates.

**Validates: Requirements 5.1, 5.3**

### Property 10: Co-optimization dominance

*For any* valid price series with both energy and FCAS prices, the co-optimized total revenue SHALL be greater than or equal to the energy-only optimized revenue (since energy-only is a feasible solution to the co-optimization problem).

**Validates: Requirements 6.1**

### Property 11: Co-optimization constraint satisfaction

*For any* optimal solution from the co-optimization engine, the following constraints SHALL hold at every interval t: (1) charge[t] * discharge[t] == 0 (mutual exclusion), (2) min_soc ≤ soc[t] ≤ max_soc, (3) discharge[t] + Σ fcas_raise[t] ≤ P_max, (4) charge[t] + Σ fcas_lower[t] ≤ P_max.

**Validates: Requirements 6.2**

### Property 12: Revenue decomposition additivity

*For any* co-optimization result with status "optimal" or "feasible", the total_gross_revenue SHALL equal energy_revenue + fcas_revenue (within floating-point tolerance of 1e-6).

**Validates: Requirements 6.3**

### Property 13: Capacity credit eligibility monotonicity

*For any* two BESS configurations where duration1 > duration2 (with equal power_mw), the eligibility_coefficient for duration1 SHALL be greater than or equal to the eligibility_coefficient for duration2.

**Validates: Requirements 7.3**

### Property 14: Spread statistics correctness

*For any* STEM price series and Balancing price series of equal length, the mean spread SHALL equal mean(STEM) - mean(Balancing), and the spread at each interval SHALL equal STEM[t] - Balancing[t].

**Validates: Requirements 8.1**

### Property 15: Physical constraint revenue bound

*For any* price series and BESS physical constraints, the theoretical_revenue (constrained) SHALL be less than or equal to the unconstrained_revenue, and constraint_impact_pct SHALL equal (unconstrained - theoretical) / unconstrained * 100.

**Validates: Requirements 8.4**

### Property 16: 5-minute volatility amplification

*For any* 30-minute price series, the simulated 5-minute volatility SHALL be greater than or equal to the original 30-minute volatility (shorter settlement intervals amplify price volatility).

**Validates: Requirements 9.1**

### Property 17: API error response structure

*For any* API error response from any new endpoint, the response body SHALL contain non-empty `error_code`, `message`, and `suggested_action` string fields.

**Validates: Requirements 12.6**

### Property 18: Module config structural completeness

*For any* module entry in any stage of any market config, the entry SHALL contain a non-empty `component` string, a non-empty `dataDependencies` array of valid API path strings, a numeric `loadPriority` ≥ 1, and a boolean `enabled` field.

**Validates: Requirements 11.1, 11.4**
