# Requirements Document

## Introduction

本文档定义 AEMO Intelligence 平台市场分析模块的全面重新设计需求。重新设计的核心目标是：将现有 4 阶段分析流程升级为 5-6 阶段的 2025 BESS 投资决策流程，新增 NEM 和 WEM 市场专属分析模块以反映当前市场现实（极端价格事件主导收入、FCAS 饱和、BESS 饱和风险、WEM 容量信用机制），并用全新的 LP/MILP 联合优化引擎替代现有回测系统。

## Glossary

- **Platform**: AEMO Intelligence 能源市场分析平台，包含 FastAPI 后端和 React 19 前端
- **MarketPage**: 统一市场页面编排器组件，根据 market prop 加载对应配置并渲染各 Stage 组件
- **Stage_Component**: 阶段组件，MarketPage 中按投资决策流程划分的独立分析区块
- **Market_Config**: 市场配置对象（marketConfig.js），定义各市场的阶段、模块、区域等元数据
- **Co_Optimization_Engine**: 联合优化引擎，基于 LP/MILP 同时优化能量套利和辅助服务调度的计算核心
- **Spike_Profit_Module**: 极端价格事件利润分析模块，专注于 >$3000/MWh 价格事件的收入贡献分析
- **Saturation_Tracker**: BESS 饱和度追踪模块，监控已注册和管道中的储能容量对市场收入的稀释效应
- **Regional_Ranking_Module**: 区域排名模块，基于多维度指标对 NEM 五个区域进行投资吸引力排序
- **Capacity_Credits_Module**: WEM 容量信用分析模块，计算储能项目的容量信用收入（$360k/MW/yr 量级）
- **STEM_Balancing_Module**: WEM STEM/Balancing 价差分析模块，分析短期能量市场的套利机会
- **Five_Min_Settlement_Module**: WEM 5 分钟结算影响分析模块，评估即将实施的 5 分钟结算对储能收入的影响
- **Capacity_Data_Source**: 容量数据源，基于 AEMO Generation Information 报告手动维护的 JSON/SQLite 表
- **NEM**: 国家电力市场 (National Electricity Market)，覆盖澳大利亚东部五州
- **WEM**: 西澳电力市场 (Western Australian Electricity Market)
- **FCAS**: 频率控制辅助服务 (Frequency Control Ancillary Services)
- **ESS**: 基本系统服务 (Essential System Services)，WEM 的辅助服务机制
- **BESS**: 电池储能系统 (Battery Energy Storage System)
- **MILP**: 混合整数线性规划 (Mixed-Integer Linear Programming)
- **LP**: 线性规划 (Linear Programming)

## Requirements

### 需求 1：阶段结构重新设计

**用户故事：** 作为储能投资分析师，我希望分析流程反映 2025 年 BESS 投资决策的实际逻辑（市场筛选 → 收入深潜 → 饱和评估 → 联合优化回测 → 财务建模 → 投资决策），以便按照正确的决策顺序逐步深入分析。

#### 验收标准

1. THE Market_Config SHALL 定义 5 至 6 个阶段，按以下顺序组织投资决策流程：市场筛选、收入深潜、饱和与竞争评估、联合优化回测、财务建模、投资决策
2. THE MarketPage SHALL 按 Market_Config 中定义的阶段顺序渲染对应的 Stage_Component，每个阶段包含独立的标题、核心问题描述和模块列表
3. WHEN Market_Config 中的阶段数量或顺序发生变化时，THE MarketPage SHALL 自动适配新的阶段结构，无需修改编排器代码
4. THE Market_Config SHALL 为 NEM 和 WEM 分别定义独立的阶段配置，允许两个市场拥有不同的阶段数量和模块组合
5. THE Platform SHALL 为每个阶段定义 core_question 字段（中英双语），描述该阶段回答的核心投资问题

### 需求 2：NEM 极端价格事件利润分析模块

**用户故事：** 作为储能投资分析师，我希望量化极端价格事件（>$3000/MWh）对 BESS 年收入的贡献比例和分布特征，以便评估收入集中度风险和捕获策略。

#### 验收标准

1. THE Spike_Profit_Module SHALL 计算指定区域和时间范围内价格超过可配置阈值（默认 $3000/MWh）的事件数量、持续时长和理论最大收入贡献
2. THE Spike_Profit_Module SHALL 计算极端价格事件收入占年度总套利收入的百分比
3. WHEN 用户选择特定区域和年份时，THE Spike_Profit_Module SHALL 展示极端价格事件的月度分布、时段分布和持续时长分布图表
4. THE Spike_Profit_Module SHALL 提供历史极端事件频率的年际趋势分析，支持至少 3 年的对比
5. IF 选定时间范围内无极端价格事件发生，THEN THE Spike_Profit_Module SHALL 显示"当前筛选条件下无极端价格事件"提示并展示该区域的历史事件频率作为参考

### 需求 3：NEM BESS 饱和度追踪模块

**用户故事：** 作为储能投资分析师，我希望追踪各区域已注册和管道中的 BESS 容量，以便评估市场饱和风险对未来收入的稀释效应。

#### 验收标准

1. THE Saturation_Tracker SHALL 从 Capacity_Data_Source 读取各 NEM 区域的已注册 BESS 容量（MW）和已公布管道容量（MW）
2. THE Saturation_Tracker SHALL 计算并展示各区域的饱和度指标：已注册容量/峰值负荷比率、管道容量/已注册容量比率
3. WHEN Capacity_Data_Source 数据更新时，THE Saturation_Tracker SHALL 在下次页面加载时反映最新数据
4. THE Saturation_Tracker SHALL 提供饱和度对收入稀释的估算模型，展示不同饱和水平下的预期收入衰减曲线
5. THE Saturation_Tracker SHALL 按区域展示容量增长时间线，标注关键项目的预计投运日期

### 需求 4：容量数据源管理

**用户故事：** 作为平台维护者，我希望通过手动维护的 JSON 或 SQLite 表管理 AEMO Generation Information 报告中的容量数据，以便在无自动化管道的情况下保持数据更新。

#### 验收标准

1. THE Capacity_Data_Source SHALL 以 JSON 文件或 SQLite 表的形式存储各区域的 BESS 容量数据，包含字段：区域、项目名称、容量 MW、储能时长、状态（已注册/在建/规划）、预计投运日期
2. THE Platform SHALL 提供数据校验机制，在加载 Capacity_Data_Source 时验证必填字段完整性和数据类型正确性
3. WHEN Capacity_Data_Source 文件格式错误或数据缺失时，THE Platform SHALL 记录详细错误日志并回退到上一个有效版本的数据
4. THE Capacity_Data_Source SHALL 包含 last_updated 元数据字段，记录数据最后更新时间
5. THE Platform SHALL 在使用容量数据的模块中显示数据更新时间，提示用户数据的时效性

### 需求 5：NEM 区域排名模块

**用户故事：** 作为储能投资分析师，我希望基于多维度指标对 NEM 五个区域进行投资吸引力排序，以便快速识别最优投资区域。

#### 验收标准

1. THE Regional_Ranking_Module SHALL 基于以下维度对 NEM 五个区域（NSW1、QLD1、VIC1、SA1、TAS1）进行综合排名：套利收入潜力、极端事件频率、FCAS 收入潜力、饱和度风险、网络约束频率
2. THE Regional_Ranking_Module SHALL 为每个排名维度提供可配置的权重参数，默认权重均等分配
3. WHEN 用户调整排名权重时，THE Regional_Ranking_Module SHALL 实时重新计算排名结果并更新展示
4. THE Regional_Ranking_Module SHALL 以表格和雷达图两种形式展示各区域的多维度得分
5. THE Regional_Ranking_Module SHALL 在排名结果中标注各维度的数据来源年份和计算方法说明

### 需求 6：NEM 联合优化回测引擎

**用户故事：** 作为储能投资分析师，我希望使用联合优化引擎同时优化能量套利和 FCAS 调度策略，以便获得比单独优化更接近实际运营的收入估算。

#### 验收标准

1. THE Co_Optimization_Engine SHALL 使用 LP/MILP 求解器同时优化能量市场套利和 FCAS 市场参与的调度决策
2. THE Co_Optimization_Engine SHALL 在优化模型中包含以下约束：充放电功率互斥、SOC 上下限、循环效率损耗、FCAS 容量预留与能量调度的耦合约束、最小持续时间要求
3. WHEN 用户请求联合优化回测时，THE Co_Optimization_Engine SHALL 返回能量套利收入和 FCAS 收入的分项明细，以及联合优化相对于单独优化的增量收入
4. THE Co_Optimization_Engine SHALL 支持按月分段求解，每月独立优化并汇总年度结果
5. IF MILP 求解器在 60 秒内未找到最优解，THEN THE Co_Optimization_Engine SHALL 返回当前最优可行解并在结果中标注 optimality_gap 百分比
6. THE Co_Optimization_Engine SHALL 替代现有的单一套利回测引擎作为平台的默认回测方法，但保留旧引擎作为 energy-only 对比基准（用于计算联合优化增量收入）

### 需求 7：WEM 容量信用分析模块

**用户故事：** 作为储能投资分析师，我希望分析 WEM 容量信用机制对 BESS 项目的收入贡献，以便评估容量信用作为 WEM 最大收入来源（$360k/MW/yr 量级）的投资价值。

#### 验收标准

1. THE Capacity_Credits_Module SHALL 计算指定 BESS 配置（功率、时长）在 WEM 容量信用机制下的预期年度收入
2. THE Capacity_Credits_Module SHALL 展示容量信用价格的历史趋势和当前价格水平
3. THE Capacity_Credits_Module SHALL 计算储能项目的容量信用资格系数（基于 BESS 时长和可用性要求）
4. WHEN 用户修改 BESS 参数（功率、时长）时，THE Capacity_Credits_Module SHALL 重新计算容量信用收入估算
5. THE Capacity_Credits_Module SHALL 提供容量信用收入与能量市场收入的对比分析，展示各收入来源的占比

### 需求 8：WEM STEM/Balancing 价差分析模块

**用户故事：** 作为储能投资分析师，我希望分析 WEM STEM 市场和 Balancing 市场之间的价差机会，以便评估短期能量市场的套利潜力。

#### 验收标准

1. THE STEM_Balancing_Module SHALL 计算 STEM 市场价格与 Balancing 市场价格之间的价差统计（均值、中位数、百分位分布）
2. THE STEM_Balancing_Module SHALL 展示价差的时段分布模式（按小时、按日类型）
3. WHEN 用户选择特定时间范围时，THE STEM_Balancing_Module SHALL 展示该范围内的价差趋势图和累计套利机会估算
4. THE STEM_Balancing_Module SHALL 计算基于历史价差的理论套利收入（考虑 BESS 物理约束）
5. IF STEM 或 Balancing 市场数据不可用，THEN THE STEM_Balancing_Module SHALL 显示数据不可用状态并标注缺失的数据源

### 需求 9：WEM 5 分钟结算影响分析模块

**用户故事：** 作为储能投资分析师，我希望评估 WEM 即将实施的 5 分钟结算对储能收入的影响，以便在投资决策中考虑市场规则变化的影响。

#### 验收标准

1. THE Five_Min_Settlement_Module SHALL 基于现有 30 分钟数据模拟 5 分钟结算场景下的价格波动性变化
2. THE Five_Min_Settlement_Module SHALL 计算 5 分钟结算相对于 30 分钟结算的预期收入变化百分比
3. THE Five_Min_Settlement_Module SHALL 展示结算间隔缩短对价差分布、极端事件捕获率和调度灵活性的影响分析
4. WHEN 5 分钟实际结算数据可用时，THE Five_Min_Settlement_Module SHALL 自动切换到实际数据分析模式并标注数据来源为实际结算数据
5. THE Five_Min_Settlement_Module SHALL 提供 30 分钟结算与 5 分钟结算的并排对比视图

### 需求 10：WEM 饱和度追踪模块

**用户故事：** 作为储能投资分析师，我希望追踪 WEM 市场的 BESS 容量增长和饱和风险，以便评估 WEM 市场的长期投资可行性。

#### 验收标准

1. THE WEM Saturation_Tracker SHALL 从 Capacity_Data_Source 读取 WEM 区域的已注册和管道中 BESS 容量数据
2. THE WEM Saturation_Tracker SHALL 计算 WEM 市场的饱和度指标：已注册 BESS 容量/系统峰值负荷比率
3. THE WEM Saturation_Tracker SHALL 展示 WEM 容量信用供需平衡分析，评估新增 BESS 对容量信用价格的潜在压力
4. THE WEM Saturation_Tracker SHALL 提供 WEM 与 NEM 各区域饱和度的横向对比视图
5. WHEN Capacity_Data_Source 中 WEM 数据缺失时，THE WEM Saturation_Tracker SHALL 显示数据不可用状态并提示需要更新容量数据

### 需求 11：Market Config 架构升级

**用户故事：** 作为平台开发者，我希望 marketConfig 架构能灵活支持新增阶段和模块的注册，以便在不修改核心编排逻辑的情况下扩展分析能力。

#### 验收标准

1. THE Market_Config SHALL 支持为每个阶段定义模块列表，每个模块条目包含：组件名称、数据依赖声明、加载优先级
2. THE Market_Config SHALL 支持模块级别的 feature flag，允许通过配置启用或禁用特定模块而无需修改代码
3. WHEN 新模块添加到 Market_Config 时，THE MarketPage SHALL 自动发现并渲染该模块，无需修改 MarketPage 组件代码
4. THE Market_Config SHALL 为每个模块定义 data_dependencies 字段，声明该模块所需的后端 API 端点
5. IF Market_Config 中引用的模块组件不存在，THEN THE MarketPage SHALL 跳过该模块并在控制台记录警告，不影响其他模块的渲染

### 需求 12：后端 API 端点扩展

**用户故事：** 作为平台开发者，我希望后端提供新模块所需的 API 端点，以便前端模块能获取计算结果。

#### 验收标准

1. THE Platform SHALL 为 Spike_Profit_Module 提供 API 端点，接受区域、年份、价格阈值参数，返回极端事件统计和收入贡献分析
2. THE Platform SHALL 为 Saturation_Tracker 提供 API 端点，返回各区域的容量数据和饱和度指标
3. THE Platform SHALL 为 Regional_Ranking_Module 提供 API 端点，接受权重参数，返回各区域的多维度得分和综合排名
4. THE Platform SHALL 为 Co_Optimization_Engine 提供 API 端点，接受 BESS 参数和优化配置，返回联合优化回测结果
5. THE Platform SHALL 为 WEM 专属模块（Capacity_Credits、STEM_Balancing、Five_Min_Settlement）提供独立的 API 端点
6. WHEN 任何新 API 端点请求失败时，THE Platform SHALL 返回结构化错误响应，包含 error_code、message 和 suggested_action 字段
