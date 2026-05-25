# Implementation Plan: Investment Narrative Layer

## Overview

将平台从纯数据展示工具转型为结构化投资故事生成器。实现 4 个新后端引擎/服务、ForwardPriceEngine 扩展、1 个新模型文件、1 个新路由文件和 7 个前端组件。按 Models → Engines → Routes → Frontend 分阶段推进，各阶段间设置检查点。

## Tasks

- [x] 1. 数据模型层（Pydantic Models）
  - [x] 1.1 创建 `backend/models/narrative_models.py` 定义所有叙事层数据模型
    - 实现 DriverType 枚举、CausalFactor、CausalAttribution 模型
    - 实现 ConfidenceLevel 枚举、LayerDiscountRates、RevenueLayer、AnnualStratifiedRevenue、StratifiedRevenue、LayerWeightedNPV 模型
    - 实现 EventAnnotation、EventCluster、EventAnnotationResponse 模型
    - 实现 CrossValidationEntry、CrossValidationResponse 模型
    - 实现 GasPriceAssumptions、FuelSensitivityScenario、FuelSensitivityResult 模型
    - 实现 AssetConfiguration 模型（含 capacity_mwh 和 label 属性）
    - 实现 ForwardSpreadCurveResponse、NetworkAugmentationEvent、NetworkImpactComparison 模型
    - 所有模型使用 Pydantic BaseModel + Field 验证约束
    - _Requirements: 15.1, 15.2, 16.1, 16.2, 8.4, 17.1-17.5_

  - [x] 1.2 扩展 `backend/engines/forward_price_engine.py` 中的 EventType 枚举，新增 NETWORK_AUGMENTATION
    - 在现有 EventType 枚举中添加 `NETWORK_AUGMENTATION = "network_augmentation"`
    - 确保不破坏现有事件类型引用
    - _Requirements: 14.1, 14.5_

  - [x]* 1.3 编写 Property 1 属性测试：CausalAttribution 序列化往返
    - **Property 1: CausalAttribution serialization round-trip**
    - 使用 Hypothesis 生成随机 CausalAttribution 对象，验证 JSON 序列化/反序列化往返一致性
    - **Validates: Requirements 15.1, 15.2, 15.3**

  - [x]* 1.4 编写 Property 2 属性测试：StratifiedRevenue 序列化往返
    - **Property 2: StratifiedRevenue serialization round-trip**
    - 使用 Hypothesis 生成随机 StratifiedRevenue 对象（含 20 年 annual_layers），验证 JSON 往返一致性
    - **Validates: Requirements 16.1, 16.2, 16.3**

  - [x]* 1.5 编写 Property 9 属性测试：无效输入拒绝
    - **Property 9: Invalid inputs are rejected with validation errors**
    - 使用 Hypothesis 生成超出范围的参数值（spread_threshold、discount_rate、power_mw、pass_through_coefficient、convergence_factor），验证 Pydantic 模型抛出 ValidationError
    - **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5**

  - [x]* 1.6 编写 Property 10 属性测试：资产标签包含必要信息
    - **Property 10: Asset label contains all identifying parameters**
    - 使用 Hypothesis 生成随机有效 AssetConfiguration，验证 label 属性包含 power_mw、duration_hours 和 region
    - **Validates: Requirements 8.3, 8.4**

- [x] 2. 检查点 - 模型层验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 后端引擎：RiskStratificationEngine
  - [x] 3.1 创建 `backend/engines/risk_stratification_engine.py` 实现风险分层引擎
    - 实现 `__init__` 接受 spread_threshold 和 layer_discount_rates 参数
    - 实现 `stratify_historical_revenue` 方法：基于历史价格数据按阈值拆分三层收入
    - 实现 `stratify_forward_revenue` 方法：基于前瞻预测估算 20 年分层收入
    - 实现 `calculate_layer_weighted_npv` 方法：各层独立折现后求和
    - Layer 1: 价格 < threshold 的区间收入（HIGH 置信度，8% 折现）
    - Layer 2: FCAS 辅助服务收入（MEDIUM 置信度，10% 折现）
    - Layer 3: 价格 > threshold 的区间收入（LOW 置信度，12% 折现）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x]* 3.2 编写 Property 3 属性测试：收入层级分区完备性
    - **Property 3: Revenue layer partitioning is exhaustive and exclusive**
    - 使用 Hypothesis 生成随机价格区间列表 + 随机阈值，验证 Layer1 + Layer2 + Layer3 = Total，且无区间同时属于 Layer1 和 Layer3
    - **Validates: Requirements 2.1, 2.5, 9.1, 9.2**

  - [x]* 3.3 编写 Property 4 属性测试：分层加权 NPV 计算正确性
    - **Property 4: Layer-weighted NPV calculation correctness**
    - 使用 Hypothesis 生成随机年度层级金额 + 随机折现率，验证 layer_weighted_npv == sum(NPV(layer_i, rate_i))
    - **Validates: Requirements 2.3, 2.4**

  - [x]* 3.4 编写 Property 12 属性测试：Layer 2 独立于阈值
    - **Property 12: Layer 2 revenue is independent of spread threshold**
    - 使用 Hypothesis 生成固定 FCAS 数据 + 变化的阈值，验证 Layer 2 金额不变
    - **Validates: Requirements 9.3**

- [x] 4. 后端引擎：NarrativeEngine
  - [x] 4.1 创建 `backend/engines/narrative_engine.py` 实现因果归因引擎
    - 实现 `__init__` 接受 EventRegistry 参数
    - 实现 `_load_templates` 加载结构化模板
    - 实现 `generate_spread_attribution` 方法：生成价差因果归因
    - 实现 `generate_revenue_change_attribution` 方法：生成年度收入变化归因
    - 实现 `generate_module_conclusion` 方法：为模块输出生成结论性归因
    - 使用模板驱动方式（非 LLM），引用 coal_retirement_schedule.json 和 capacity_data.json 数据
    - 实现降级策略：事件注册表为空时生成通用归因文本
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 15.1, 15.2_

- [x] 5. 后端引擎：EventAnnotationService
  - [x] 5.1 创建 `backend/engines/event_annotation_service.py` 实现事件标注服务
    - 实现 `__init__` 接受 EventRegistry 参数（直接引用，不重复存储）
    - 实现 `get_annotations` 方法：按区域、时间范围、事件类型过滤事件
    - 实现 `cluster_annotations` 方法：同一像素范围内多事件聚类合并
    - 支持 COAL_CLOSURE、BESS_COMMISSIONING、NETWORK_AUGMENTATION 三种事件类型
    - 区域无事件时返回空列表（不报错）
    - _Requirements: 4.1, 4.2, 4.5, 11.1, 11.2, 11.3, 11.4, 11.5, 17.6_

  - [x]* 5.2 编写 Property 5 属性测试：事件过滤正确性
    - **Property 5: Event filtering returns only matching region and time range**
    - 使用 Hypothesis 生成随机事件注册表 + 随机区域/时间范围，验证返回事件均满足 region 和 year 约束
    - **Validates: Requirements 4.1, 4.5, 11.2**

  - [x]* 5.3 编写 Property 6 属性测试：事件聚类保持总数
    - **Property 6: Event clustering preserves total count**
    - 使用 Hypothesis 生成随机事件列表 + 随机像素阈值，验证聚类后总事件数不变
    - **Validates: Requirements 11.4**

- [x] 6. 后端引擎：CrossValidationService
  - [x] 6.1 创建 `backend/engines/cross_validation_service.py` 实现交叉验证服务
    - 实现 `__init__` 接受 evidence_path 和 EventRegistry 参数
    - 实现 `_load_evidence` 从 financial_evidence.json 加载外部源数据
    - 实现 `compare_coal_retirements` 方法：对比煤电退役日期（平台 vs AEMO ISP vs 运营商公告）
    - 实现 `compare_revenue_benchmarks` 方法：对比收入基准（平台模型 vs Modo Energy 报告）
    - 实现 `compare_price_forecasts` 方法：对比价格预测（平台情景 vs AEMO ISP 情景）
    - 超过 12 个月未更新的外部源标记为 stale
    - 实现降级策略：外部源不可用时仅返回平台数据
    - _Requirements: 7.1, 7.2, 7.3, 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x]* 6.2 编写 Property 11 属性测试：过期标志正确性
    - **Property 11: Staleness flag correctness**
    - 使用 Hypothesis 生成随机日期，验证 is_stale 标志当且仅当 source_date 超过 12 个月时为 True
    - **Validates: Requirements 12.5**

- [x] 7. 后端引擎：ForwardPriceEngine 扩展
  - [x] 7.1 扩展 `backend/engines/forward_price_engine.py` 添加燃料敏感性分析方法
    - 实现 `calculate_fuel_sensitivity` 方法
    - 接受 region、scenario、battery、gas_base_price、gas_escalation_rate、pass_through_coefficient 参数
    - 输出 5 个情景：-20%, -10%, base, +10%, +20% 气价变化
    - 计算敏感性系数：BESS 年收入变化% / 气价变化 10%
    - 验证 pass_through_coefficient > 0，否则抛出验证错误
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 17.4_

  - [x] 7.2 扩展 `backend/engines/forward_price_engine.py` 添加网络增强影响建模
    - 实现网络增强事件处理逻辑：convergence_factor 范围 [0.05, 0.30]
    - 网络增强事件的 spread_impact_factor < 1（压缩价差）
    - 事件日期后所有年份应用负 spread_impact_factor
    - 从 capacity_data.json 的 `interconnectors` 字段读取事件数据
    - 验证 convergence_factor 范围，超出时抛出验证错误
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 17.5_

  - [x]* 7.3 编写 Property 7 属性测试：网络增强单调降低价差
    - **Property 7: Network augmentation reduces spread monotonically**
    - 使用 Hypothesis 生成随机价差 + 随机收敛因子 [0.05, 0.30]，验证事件后价差 <= 事件前价差
    - **Validates: Requirements 14.1, 14.2, 14.3**

  - [x]* 7.4 编写 Property 8 属性测试：燃料成本传导线性
    - **Property 8: Fuel cost pass-through is linear**
    - 使用 Hypothesis 生成随机气价变化 + 随机传导系数，验证 peak_price_impact == delta_gas × coeff
    - **Validates: Requirements 13.1, 13.5**

- [x] 8. 检查点 - 引擎层验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. API 路由层
  - [x] 9.1 创建 `backend/routes/narrative_routes.py` 实现叙事层 API 端点
    - 实现 `GET /api/v1/narrative/attribution/{region}` 因果归因端点
    - 实现 `GET /api/v1/narrative/stratification/{region}` 分层收入端点
    - 实现 `GET /api/v1/narrative/events/{region}` 事件标注端点
    - 实现 `GET /api/v1/narrative/cross-validation/{category}` 交叉验证端点
    - 实现 `GET/POST /api/v1/narrative/asset-config` 资产配置端点
    - 实现 `GET /api/v1/narrative/forward-spread/{region}` 前瞻价差曲线端点
    - 实现 `GET /api/v1/narrative/fuel-sensitivity/{region}` 燃料敏感性端点
    - 实现 `GET /api/v1/narrative/network-impact/{region}` 网络增强影响端点
    - 所有端点使用 Pydantic 模型进行请求验证和响应序列化
    - 实现错误处理：422 验证错误、503 数据不可用、200 降级响应
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 9.2 在 `backend/app.py` 中注册 narrative_routes 路由
    - 导入 narrative_routes router
    - 使用 `app.include_router` 注册到应用
    - _Requirements: 18.1_

  - [x]* 9.3 编写 Property 13 属性测试：前瞻价差输出格式合规
    - **Property 13: Forward spread projection output format compliance**
    - 使用 Hypothesis 生成随机区域和情景，验证响应包含 20 个 projection 条目，且 high_spread >= central_spread >= low_spread
    - **Validates: Requirements 10.4**

  - [x]* 9.4 编写路由层单元测试
    - 测试各端点的 422 验证错误响应
    - 测试 503 数据不可用降级
    - 测试正常请求的响应格式
    - _Requirements: 17.1-17.6, 18.1-18.6_

- [x] 10. 检查点 - 后端完整验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 前端组件：图表与可视化
  - [x] 11.1 创建 `web/src/components/modules/ForwardSpreadCurve.jsx` 前瞻价差曲线组件
    - 使用 Recharts LineChart + Area 实现 20 年三情景线图
    - 历史数据实线（黑色）、Central 蓝色虚线、High/Low 灰色虚线 + 浅蓝色置信带
    - 支持区域切换重新加载数据
    - 调用 `GET /api/v1/narrative/forward-spread/{region}` 获取数据
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 11.2 创建 `web/src/components/modules/RevenueStratificationChart.jsx` 收入分层图组件
    - 使用 Recharts StackedAreaChart 实现 20 年收入分层堆叠面积图
    - Layer 1 蓝色、Layer 2 琥珀色、Layer 3 红色
    - 悬浮显示各层金额和百分比
    - 显示 layer-weighted NPV 与 standard NPV 对比
    - 包含图例：层名称、置信度、折现率
    - 调用 `GET /api/v1/narrative/stratification/{region}` 获取数据
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 11.3 创建 `web/src/components/modules/EventAnnotationOverlay.jsx` 事件标注叠加层组件
    - 实现可复用的 Recharts 自定义组件
    - 煤电退役：红色倒三角 ▼；BESS 投运：蓝色正三角 ▲；网络增强：绿色菱形 ◆
    - 支持事件聚类：圆形 + 数字计数
    - 点击事件标记显示详情面板（名称、区域、容量、日期、置信度、影响因子）
    - 调用 `GET /api/v1/narrative/events/{region}` 获取数据
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 11.1, 11.2, 11.3, 11.4_

- [x] 12. 前端组件：面板与表格
  - [x] 12.1 创建 `web/src/components/modules/AssumptionPanel.jsx` 假设透明面板组件
    - 按类别分组展示所有模型输入假设（battery、cost、tax、forward_price、scenario）
    - 显示当前值、默认值、有效范围
    - 支持用户修改假设值并触发重新计算
    - 显示数据来源引用（financial_evidence.json）
    - 提供重置按钮恢复默认值
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 12.2 创建 `web/src/components/modules/AssetConfigPanel.jsx` 资产配置面板组件
    - 支持配置：region、power_mw、duration_hours、round_trip_efficiency、mlf、connection_point
    - 前端验证参数范围（power: 1-2000MW, duration: 0.5-12h, RTE: 0.70-0.95, MLF: 0.80-1.10）
    - 保存配置调用 `POST /api/v1/narrative/asset-config`
    - 配置变更触发所有下游模块重新计算
    - 结果标签显示用户资产参数（如 "For YOUR 100MW/4h BESS at NSW1"）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 12.3 创建 `web/src/components/modules/CrossValidationTable.jsx` 交叉验证表组件
    - 渲染多源数据对比表格
    - 显示：数据点、来源名称、来源日期、报告值、差异百分比
    - 差异超过 10% 的数据点高亮显示
    - 过期数据（is_stale）显示警告标志
    - 调用 `GET /api/v1/narrative/cross-validation/{category}` 获取数据
    - _Requirements: 7.4, 7.5, 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 12.4 创建 `web/src/components/modules/NarrativeTooltip.jsx` 因果归因提示组件
    - 实现可展开的悬浮提示组件
    - 显示指标的因果归因链：驱动因素名称、类型、贡献量、来源引用
    - 支持任意触发元素（指标数值）
    - 调用 `GET /api/v1/narrative/attribution/{region}` 获取数据
    - _Requirements: 1.2, 1.3, 1.5_

- [x] 13. 前端集成与布线
  - [x] 13.1 将叙事层组件集成到 Investment Outlook Stage（Stage 4）
    - 在 Stage 4 页面中集成 ForwardSpreadCurve + EventAnnotationOverlay
    - 在 Stage 4 页面中集成 RevenueStratificationChart
    - 通过 marketConfig 模块注册表注册新组件
    - _Requirements: 4.4, 5.1, 3.1_

  - [x] 13.2 将叙事层组件集成到 Financial Modeling Stage（Stage 6）
    - 在 Stage 6 页面中集成 AssumptionPanel + AssetConfigPanel
    - 在 Stage 6 页面中集成 CrossValidationTable
    - 在 Stage 6 页面中集成燃料敏感性展示（sensitivity table: -20%, -10%, base, +10%, +20%）
    - 在 Stage 6 页面中集成网络增强前后对比展示
    - 通过 marketConfig 模块注册表注册新组件
    - _Requirements: 6.1, 8.1, 7.4, 13.4, 14.4_

  - [x] 13.3 集成 NarrativeTooltip 到所有关键指标展示位置
    - 在 spread、revenue、NPV、IRR 等关键指标旁添加 NarrativeTooltip
    - 确保 tooltip 数据按需加载（hover 时请求）
    - _Requirements: 1.2, 1.5_

  - [x]* 13.4 编写前端组件单元测试
    - 测试 ForwardSpreadCurve 渲染三条情景线
    - 测试 RevenueStratificationChart 堆叠面积图颜色编码
    - 测试 EventAnnotationOverlay 事件标记类型和颜色
    - 测试 AssetConfigPanel 参数验证
    - 测试 CrossValidationTable 差异高亮逻辑
    - _Requirements: 3.1-3.5, 5.1-5.5, 8.4_

- [x] 14. 最终检查点 - 全功能验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (13 properties from design)
- Unit tests validate specific examples and edge cases
- 后端使用 Python + FastAPI + Pydantic，前端使用 React + Recharts
- 属性测试使用 Hypothesis 框架（项目已配置）
- 所有新组件通过 marketConfig 模块注册表集成，不破坏现有阶段结构

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "1.6"] },
    { "id": 2, "tasks": ["3.1", "4.1", "5.1", "6.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "5.2", "5.3", "6.2", "7.1", "7.2"] },
    { "id": 4, "tasks": ["7.3", "7.4", "9.1"] },
    { "id": 5, "tasks": ["9.2", "9.3", "9.4"] },
    { "id": 6, "tasks": ["11.1", "11.2", "11.3", "12.1", "12.2", "12.3", "12.4"] },
    { "id": 7, "tasks": ["13.1", "13.2", "13.3"] },
    { "id": 8, "tasks": ["13.4"] }
  ]
}
```
