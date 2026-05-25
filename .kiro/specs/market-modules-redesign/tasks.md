# Implementation Plan: Market Modules Redesign

## Overview

将 AEMO Intelligence 平台从现有 4 阶段硬编码分析流程升级为 5-6 阶段动态模块化架构。包括：升级 marketConfig 为数组格式支持动态注册、新增容量数据源、实现 7 个新分析模块的后端 API 和前端组件、引入 LP/MILP 联合优化引擎、以及将 MarketPage 迁移为配置驱动的动态渲染。

## Tasks

- [ ] 1. 基础设施：marketConfig 升级与动态渲染框架
  - [x] 1.1 升级 marketConfig.js 为数组格式阶段定义
    - 将 `web/src/lib/marketConfig.js` 中 NEM 和 WEM 的 `stages` 从对象格式改为数组格式
    - 每个阶段条目包含 `id`, `title` (zh/en), `coreQuestion` (zh/en), `modules` 数组
    - 每个模块条目包含 `component`, `dataDependencies`, `loadPriority`, `enabled` 字段
    - 保留 `getStageDefinitions()` 兼容函数生成旧格式 `STAGE_DEFINITIONS`
    - NEM 定义 6 个阶段及模块分配：
      - market-screening: PriceChart, SummaryStats, RegionalRanking, GridForecast
      - revenue-deep-dive: SpikeProfitAnalysis, PeakAnalysis, FcasAnalysis, ChargingWindow
      - saturation-competition: SaturationTracker
      - co-optimized-backtest: CoOptimizedBacktest
      - financial-modeling: InvestmentAnalysis, CycleCost
      - investment-decision: ReportPreview
    - WEM 定义 5 个阶段及模块分配：
      - market-screening: PriceChart, SummaryStats, StemBalancingSpread
      - revenue-deep-dive: CapacityCreditsAnalysis, WemEssAnalysis, FiveMinSettlementImpact
      - saturation-competition: SaturationTracker
      - co-optimized-backtest: CoOptimizedBacktest
      - investment-decision: InvestmentAnalysis
    - 在 MODULE_REGISTRY 中注册所有模块（含现有的 ChargingWindow, GridForecast, PeakAnalysis, FcasAnalysis, CycleCost, ReportPreview）
    - _Requirements: 1.1, 1.4, 1.5, 11.1, 11.2, 11.4_

  - [x] 1.2 创建 DynamicStage 组件
    - 在 `web/src/components/funnel/DynamicStage.jsx` 创建通用阶段渲染器
    - 接收 `stageDefinition`, `stageNumber`, `config`, `lang`, `onVisible` props
    - 过滤 `enabled: true` 的模块，按 `loadPriority` 排序
    - 内部使用现有 `FunnelStage` 组件渲染阶段外壳
    - 遍历模块列表调用 `ModuleRenderer` 渲染各模块
    - _Requirements: 1.2, 1.3, 11.3_

  - [x] 1.3 创建 ModuleRenderer 组件
    - 在 `web/src/components/funnel/ModuleRenderer.jsx` 创建动态模块加载器
    - 定义 `MODULE_REGISTRY` 对象，使用 `React.lazy` 映射组件名称到动态导入
    - 使用 `ErrorBoundary` + `Suspense` 包裹，加载失败时跳过渲染并 console.warn
    - 创建 `ModuleLoadingSkeleton` 加载占位组件
    - 注册所有现有模块和 7 个新模块的 lazy import 路径
    - _Requirements: 11.3, 11.5_

  - [x] 1.4 创建容量数据源文件和 Pydantic 模型
    - 在 `data/capacity_data.json` 创建初始容量数据 JSON 文件（含 metadata 和 projects 数组）
    - 在 `data/capacity_data_backup.json` 创建备份文件
    - 在 `backend/models/capacity_models.py` 实现 `CapacityProject`, `CapacityDataMetadata`, `CapacityDataSource` Pydantic 模型
    - 实现 `CapacityDataLoader` 类，支持校验和回退机制
    - 实现 `get_region_summary()` 方法计算区域容量汇总
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x]* 1.5 编写容量数据模型属性测试
    - **Property 5: Capacity data validation round-trip**
    - **Property 6: Capacity data parsing correctness**
    - **Validates: Requirements 4.1, 4.2, 3.1, 10.1**

  - [x]* 1.6 编写 marketConfig 结构属性测试
    - **Property 1: Stage config structural validity**
    - **Property 18: Module config structural completeness**
    - **Validates: Requirements 1.1, 1.4, 1.5, 11.1, 11.4**

- [ ] 2. Checkpoint - 确保基础设施测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. 后端 API：NEM 模块端点
  - [x] 3.1 实现 Spike Profit API 端点
    - 创建 `backend/routes/spike_routes.py`，定义 `APIRouter(prefix="/api/v1/nem")`
    - 实现 `GET /spike-profit` 端点，接受 region, year, threshold 参数
    - 实现 spike 检测逻辑：从数据库查询价格数据，识别 ≥ threshold 的连续区间
    - 计算事件统计、收入贡献百分比、月度/时段/持续时长分布
    - 计算年际趋势（至少 3 年对比）
    - 返回 `SpikeProfitResponse` 结构化响应
    - 无事件时返回空结果 + 历史频率参考
    - 在 `backend/routes/__init__.py` 注册路由
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 12.1_

  - [x]* 3.2 编写 Spike 检测属性测试
    - **Property 3: Spike detection correctness**
    - **Property 4: Spike revenue percentage invariant**
    - **Validates: Requirements 2.1, 2.2**

  - [x] 3.3 实现 Saturation API 端点
    - 创建 `backend/routes/saturation_routes.py`，定义 `APIRouter(prefix="/api/v1")`
    - 实现 `GET /saturation` 端点，接受 market, region 参数
    - 使用 `CapacityDataLoader` 加载容量数据
    - 计算各区域饱和度指标：registered/peak_load 比率、pipeline/registered 比率
    - 实现收入稀释估算模型
    - 生成容量增长时间线数据
    - 返回 `SaturationResponse` 结构化响应
    - 在 `backend/routes/__init__.py` 注册路由
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.1, 10.2, 12.2_

  - [x]* 3.4 编写饱和度计算属性测试
    - **Property 7: Saturation ratio calculation**
    - **Property 8: Revenue dilution monotonicity**
    - **Validates: Requirements 3.2, 3.4, 10.2**

  - [x] 3.5 实现 Regional Ranking API 端点
    - 创建 `backend/routes/ranking_routes.py`，定义 `APIRouter(prefix="/api/v1/nem")`
    - 实现 `GET /regional-ranking` 端点，接受 year 和 5 个维度权重参数
    - 实现多维度评分逻辑：套利收入、极端事件频率、FCAS 收入、饱和度风险、网络约束
    - 计算加权总分并排序
    - 返回 `RegionalRankingResponse` 含排名、各维度得分、雷达图数据
    - 在 `backend/routes/__init__.py` 注册路由
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 12.3_

  - [x]* 3.6 编写区域排名属性测试
    - **Property 9: Regional ranking consistency**
    - **Validates: Requirements 5.1, 5.3**

- [ ] 4. 后端 API：联合优化引擎
  - [x] 4.1 实现 Co-Optimization Engine 核心
    - 创建 `backend/engines/co_optimization_engine.py`
    - 实现 `CoOptConfig` 数据类和 `CoOptimizationEngine` 类
    - 实现 `_solve_full()` 方法：构建 PuLP MILP 模型，定义决策变量（charge, discharge, soc, is_charging, fcas_raise, fcas_lower）
    - 实现目标函数：最大化能量收入 + FCAS 收入 - 成本
    - 实现约束条件：充放电互斥、SOC 动态、FCAS 耦合、容量上限、SOC 预留、终端 SOC
    - 实现 `_solve_monthly()` 按月分段求解和 `_aggregate_monthly()` 汇总
    - 实现超时处理：60 秒内未找到最优解时返回可行解 + optimality_gap
    - 调用现有 `DispatchOptimizer` 作为 energy-only 基准计算 uplift
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6_

  - [x] 4.2 实现 Co-Optimization API 端点
    - 创建 `backend/routes/coopt_routes.py`，定义 `APIRouter(prefix="/api/v1/co-optimization")`
    - 在 `backend/models/` 中定义 `CoOptimizationParams` 和 `CoOptimizationResult` Pydantic 模型
    - 实现 `POST /backtest` 端点，接受 `CoOptimizationParams` 请求体
    - 加载能量价格和 FCAS 价格数据，调用 `CoOptimizationEngine.optimize()`
    - 返回 `CoOptimizationResult` 含分项收入、约束绑定报告、月度分解
    - 在 `backend/routes/__init__.py` 注册路由
    - _Requirements: 6.1, 6.3, 12.4_

  - [x]* 4.3 编写联合优化引擎属性测试
    - **Property 10: Co-optimization dominance**
    - **Property 11: Co-optimization constraint satisfaction**
    - **Property 12: Revenue decomposition additivity**
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [ ] 5. 后端 API：WEM 模块端点
  - [x] 5.1 实现 WEM Capacity Credits API 端点
    - 创建 `backend/routes/wem_modules_routes.py`，定义 `APIRouter(prefix="/api/v1/wem")`
    - 实现 `GET /capacity-credits` 端点，接受 power_mw, duration_hours 参数
    - 实现容量信用资格系数计算（基于 BESS 时长）
    - 计算年度容量信用收入和能量市场收入对比
    - 加载历史容量信用价格数据
    - 返回 `CapacityCreditsResponse` 结构化响应
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 12.5_

  - [x]* 5.2 编写容量信用资格系数属性测试
    - **Property 13: Capacity credit eligibility monotonicity**
    - **Validates: Requirements 7.3**

  - [x] 5.3 实现 WEM STEM/Balancing API 端点
    - 在 `backend/routes/wem_modules_routes.py` 中添加 `GET /stem-balancing` 端点
    - 接受 start_date, end_date, power_mw, duration_hours 参数
    - 计算 STEM 与 Balancing 价差统计（均值、中位数、百分位）
    - 计算时段分布模式和理论套利收入（考虑 BESS 物理约束）
    - 处理数据缺失情况，返回结构化错误
    - 返回 `StemBalancingResponse` 结构化响应
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 12.5_

  - [x]* 5.4 编写价差统计属性测试
    - **Property 14: Spread statistics correctness**
    - **Property 15: Physical constraint revenue bound**
    - **Validates: Requirements 8.1, 8.4**

  - [x] 5.5 实现 WEM Five-Min Settlement API 端点
    - 在 `backend/routes/wem_modules_routes.py` 中添加 `GET /five-min-settlement` 端点
    - 接受 year, power_mw, duration_hours 参数
    - 实现 30 分钟数据到 5 分钟的波动性模拟逻辑
    - 计算收入变化百分比、价差分布对比、极端事件捕获率对比
    - 支持实际数据可用时自动切换数据模式
    - 返回 `FiveMinSettlementResponse` 结构化响应
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 12.5_

  - [x]* 5.6 编写 5 分钟波动性属性测试
    - **Property 16: 5-minute volatility amplification**
    - **Validates: Requirements 9.1**

- [ ] 6. Checkpoint - 确保所有后端 API 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. 前端模块：NEM 专属组件
  - [x] 7.1 实现 SpikeProfitAnalysis 前端组件
    - 创建 `web/src/components/modules/SpikeProfitAnalysis.jsx`
    - 实现数据获取 hook `useSpikeProfitData(region, year, threshold)`
    - 渲染事件统计卡片、收入贡献百分比、月度分布图、时段分布图、持续时长分布图
    - 渲染年际趋势对比图（至少 3 年）
    - 无事件时显示提示信息 + 历史频率参考
    - 支持中英双语
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 7.2 实现 SaturationTracker 前端组件
    - 创建 `web/src/components/modules/SaturationTracker.jsx`
    - 实现数据获取 hook `useSaturationData(market, region)`
    - 渲染各区域容量数据表格（已注册 MW、管道 MW）
    - 渲染饱和度指标可视化和收入稀释曲线图
    - 渲染容量增长时间线（标注关键项目投运日期）
    - 显示数据更新时间提示
    - 支持 NEM 和 WEM 两种市场模式
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.5, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 7.3 实现 RegionalRanking 前端组件
    - 创建 `web/src/components/modules/RegionalRanking.jsx`
    - 实现数据获取 hook `useRegionalRankingData(year, weights)`
    - 渲染排名表格（含各维度得分）和雷达图
    - 实现权重调整滑块，调整后实时重新请求排名
    - 标注数据来源年份和计算方法说明
    - 支持中英双语
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 7.4 实现 CoOptimizedBacktest 前端组件
    - 创建 `web/src/components/modules/CoOptimizedBacktest.jsx`
    - 实现数据获取 hook `useCoOptimizationData(params)`
    - 渲染分项收入明细（能量 vs FCAS）、联合优化增量收入
    - 渲染约束绑定报告和 optimality_gap 标注
    - 渲染月度收入分解图
    - 超时时显示可行解 + gap 警告
    - 支持中英双语
    - _Requirements: 6.1, 6.3, 6.5_

- [ ] 8. 前端模块：WEM 专属组件
  - [x] 8.1 实现 CapacityCreditsAnalysis 前端组件
    - 创建 `web/src/components/modules/CapacityCreditsAnalysis.jsx`
    - 实现数据获取 hook `useCapacityCreditsData(power_mw, duration_hours)`
    - 渲染年度容量信用收入、资格系数、历史价格趋势图
    - 渲染容量信用 vs 能量市场收入对比饼图
    - BESS 参数变更时自动重新计算
    - 支持中英双语
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 8.2 实现 StemBalancingSpread 前端组件
    - 创建 `web/src/components/modules/StemBalancingSpread.jsx`
    - 实现数据获取 hook `useStemBalancingData(dateRange, bessParams)`
    - 渲染价差统计卡片、时段分布热力图、累计套利收入趋势
    - 数据不可用时显示结构化错误状态
    - 支持中英双语
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 8.3 实现 FiveMinSettlementImpact 前端组件
    - 创建 `web/src/components/modules/FiveMinSettlementImpact.jsx`
    - 实现数据获取 hook `useFiveMinSettlementData(year, bessParams)`
    - 渲染波动性变化指标、收入变化百分比、30min vs 5min 并排对比视图
    - 标注数据模式（simulated/actual）
    - 支持中英双语
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 9. Checkpoint - 确保前端组件可正常渲染
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. 集成：MarketPage 迁移为动态渲染
  - [x] 10.1 迁移 MarketPage 为配置驱动动态渲染
    - 修改 `web/src/pages/MarketPage.jsx`，移除硬编码的 Stage 组件导入
    - 使用 `getMarketConfig(market).stages` 数组驱动渲染
    - 使用 `DynamicStage` 组件替代现有硬编码的阶段渲染
    - 保留 `ExecutiveSummary` 组件在顶部
    - 确保 `FilterContext` (region, year, bessParams) 正确传递到各模块
    - 验证 NEM 6 阶段和 WEM 5 阶段均正确渲染
    - _Requirements: 1.2, 1.3, 11.3_

  - [x] 10.2 更新路由注册和错误处理中间件
    - 更新 `backend/routes/__init__.py`，注册所有新路由模块
    - 实现 `MarketModuleError` 异常类和统一错误处理中间件
    - 确保所有新端点在异常输入下返回结构化错误响应（error_code, message, suggested_action）
    - _Requirements: 12.6_

  - [x]* 10.3 编写 API 错误响应结构属性测试
    - **Property 17: API error response structure**
    - **Validates: Requirements 12.6**

  - [x]* 10.4 编写动态渲染属性测试
    - **Property 2: Dynamic stage rendering matches config**
    - **Validates: Requirements 1.2, 1.3, 11.2, 11.3**

- [ ] 11. Final Checkpoint - 确保所有测试通过，完整集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- 联合优化引擎（Task 4.1）是最复杂的单一任务，建议优先实现并充分测试
- 前端模块（Tasks 7-8）可在后端 API 完成后并行开发
- MarketPage 迁移（Task 10.1）应在所有模块就绪后进行，确保无回归

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.4"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.5", "1.6"] },
    { "id": 2, "tasks": ["3.1", "3.3", "3.5", "4.1", "5.1", "5.3", "5.5"] },
    { "id": 3, "tasks": ["3.2", "3.4", "3.6", "4.2", "5.2", "5.4", "5.6"] },
    { "id": 4, "tasks": ["4.3", "7.1", "7.2", "7.3", "7.4", "8.1", "8.2", "8.3"] },
    { "id": 5, "tasks": ["10.1", "10.2"] },
    { "id": 6, "tasks": ["10.3", "10.4"] }
  ]
}
```
