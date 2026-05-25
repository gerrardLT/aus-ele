# Implementation Plan: Investment Outlook Scenarios

## Overview

为 AEMO Intelligence 平台新增 4 个投资前景情景分析模块（Cannibalization Simulator、FCAS Collapse Forecaster、Regional Timing Scorer、Merchant Risk Quantifier）。实现包括：新增数据文件、4 个后端分析引擎、统一 API 路由、4 个前端组件、以及与现有平台的集成注册。

## Tasks

- [x] 1. 数据层：新增数据文件和模型定义
  - [x] 1.1 创建 coal_retirement_schedule.json 数据文件
    - 在 `data/coal_retirement_schedule.json` 创建煤电退役时间表数据文件
    - 包含 metadata（last_updated, source）和 retirements 数组
    - 每条记录包含 plant_name, region, capacity_mw, fuel_type, expected_closure_date, confidence, volatility_impact_estimate
    - 初始数据包含 Yallourn (VIC1, 1480MW, 2028), Eraring (NSW1, 2880MW, 2027), Bayswater (NSW1, 2640MW, 2030) 等已确认/已公布的退役计划
    - _Requirements: 3.3, 3.8_

  - [x] 1.2 创建 market_examples.json 数据文件
    - 在 `data/market_examples.json` 创建真实市场数据注释文件
    - 包含 metadata 和 examples 对象，按模块分类（cannibalization, fcas_collapse, regional_timing, merchant_risk）
    - cannibalization 示例：QLD 容量 3x 增长导致收入从 $280k 降至 $73k
    - fcas_collapse 示例：2020-2025 FCAS 收入轨迹（$384k→$11k）
    - regional_timing 示例：SA 煤电退役后收入溢价 40%
    - merchant_risk 示例：NSW 2022-2024 收入范围 $45k-$180k
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 1.3 创建 Pydantic 数据模型
    - 在 `backend/models/outlook_models.py` 定义所有数据模型
    - 实现 `CoalRetirement`, `CoalRetirementSchedule` 模型（含 get_retirements_before, total_retiring_capacity 方法）
    - 实现 `FcasServiceParams`, `FcasCollapseParams` 模型
    - 实现 `MerchantRiskRequest`, `MonteCarloConfig` 模型
    - 实现所有 API 响应模型：`DilutionPoint`, `YearlyProjection`, `MarketExample`, `CannibalizationResponse`, `FcasServiceResult`, `FcasCollapseResponse`, `RegionTimingScore`, `RegionalTimingResponse`, `RevenueDistribution`, `MerchantRiskResponse`
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.4_

  - [x] 1.4 编写数据模型属性测试
    - **Property 12: Market examples have valid structure**
    - **Validates: Requirements 6.5, 6.6**

- [x] 2. Checkpoint - 确保数据层测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 后端引擎：Cannibalization Simulator
  - [x] 3.1 实现 CannibalizationEngine
    - 创建 `backend/engines/cannibalization_engine.py`
    - 实现 `CannibalizationEngine` 类，接受 `CapacityDataLoader` 依赖
    - 实现 `simulate()` 方法：基于幂律模型 `revenue_per_mw = base_revenue / (capacity / base_capacity) ^ alpha` 计算稀释
    - 实现 `compute_dilution_curve()` 方法：生成 50 个数据点的稀释曲线
    - 从 capacity_data.json 加载管道数据（committed, construction, planning 状态）
    - 支持 1-5 年前瞻预测，基于预期投产日期
    - 超过 50% 稀释时设置 warning_triggered=True
    - 加载 market_examples.json 中对应区域的真实案例注释
    - 生成纯文本结论摘要
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x]* 3.2 编写 CannibalizationEngine 属性测试
    - **Property 1: Dilution curve follows power-law model**
    - **Validates: Requirements 1.1**

  - [x]* 3.3 编写年度预测属性测试
    - **Property 2: Yearly projections count matches parameter**
    - **Validates: Requirements 1.5**

  - [x]* 3.4 编写警告阈值属性测试
    - **Property 3: Warning threshold consistency**
    - **Validates: Requirements 1.6**

- [x] 4. 后端引擎：FCAS Collapse Forecaster
  - [x] 4.1 实现 FcasCollapseEngine
    - 创建 `backend/engines/fcas_collapse_engine.py`
    - 实现 `FcasCollapseEngine` 类，接受 `DatabaseManager` 依赖
    - 实现 `forecast()` 方法：计算 10 种 FCAS 服务的供需比和价格天花板
    - FCAS 注册容量数据来源：基于 capacity_data.json 中 BESS 总量 × 服务参与率估算（参与率默认值：raise6sec=0.8, raise60sec=0.7, raise5min=0.6, raisereg=0.5, lower 类似）
    - 市场需求量（Market Requirement Volume）使用 AEMO 公开的各服务最低采购量常量（raise6sec≈200MW, raise60sec≈300MW 等）
    - 实现 `compute_price_ceiling()` 方法：`price = max(0, base_price * (1 - (supply/demand - 1) ^ beta))`，supply/demand ≤ 1 时返回 base_price
    - 实现 `classify_service()` 方法：healthy (<1.5), at_risk (1.5-3.0), collapsed (>3.0)
    - 计算 total_fcas_ceiling_per_mw_year = sum(price_ceiling * enablement_probability * 8760)
    - 从 SQLite 加载历史 FCAS 价格数据，缺失时排除该服务
    - 加载 market_examples.json 中 FCAS 历史轨迹数据
    - 生成结论摘要（最大现实 FCAS 收入）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x]* 4.2 编写供需比计算属性测试
    - **Property 4: Supply-demand ratio calculation**
    - **Validates: Requirements 2.1**

  - [x]* 4.3 编写 FCAS 分类属性测试
    - **Property 5: FCAS service classification is deterministic**
    - **Validates: Requirements 2.2, 2.3**

  - [x]* 4.4 编写 FCAS 总收入天花板属性测试
    - **Property 6: Total FCAS ceiling equals weighted sum of parts**
    - **Validates: Requirements 2.6**

- [x] 5. 后端引擎：Regional Timing Scorer
  - [x] 5.1 实现 RegionalTimingEngine
    - 创建 `backend/engines/regional_timing_engine.py`
    - 实现 `RegionalTimingEngine` 类，接受 `DatabaseManager`, `CapacityDataLoader`, `CoalRetirementSchedule` 依赖
    - 实现 `score_regions()` 方法：计算 4 个维度评分（coal_retirement, pipeline_growth, renewable_penetration, revenue_trajectory），加权求和排序
    - renewable_penetration 维度使用负价频率作为代理指标（负价天数/总天数），从现有价格数据计算（负价越多 = 可再生渗透越高 = 波动性越大 = BESS 机会越多）
    - 实现 `estimate_coal_retirement_impact()` 方法：基于退役容量和 volatility_impact_estimate 计算 0-1 分
    - 实现 `project_pipeline_growth()` 方法：基于 capacity_data.json 预测 3 年管道增长率
    - 支持目标投资年份选择（当前年 ~ 当前年+5）
    - 煤电退役数据不可用时降级运行（仅计算其余 3 维度，标注 coal_data_available=False）
    - 加载 market_examples.json 中区域时机案例
    - 生成推荐区域和时机结论
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x]* 5.2 编写区域评分维度属性测试
    - **Property 7: Regional scores have all dimensions in valid range**
    - **Validates: Requirements 3.1**

  - [x]* 5.3 编写排名排序属性测试
    - **Property 8: Rankings are properly ordered**
    - **Validates: Requirements 3.2**

- [x] 6. 后端引擎：Merchant Risk Quantifier
  - [x] 6.1 实现 MerchantRiskEngine
    - 创建 `backend/engines/merchant_risk_engine.py`
    - 实现 `MerchantRiskEngine` 类，接受 `DatabaseManager` 依赖
    - 实现 `simulate()` 方法：使用简化日收入计算（每日 peak-trough spread × power_mw × interval_hours × efficiency），不调用 MILP 引擎
    - 从历史价格数据（trading_price_{year} 表）直接计算每日套利收入，随机抽取 365 天 × N 次模拟，加入 ±noise_std_pct 高斯噪声
    - 实现 `resample_daily_revenue()` 方法：随机抽取 365 天日收入 + 噪声扰动生成年度收入
    - 实现 `compute_contract_coverage()` 方法：计算满足银行融资门槛所需最低合约覆盖率
    - 计算 P10/P50/P90 分位数和直方图分箱数据
    - 支持 DSCR（默认 1.3x）和银行合约要求比例（默认 60-80%）可调
    - 历史数据不足 2 年时附带 data_warning
    - 加载 market_examples.json 中商户风险案例
    - 生成合约策略建议结论
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x]* 6.2 编写蒙特卡洛分位数属性测试
    - **Property 9: Monte Carlo percentiles are ordered**
    - **Validates: Requirements 4.1**

  - [x]* 6.3 编写合约覆盖率计算属性测试
    - **Property 10: Contract coverage calculation consistency**
    - **Validates: Requirements 4.4**

- [x] 7. Checkpoint - 确保所有后端引擎测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. API 路由：统一 Outlook 端点
  - [x] 8.1 实现 outlook_routes.py
    - 创建 `backend/routes/outlook_routes.py`，定义 `APIRouter(prefix="/api/v1/outlook")`
    - 实现 `GET /cannibalization` 端点：接受 market, region, alpha, base_revenue, projection_years 参数
    - 实现 `GET /fcas-collapse` 端点：接受 market, region, year, beta 参数
    - 实现 `GET /regional-timing` 端点：接受 market, target_year, weight_coal, weight_pipeline, weight_renewable, weight_revenue 参数
    - 实现 `POST /merchant-risk` 端点：接受 MerchantRiskRequest 请求体（含 market 字段）
    - 所有端点返回标准 metadata 对象（market, region, timezone, currency, methodology_version）
    - 错误时返回结构化错误响应（error_code, message, suggested_action），使用现有 MarketModuleError
    - 在 `backend/routes/__init__.py` 的 ROUTE_MODULES 列表中注册 `"routes.outlook_routes"`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x]* 8.2 编写 API 元数据属性测试
    - **Property 11: API responses contain standard metadata**
    - **Validates: Requirements 5.4**

  - [x]* 8.3 编写 API 集成测试
    - 使用 FastAPI TestClient 测试 4 个端点的正常响应和错误响应
    - 测试无效区域返回 400 + INVALID_REGION
    - 测试缺失数据返回降级响应
    - _Requirements: 5.5_

- [x] 9. Checkpoint - 确保 API 端点测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 前端组件：4 个 Outlook 模块
  - [x] 10.1 实现 CannibalizationSimulator 前端组件
    - 创建 `web/src/components/modules/CannibalizationSimulator.jsx`
    - 使用 fetchJson 调用 `/api/v1/nem/outlook/cannibalization` 端点
    - 使用 Recharts LineChart 渲染稀释曲线（容量 MW vs 收入/MW/年）
    - 标注真实市场数据点（来自 market_examples）
    - 显示年度预测时间线表格
    - 超过 50% 稀释时显示橙色警告指示器
    - 底部显示纯文本结论摘要
    - 支持中英双语，遵循现有模块 props 模式（config, lang, region, year, apiBase）
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.8, 6.1_

  - [x] 10.2 实现 FcasCollapseForecaster 前端组件
    - 创建 `web/src/components/modules/FcasCollapseForecaster.jsx`
    - 使用 fetchJson 调用 `/api/v1/nem/outlook/fcas-collapse` 端点
    - 渲染 10 种 FCAS 服务汇总表格（服务名、供需比、分类、价格天花板）
    - 颜色编码：healthy=绿色, at_risk=橙色, collapsed=红色
    - 使用 Recharts LineChart 渲染历史收入轨迹折线图（2020→最新年份）
    - 底部显示最大现实 FCAS 收入结论
    - 支持中英双语
    - _Requirements: 2.1, 2.4, 2.5, 2.6, 2.8, 6.2_

  - [x] 10.3 实现 RegionalTimingScorer 前端组件
    - 创建 `web/src/components/modules/RegionalTimingScorer.jsx`
    - 使用 fetchJson 调用 `/api/v1/nem/outlook/regional-timing` 端点
    - 渲染排名表格（区域、综合评分、各维度分数）
    - 使用 Recharts RadarChart 渲染各区域维度对比雷达图
    - 显示真实案例注释（SA 煤电退役后收入变化）
    - 支持目标投资年份选择器（当前年 ~ 当前年+5）
    - 底部显示推荐区域和时机结论
    - 支持中英双语
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 3.7, 6.3_

  - [x] 10.4 实现 MerchantRiskQuantifier 前端组件
    - 创建 `web/src/components/modules/MerchantRiskQuantifier.jsx`
    - 使用 fetchJson POST 调用 `/api/v1/nem/outlook/merchant-risk` 端点
    - 使用 Recharts BarChart 渲染收入分布直方图，标注 P10/P50/P90 竖线（ReferenceLine）
    - 渲染合约覆盖率计算面板（可调 DSCR 滑块和银行要求比例滑块）
    - 渲染历史实际收入范围对比条
    - 数据不足时显示统计代表性警告
    - 底部显示合约策略建议结论
    - 支持中英双语
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 6.4_

- [x] 11. Checkpoint - 确保前端组件可正常渲染
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. 集成：平台注册与连接
  - [x] 12.1 注册 MODULE_REGISTRY 和 NEM stages
    - 在 `web/src/lib/marketConfig.js` 的 MODULE_REGISTRY 中新增 4 个模块：
      - CannibalizationSimulator: { category: 'nem', description: 'Revenue cannibalization simulation' }
      - FcasCollapseForecaster: { category: 'nem', description: 'FCAS supply-demand collapse forecast' }
      - RegionalTimingScorer: { category: 'nem', description: 'Forward-looking regional timing score' }
      - MerchantRiskQuantifier: { category: 'nem', description: 'Monte Carlo merchant risk quantification' }
    - 在 NEM stages 数组中新增 `investment-outlook` 阶段（位于 `saturation-competition` 之后、`co-optimized-backtest` 之前）
    - 阶段配置包含 4 个模块及其 dataDependencies 和 loadPriority
    - _Requirements: 5.1, 5.3_

  - [x] 12.2 注册 ModuleRenderer lazy imports
    - 在 `web/src/components/funnel/ModuleRenderer.jsx` 的 MODULE_REGISTRY 中新增 4 个 lazy import：
      - CannibalizationSimulator: lazy(() => import('../modules/CannibalizationSimulator'))
      - FcasCollapseForecaster: lazy(() => import('../modules/FcasCollapseForecaster'))
      - RegionalTimingScorer: lazy(() => import('../modules/RegionalTimingScorer'))
      - MerchantRiskQuantifier: lazy(() => import('../modules/MerchantRiskQuantifier'))
    - _Requirements: 5.3_

  - [x] 12.3 注册后端路由
    - 在 `backend/routes/__init__.py` 的 ROUTE_MODULES 列表中添加 `"routes.outlook_routes"`
    - 确认路由注册后 4 个端点可正常访问
    - _Requirements: 5.2_

- [x] 13. Final Checkpoint - 确保所有测试通过，完整集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- 后端引擎（Tasks 3-6）是核心计算逻辑，建议优先实现并充分测试
- 前端组件（Task 10）可在 API 端点完成后并行开发
- 集成注册（Task 12）应在所有模块就绪后进行，确保无回归
- 现有 CapacityDataLoader 和 CoOptimizedBacktest 引擎可直接复用，无需重新实现

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "3.1", "4.1"] },
    { "id": 2, "tasks": ["3.2", "3.3", "3.4", "4.2", "4.3", "4.4", "5.1", "6.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "6.2", "6.3", "8.1"] },
    { "id": 4, "tasks": ["8.2", "8.3"] },
    { "id": 5, "tasks": ["10.1", "10.2", "10.3", "10.4"] },
    { "id": 6, "tasks": ["12.1", "12.2", "12.3"] }
  ]
}
```
