# Requirements Document

## Introduction

本文档定义 AEMO Intelligence 能源市场分析平台的全面优化需求，涵盖四个阶段：业务正确性修复、架构重构、数据管道完善、商业化准备。优化目标是消除已知的计算错误、改善代码可维护性、补全数据管道缺口，并为生产部署建立完整的质量保障体系。

## Glossary

- **Platform**: AEMO Intelligence 能源市场分析平台，包含 FastAPI 后端和 React 前端
- **Revenue_Stacking_Engine**: 收入叠加分析引擎，负责计算 BESS 储能多市场收入组合
- **Price_Analysis_Module**: 价格分析模块，负责电价时间序列统计与可视化
- **Revenue_Analysis_Module**: 收入分析模块，负责基于价格数据计算实际收入（含容量、效率、损耗）
- **Investment_Model**: 投资分析模型，负责 NPV/IRR 计算及敏感性分析
- **Degradation_Rate**: 电池衰减率参数，表示电池容量随循环次数下降的年化比率
- **WEM**: 西澳电力市场 (Western Australian Electricity Market)
- **NEM**: 国家电力市场 (National Electricity Market)，覆盖澳大利亚东部五州
- **ESS**: 基本系统服务 (Essential System Services)，WEM 的辅助服务机制
- **FCAS**: 频率控制辅助服务 (Frequency Control Ancillary Services)，NEM 的辅助服务机制
- **MILP**: 混合整数线性规划 (Mixed-Integer Linear Programming)
- **Backtest_Engine**: 回测引擎，基于历史数据模拟 BESS 调度策略的收益表现
- **Route_Module**: 路由模块，FastAPI 中按业务域划分的 APIRouter 子模块
- **Filter_Context**: 过滤上下文，用户在前端选择的市场/区域/时间范围等筛选条件的集合
- **Data_Pipeline**: 数据管道，从外部数据源获取、清洗、存储市场数据的自动化流程
- **Server_Module**: 后端主服务文件 server.py，当前包含所有 API 路由定义（7000+ 行）
- **Frontend_State**: 前端状态管理，App.jsx 中集中管理的应用状态（900+ 行）

## Requirements

### 需求 1：价格分析与收入分析分离

**用户故事：** 作为储能投资分析师，我希望价格分析和收入分析是独立的计算模块，以便获得维度正确的分析结果，避免将价格序列（$/MWh）与收入值（$）混淆。

#### 验收标准

1. THE Revenue_Stacking_Engine SHALL 将价格序列分析（单位：$/MWh）与收入计算（单位：$）分离为独立的计算路径
2. WHEN 用户请求价格分析时，THE Price_Analysis_Module SHALL 返回以 $/MWh 为单位的统计结果，且不包含容量或效率参数的影响
3. WHEN 用户请求收入分析时，THE Revenue_Analysis_Module SHALL 基于价格数据、电池容量、循环效率和损耗系数计算以 $ 为单位的收入结果
4. THE Platform SHALL 在所有分析结果的 metadata 中包含 unit 字段，明确标注当前结果的计量单位
5. IF 价格分析结果被传入收入计算接口，THEN THE Revenue_Analysis_Module SHALL 验证输入维度并返回明确的维度不匹配错误

### 需求 2：电池衰减率参数生效

**用户故事：** 作为储能投资分析师，我希望自定义的电池衰减率参数能在投资模型中生效，以便准确评估不同衰减假设下的长期投资回报。

#### 验收标准

1. WHEN 用户提供 degradation_rate 参数时，THE Investment_Model SHALL 使用用户指定的衰减率替代内置默认值进行全生命周期计算
2. THE Investment_Model SHALL 在响应中包含 degradation_model 字段，标明实际使用的衰减模型类型和参数值
3. WHEN 用户未提供 degradation_rate 参数时，THE Investment_Model SHALL 使用内置双因子衰减模型并在响应中标注 degradation_model 为 "dual-factor-default"
4. THE Investment_Model SHALL 支持以下衰减模型输入格式：单一年化线性衰减率（0 至 0.15 之间的浮点数）
5. IF 用户提供的 degradation_rate 超出有效范围（0 至 0.15），THEN THE Investment_Model SHALL 返回参数校验错误并说明有效范围

### 需求 3：WEM 市场能力边界标注

**用户故事：** 作为能源市场分析师，我希望前端界面清晰标注 WEM 市场数据的完整性边界，以便了解哪些 WEM 功能已完全实现、哪些仍处于预览状态。

#### 验收标准

1. THE Platform SHALL 在 WEM 相关页面显示数据完整性标注，区分"完整数据"和"预览数据"两种状态
2. WHILE WEM ESS 数据管道未连接，THE Platform SHALL 在 ESS 相关分析结果上显示"预览 — ESS 管道未连接"标注
3. WHILE WEM FCAS 数据管道未完成，THE Platform SHALL 在 FCAS 相关分析结果上显示"预览 — FCAS 数据有限"标注
4. THE Platform SHALL 通过 API 响应 metadata 中的 data_completeness 字段传递数据完整性状态（值为 "complete" 或 "preview"）
5. WHEN 数据管道状态发生变化时，THE Platform SHALL 自动更新对应模块的完整性标注，无需手动干预

### 需求 4：后端路由模块化拆分

**用户故事：** 作为平台开发者，我希望将 server.py 按业务域拆分为独立的路由模块，以便提高代码可维护性和团队协作效率。

#### 验收标准

1. THE Platform SHALL 将 Server_Module 拆分为按业务域组织的独立 Route_Module 文件，每个文件不超过 800 行
2. THE Platform SHALL 按以下业务域划分路由模块：价格分析、收入分析、投资分析、FCAS 分析、数据质量、芬兰市场、系统管理、外部 API
3. WHEN 路由模块拆分完成后，THE Platform SHALL 保持所有现有 API 端点的 URL 路径、请求参数和响应格式不变
4. THE Platform SHALL 将共享的数据库连接、缓存实例和认证中间件提取为独立的依赖注入模块
5. IF 任何路由模块加载失败，THEN THE Platform SHALL 记录错误日志并继续启动其余模块，同时在 /api/health 端点报告降级状态

### 需求 5：前端状态管理优化

**用户故事：** 作为平台开发者，我希望将 App.jsx 的集中式状态拆分为独立的状态管理单元，以便减少不必要的重渲染并提高前端可维护性。

#### 验收标准

1. THE Platform SHALL 将 Frontend_State 按业务域拆分为独立的状态管理模块（hooks 或 context）
2. THE Platform SHALL 确保各状态模块之间的更新互不触发无关组件的重渲染
3. WHEN 用户切换分析模块时，THE Platform SHALL 仅加载目标模块所需的状态数据，不加载其他模块的状态
4. THE Platform SHALL 保持拆分前后的用户交互行为和界面表现完全一致
5. THE Platform SHALL 将全局过滤条件（市场、区域、时间范围）作为共享状态模块，供所有分析模块订阅

### 需求 6：过滤条件全模块透传

**用户故事：** 作为储能投资分析师，我希望在顶部设置的过滤条件（市场、区域、时间范围）能自动应用到所有分析模块，以便获得一致的分析视角而无需重复设置。

#### 验收标准

1. WHEN 用户修改全局过滤条件时，THE Platform SHALL 将更新后的 Filter_Context 传递到所有活跃的分析模块
2. THE Platform SHALL 在每个分析模块的 API 请求中自动附加当前 Filter_Context 参数
3. WHEN 分析模块不支持某个过滤维度时，THE Platform SHALL 忽略该维度并在响应 metadata 中标注 ignored_filters 列表
4. THE Platform SHALL 在过滤条件变更后 2 秒内发起所有可见模块的数据刷新请求，并在各模块 API 响应返回后立即更新对应 UI
5. IF 过滤条件变更导致某模块无可用数据，THEN THE Platform SHALL 显示"当前筛选条件下无数据"提示而非空白或错误状态

### 需求 7：WEM ESS 数据同步管道连接

**用户故事：** 作为能源市场分析师，我希望 WEM ESS 数据管道能自动同步最新数据，以便在平台中获得完整的 WEM 辅助服务市场分析能力。

#### 验收标准

1. THE Data_Pipeline SHALL 按配置的调度周期自动从 WEM 数据源获取 ESS 市场数据
2. WHEN ESS 数据同步完成时，THE Data_Pipeline SHALL 更新数据库中的 ESS 价格和容量记录，并记录同步时间戳
3. THE Data_Pipeline SHALL 支持增量同步模式，仅获取上次同步时间戳之后的新数据
4. IF ESS 数据源不可用或返回错误，THEN THE Data_Pipeline SHALL 记录失败详情、保留上次成功同步的数据，并在下一调度周期重试
5. WHEN ESS 数据同步成功后，THE Platform SHALL 自动将 WEM ESS 模块的 data_completeness 状态从 "preview" 更新为 "complete"

### 需求 8：高分辨率 FCAS 全管道升级（4 秒 + 1 秒服务类型）

**用户故事：** 作为电力交易员，我希望 FCAS 分析能基于 4 秒分辨率数据并覆盖 RAISE1SEC/LOWER1SEC 服务类型，以便捕捉快速频率响应市场中的精确调度机会。

#### 验收标准

1. THE Data_Pipeline SHALL 支持获取和存储 4 秒分辨率的 FCAS 市场数据（AEMO 4-second FCAS data），并支持 RAISE1SEC/LOWER1SEC 服务类型的 5 分钟价格数据
2. THE Backtest_Engine SHALL 支持基于 4 秒分辨率数据运行 FCAS 调度回测
3. WHEN 用户选择高分辨率分析时，THE Platform SHALL 使用 4 秒数据进行计算并在 metadata 中标注 interval_seconds 为 4
4. WHILE 4 秒数据不可用时，THE Platform SHALL 回退到 5 分钟分辨率数据并在 metadata 中标注实际使用的分辨率
5. THE Data_Pipeline SHALL 对 4 秒数据实施数据压缩策略，保留最近 90 天的原始数据，超过 90 天的数据降采样为 1 分钟分辨率存储

### 需求 9：回测引擎约束强化

**用户故事：** 作为储能投资分析师，我希望回测引擎能正确建模所有物理和市场约束，以便获得更贴近实际运行的回测结果。

#### 验收标准

1. THE Backtest_Engine SHALL 在 MILP 模型中包含以下物理约束：最大充放电功率、最小 SOC、最大 SOC、循环效率损耗、辅助功耗
2. THE Backtest_Engine SHALL 在 MILP 模型中包含以下市场约束：最小持续时间要求、调度间隔对齐、市场注册容量上限
3. WHEN 回测结果中存在约束被激活的时段时，THE Backtest_Engine SHALL 在结果中标注 binding_constraints 列表及其激活时段
4. IF MILP 求解器在指定时间内未找到可行解，THEN THE Backtest_Engine SHALL 返回不可行状态并列出导致不可行的约束组合
5. THE Backtest_Engine SHALL 确保回测结果中的 SOC 轨迹在任意时刻满足 SOC_min ≤ SOC ≤ SOC_max 约束

### 需求 10：性能优化

**用户故事：** 作为平台用户，我希望分析请求能在合理时间内返回结果，以便保持流畅的分析工作流。

#### 验收标准

1. THE Platform SHALL 确保价格分析和收入分析 API 在 3 秒内返回结果（基于 1 年数据量、5 分钟分辨率）
2. THE Platform SHALL 确保投资分析 API 在 10 秒内返回结果（基于 20 年生命周期、含回测）
3. THE Platform SHALL 对重复请求实施 Redis 缓存策略，相同参数的请求在缓存有效期内直接返回缓存结果
4. WHEN 分析计算预计超过 5 秒时，THE Platform SHALL 将任务提交到后台作业队列并返回作业 ID 供客户端轮询
5. THE Platform SHALL 在 API 响应 metadata 中包含 computation_time_ms 字段，记录实际计算耗时

### 需求 11：测试体系完善

**用户故事：** 作为平台开发者，我希望建立完整的自动化测试体系，以便在持续迭代中保障代码质量和业务正确性。

#### 验收标准

1. THE Platform SHALL 为所有分析引擎建立单元测试，覆盖核心计算逻辑的正确性验证
2. THE Platform SHALL 为关键 API 端点建立集成测试，验证请求-响应契约的完整性
3. THE Platform SHALL 为 MILP 回测引擎建立属性测试（property-based test），验证 SOC 约束不变量和收入非负性
4. THE Platform SHALL 建立端到端测试，覆盖用户从登录到完成投资分析的完整流程
5. THE Platform SHALL 确保测试套件在 CI 环境中 5 分钟内完成执行

### 需求 12：数据库迁移评估

**用户故事：** 作为平台架构师，我希望评估从 SQLite 迁移到 PostgreSQL 的可行性和收益，以便为多用户并发访问和数据规模增长做好准备。

#### 验收标准

1. THE Platform SHALL 提供数据库抽象层，使业务逻辑不直接依赖特定数据库驱动的 SQL 方言
2. THE Platform SHALL 支持通过环境变量切换 SQLite 和 PostgreSQL 后端，无需修改业务代码
3. WHEN 使用 PostgreSQL 后端时，THE Platform SHALL 支持连接池管理，配置最大连接数和连接超时
4. THE Platform SHALL 提供数据迁移脚本，支持将现有 SQLite 数据完整迁移到 PostgreSQL
5. IF 数据库连接失败，THEN THE Platform SHALL 在 30 秒内进行最多 3 次重连尝试，并在所有重试失败后返回服务不可用状态

### 需求 13：CI/CD 管道建设

**用户故事：** 作为平台开发者，我希望建立自动化的 CI/CD 管道，以便每次代码变更都能自动验证质量并支持一键部署。

#### 验收标准

1. WHEN 代码推送到版本控制仓库时，THE Platform SHALL 自动触发 CI 管道执行代码检查、测试和构建
2. THE Platform SHALL 在 CI 管道中执行以下检查：Python 类型检查、ESLint 前端检查、单元测试、集成测试
3. WHEN CI 管道中任何检查失败时，THE Platform SHALL 阻止代码合并并通知提交者失败原因
4. THE Platform SHALL 支持通过 CI 管道自动构建 Docker 镜像并推送到容器注册表
5. THE Platform SHALL 提供部署脚本，支持将构建产物部署到目标环境（开发/预发布/生产）
