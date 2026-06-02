# Requirements Document

## Introduction

基于对 ForwardPriceEngine（规则模型）和 MLCalibrationEngine（LightGBM 校准）的实际市场数据交叉验证，发现多个精度问题。本 spec 将这些修复整合为统一升级方案，涵盖 FCAS 收入衰减建模、Capture Rate 公式更新、ML Concept Drift 修复、BESS 容量管道建模、需求侧增长、煤电退役延期缓冲、Duration 非线性效应、市场改革风险标注、Quantile Regression 改进和日内粒度特征增强。

## Glossary

- **ForwardPriceEngine**: 规则模型引擎，基于事件注册表和指数衰减压缩公式生成 20 年三情景价差预测
- **MLCalibrationEngine**: LightGBM Quantile Regression 校准引擎，从历史数据学习 base_spread 校准值
- **FCAS**: Frequency Control Ancillary Services，频率控制辅助服务
- **Capture_Rate**: BESS 套利捕获率，实际可获取价差占理论价差的比例
- **Compression_Factor**: BESS 饱和压缩因子，衡量 BESS 渗透率对价差的压缩效应
- **Concept_Drift**: 机器学习中训练数据分布与预测目标分布发生结构性偏移的现象
- **Pipeline_Realization_Rate**: 管道实现率，区分 committed/proposed/speculated 项目的实际转化概率
- **Duration_Efficiency_Factor**: 储能时长效率因子，反映不同时长 BESS 的边际收入递减效应
- **PEAK_DEMAND**: 各区域峰值需求常量（MW），用于计算 BESS 容量比
- **PSF**: Price Setting Frequency，BESS 价格设定频率
- **Modo_Energy**: 第三方 BESS 收入基准数据提供商
- **NEM**: National Electricity Market，澳洲国家电力市场
- **SoH**: State of Health，电池健康状态
- **RTE**: Round Trip Efficiency，往返效率
- **Autobidder**: 自动竞价系统，BESS 运营商用于优化调度的软件

## Requirements

### Requirement 1: FCAS 收入衰减纳入前瞻模型

**User Story:** As a 储能投资分析师, I want ForwardPriceEngine 在 20 年预测中包含 FCAS 收入衰减轨迹, so that 投资回报预测不会因忽略 FCAS 崩塌而系统性高估。

#### Acceptance Criteria

1. WHEN ForwardPriceEngine 生成年度收入预测, THE ForwardPriceEngine SHALL 输出独立的 FCAS 收入分量（与能量套利收入分开）
2. WHEN 计算 FCAS 年度收入, THE ForwardPriceEngine SHALL 使用 FcasCollapseEngine 的供需比模型计算各年份的 FCAS 价格天花板
3. THE ForwardPriceEngine SHALL 确保 FCAS 收入分量随 BESS 容量增长单调递减
4. WHEN MLCalibrationEngine 提取训练特征, THE MLCalibrationEngine SHALL 从 rolling_30d_spread 中剥离 FCAS 价格成分（仅保留能量套利价差信号）
5. IF FCAS 收入分量计算失败, THEN THE ForwardPriceEngine SHALL 将 FCAS 收入设为零并在 metadata 中标注降级状态

### Requirement 2: Capture Rate 模型更新

**User Story:** As a 储能投资分析师, I want Capture Rate 公式反映 2025-2026 年的实际市场竞争水平, so that 收入预测不会因过时的捕获率假设而高估。

#### Acceptance Criteria

1. THE ForwardPriceEngine SHALL 使用 0.55 作为 BASE_CAPTURE_RATE 基准值（替代当前 0.65）
2. WHEN 计算 capture_rate, THE ForwardPriceEngine SHALL 应用 autobidder 竞争因子：capture_rate = base × compression^0.5 × autobidder_decay(year)
3. THE ForwardPriceEngine SHALL 确保 autobidder_decay 函数随年份单调递减，范围为 [0.7, 1.0]
4. WHEN BESS 容量比超过 0.30, THE ForwardPriceEngine SHALL 确保 capture_rate 不超过 0.40
5. THE ForwardPriceEngine SHALL 引入 fleet_size_factor 参数，使 capture_rate 随区域 BESS 项目数量增加而额外衰减
6. WHILE 模型输出 capture_rate, THE ForwardPriceEngine SHALL 确保 capture_rate 始终在 [0.10, 0.55] 范围内

### Requirement 3: ML 模型 Concept Drift 修复

**User Story:** As a 储能投资分析师, I want MLCalibrationEngine 能识别并适应 BESS 渗透率结构性断裂, so that 校准参数不会被高价差历史时期污染。

#### Acceptance Criteria

1. WHEN MLCalibrationEngine 训练模型, THE MLCalibrationEngine SHALL 使用滚动窗口策略（最近 12 个月数据权重为 1.0，12-24 个月权重为 0.5，24 个月以前权重为 0.2）
2. THE MLCalibrationEngine SHALL 将 bess_capacity_ratio 特征的 LightGBM monotone_constraints 设为 -1（强制单调递减关系）
3. WHEN bess_capacity_ratio 超过训练集最大值, THE MLCalibrationEngine SHALL 在 calibration_metadata 中标注 extrapolation_warning
4. THE MLCalibrationEngine SHALL 在 calibration_metadata 中输出 regime_indicator 字段，标识当前处于哪个渗透率区间（low: <5%, medium: 5-15%, high: >15%）
5. IF 验证集 MAE 超过训练集 MAE 的 2 倍, THEN THE MLCalibrationEngine SHALL 触发 concept_drift_detected 警告并降低校准权重至 0.5

### Requirement 4: BESS 容量管道建模

**User Story:** As a 储能投资分析师, I want 前瞻模型区分不同确定性级别的 BESS 管道项目, so that 容量预测不会因将所有管道项目等同视之而失真。

#### Acceptance Criteria

1. WHEN ForwardPriceEngine 计算未来 BESS 容量, THE ForwardPriceEngine SHALL 对 committed 项目应用 90% 实现率、对 proposed 项目应用 50% 实现率、对 speculated 项目应用 20% 实现率
2. THE ForwardPriceEngine SHALL 从 capacity_data.json 的 status 字段映射项目确定性级别
3. WHEN 计算累计 BESS 容量, THE ForwardPriceEngine SHALL 输出加权容量（capacity_mw × realization_rate）而非原始容量
4. THE ForwardPriceEngine SHALL 确保加权后的累计容量随时间单调递增
5. IF capacity_data.json 中出现未知 status 值, THEN THE ForwardPriceEngine SHALL 使用 20% 默认实现率并记录警告日志

### Requirement 5: 需求侧增长建模

**User Story:** As a 储能投资分析师, I want PEAK_DEMAND 随时间增长以反映数据中心等新负荷, so that BESS 容量比不会因静态需求假设而被高估。

#### Acceptance Criteria

1. WHEN ForwardPriceEngine 计算 bess_capacity_ratio, THE ForwardPriceEngine SHALL 使用动态 PEAK_DEMAND 值：peak_demand(year) = base_peak_demand × (1 + annual_growth_rate)^(year - base_year)
2. THE ForwardPriceEngine SHALL 使用 2025 作为 base_year，年增长率默认为 0.025（2.5%/年）
3. THE ForwardPriceEngine SHALL 确保动态 PEAK_DEMAND 不低于当前静态值（向下兼容）
4. WHEN 年增长率参数超出 [0.0, 0.10] 范围, THE ForwardPriceEngine SHALL 拒绝该参数并使用默认值 0.025
5. THE ForwardPriceEngine SHALL 在 metadata 中输出各年份使用的 effective_peak_demand 值

### Requirement 6: 煤电退役延期缓冲

**User Story:** As a 储能投资分析师, I want Central 情景包含煤电退役延期的可能性, so that 价差预测不会因假设煤电准时退役而过于乐观。

#### Acceptance Criteria

1. WHEN ForwardPriceEngine 在 Central 情景处理煤电退役事件, THE ForwardPriceEngine SHALL 将退役日期延后 2 年作为缓冲
2. WHEN ForwardPriceEngine 在 High 情景处理煤电退役事件, THE ForwardPriceEngine SHALL 保持当前逻辑（提前 2 年退役）不变
3. WHEN ForwardPriceEngine 在 Low 情景处理煤电退役事件, THE ForwardPriceEngine SHALL 将退役日期延后 4 年（当前 3 年 + 额外 1 年缓冲）
4. THE ForwardPriceEngine SHALL 确保调整后的退役日期不早于当前日期
5. THE ForwardPriceEngine SHALL 在 ScenarioDefinition.assumptions 中明确标注延期缓冲假设

### Requirement 7: Duration 非线性收入效应

**User Story:** As a 储能投资分析师, I want 收入公式反映不同储能时长的边际收入递减效应, so that 4h 和 8h BESS 的收入预测更贴近实际。

#### Acceptance Criteria

1. WHEN ForwardPriceEngine 计算年度收入, THE ForwardPriceEngine SHALL 应用 duration_efficiency_factor 替代线性 duration_hours 乘数
2. THE ForwardPriceEngine SHALL 使用公式 duration_efficiency_factor = duration_hours^gamma（gamma 默认 0.85）计算有效时长
3. THE ForwardPriceEngine SHALL 确保 duration_efficiency_factor 随 duration_hours 单调递增
4. THE ForwardPriceEngine SHALL 确保 2h BESS 的 duration_efficiency_factor 为 2^0.85 ≈ 1.81，4h 为 4^0.85 ≈ 3.28，8h 为 8^0.85 ≈ 5.93
5. WHEN duration_hours 超过 12, THE ForwardPriceEngine SHALL 将 gamma 降至 0.75（超长时储能边际递减更快）

### Requirement 8: 市场改革风险标注

**User Story:** As a 储能投资分析师, I want 前瞻预测结果包含结构性市场改革风险标注, so that 投资决策能考虑 NEM 从 merchant 模式转向 contracted 模式的可能性。

#### Acceptance Criteria

1. THE ForwardPriceEngine SHALL 在 ScenarioProjection 的 metadata 中包含 structural_risks 列表字段
2. WHEN 预测年份超过 2028, THE ForwardPriceEngine SHALL 在 structural_risks 中添加 "Nelson Review: potential shift from merchant to contracted model"
3. THE ForwardPriceEngine SHALL 确保 structural_risks 字段为字符串列表，不影响数值计算逻辑
4. IF structural_risks 列表为空, THEN THE ForwardPriceEngine SHALL 输出空列表而非 null

### Requirement 9: Quantile Regression 方法论改进

**User Story:** As a 储能投资分析师, I want ML 校准的概率预测更加可靠, so that P10/P50/P90 置信区间能真实反映预测不确定性。

#### Acceptance Criteria

1. WHEN MLCalibrationEngine 训练完成后, THE MLCalibrationEngine SHALL 对 P10/P50/P90 预测应用 Isotonic Regression 后处理以消除 quantile crossing
2. THE MLCalibrationEngine SHALL 验证校准后的分位数满足 P10 ≤ P50 ≤ P90（对所有预测样本）
3. WHEN 多个区域的预测结果可用, THE MLCalibrationEngine SHALL 计算 SQR Averaging（Simple Quantile Regression Averaging）作为集成预测
4. THE MLCalibrationEngine SHALL 在 calibration_metadata 中输出 pinball_loss 指标（各分位数的 pinball loss 均值）
5. IF Isotonic Regression 后处理导致 P10-P90 区间宽度小于 20 AUD/MWh, THEN THE MLCalibrationEngine SHALL 将区间宽度扩展至最小 20 AUD/MWh

### Requirement 10: 日内粒度特征增强

**User Story:** As a 储能投资分析师, I want ML 模型捕获日内价格结构变化, so that 校准能反映晚峰与午间价差的演变趋势。

#### Acceptance Criteria

1. WHEN MLCalibrationEngine 提取日度特征, THE MLCalibrationEngine SHALL 计算 evening_solar_spread 特征（17:00-21:00 均价 - 10:00-14:00 均价）
2. WHEN MLCalibrationEngine 提取日度特征, THE MLCalibrationEngine SHALL 计算 morning_ramp_spread 特征（06:00-09:00 均价 - 00:00-05:00 均价）
3. THE MLCalibrationEngine SHALL 对新增特征使用前一天的值作为滞后特征（lag_1_evening_solar_spread, lag_1_morning_ramp_spread）以消除数据泄漏
4. THE MLCalibrationEngine SHALL 确保新增特征不改变现有特征的计算逻辑
5. IF 半小时数据不可用（interval_count < 48）, THEN THE MLCalibrationEngine SHALL 将日内特征设为 0.0 并标记该记录为 incomplete_intraday

## Cross-Cutting Constraints

### Constraint 1: API 契约向后兼容

THE ForwardPriceEngine SHALL 保持现有 API 响应结构不变，所有新增字段为可选字段（不破坏现有消费者）。

### Constraint 2: 数学不变量保持

THE ForwardPriceEngine SHALL 确保以下不变量在所有修改后仍然成立：
- compression_factor 随 bess_capacity_ratio 单调递减
- mean_spread 非负
- capture_rate 在 [0.10, 0.55] 范围内
- P10 ≤ P50 ≤ P90（分位数排序）
- 年度收入随 SoH 单调递减

### Constraint 3: ML 降级兼容

IF MLCalibrationEngine 校准失败或质量不足, THEN THE ForwardPriceEngine SHALL 使用规则模型默认参数继续运行，不中断服务。

### Constraint 4: 基准验证阈值

THE ForwardPriceEngine SHALL 确保与 Modo Energy 基准数据的偏差不超过 30%（对 2024-2025 年已知数据点）。

### Constraint 5: Hypothesis 属性测试覆盖

所有新增数学公式和不变量 SHALL 有对应的 Hypothesis 属性测试验证。
