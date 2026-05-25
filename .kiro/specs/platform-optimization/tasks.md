# Implementation Plan: Platform Optimization

## Overview

本实现计划将 AEMO Intelligence 平台优化分为四个阶段执行：业务正确性修复、架构重构、数据管道完善、商业化准备。每个阶段的任务按依赖关系排列，确保增量交付和持续验证。后端使用 Python 3.11 + FastAPI，前端使用 React 19 + Vite 8，属性测试使用 Hypothesis。

## Tasks

- [x] 1. Phase 1: 业务正确性 — 核心引擎与数据模型
  - [x] 1.1 创建 PriceAnalysisEngine 和 RevenueAnalysisEngine
    - 在 `backend/engines/` 下新建 `price_analysis_engine.py`
    - 实现 `PriceAnalysisEngine.analyze()` 方法：接收价格时间序列，返回 $/MWh 统计结果（mean, median, p25, p75, max, min, 分布直方图）
    - 实现 `PriceAnalysisResult` Pydantic 模型，metadata.unit 固定为 "$/MWh"
    - 在 `backend/engines/` 下新建 `revenue_analysis_engine.py`
    - 实现 `RevenueAnalysisEngine.calculate()` 方法：接收价格序列 + 电池参数（power_mw, energy_mwh, round_trip_efficiency, degradation_rate, network_fee_per_mwh），返回 $ 收入结果
    - 实现 `RevenueAnalysisResult` Pydantic 模型，metadata.unit 固定为 "$"
    - 实现 `validate_input_dimensions()` 方法：检测 metadata.unit=="$/MWh" 时抛出 `DimensionMismatchError`
    - 新建 `backend/engines/exceptions.py` 定义 `DimensionMismatchError`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
    - _Design: PriceAnalysisEngine, RevenueAnalysisEngine, AnalysisMetadata_

  - [x]* 1.2 编写 Property 1-3 属性测试（价格/收入维度不变量）
    - 新建 `tests/test_price_revenue_properties.py`
    - **Property 1: 价格分析维度不变量** — 随机价格序列 + 随机电池参数，验证 PriceAnalysisEngine 输出不受电池参数影响且 unit=="$/MWh"
    - **Property 2: 收入计算维度正确性** — 随机价格 + 随机容量，验证 unit=="$" 且收入与容量单调递增
    - **Property 3: 维度不匹配拒绝** — 随机 $/MWh 标记数据传入 RevenueAnalysisEngine 时抛出 DimensionMismatchError
    - 使用 `@settings(max_examples=200)` 配置
    - 标注格式: `Feature: platform-optimization, Property N: ...`
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

  - [x] 1.3 实现 DegradationModel 和投资模型衰减率集成
    - 在 `backend/engines/` 下新建 `degradation_model.py`
    - 实现 `DegradationModel` Pydantic 模型：支持 "user-linear" 和 "dual-factor-default" 两种模式
    - 实现 `from_user_input(degradation_rate)` 工厂方法：有效范围 0-0.15，超出抛出 ValueError
    - 实现 `capacity_at_year(year, cycles_per_year)` 方法
    - 修改 `backend/models/financial_params.py` 中的 `InvestmentParams`，增加 `degradation_rate: float | None = None` 字段
    - 修改投资分析计算逻辑，优先使用用户 degradation_rate，回退到双因子模型
    - 在投资分析响应中增加 `degradation_model` 字段
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
    - _Design: DegradationModel, InvestmentAnalysisResponse_

  - [x]* 1.4 编写 Property 4 属性测试（衰减模型一致性）
    - 新建 `tests/test_degradation_properties.py`
    - **Property 4: 衰减模型一致性** — 随机 float [0, 0.15] 验证 model_type=="user-linear" 且 annual_rate==输入值；越界值验证抛出 ValueError
    - 使用 Hypothesis `st.floats(min_value=0, max_value=0.15)` 和越界策略
    - **Validates: Requirements 2.1, 2.2, 2.4, 2.5**

  - [x] 1.5 实现 WEM 数据完整性标注机制
    - 新建 `backend/data_completeness.py`，定义 `DataCompletenessStatus` 模型
    - 实现 `get_module_completeness(module: str, db: DatabaseManager)` 函数
    - 修改现有 WEM 相关 API 响应，在 metadata 中增加 `data_completeness` 字段
    - 前端：在 WEM 相关组件中添加数据完整性标注 UI（Badge 组件显示 "完整数据" / "预览 — ESS 管道未连接" / "预览 — FCAS 数据有限"）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
    - _Design: DataCompletenessStatus_

  - [x]* 1.6 编写 Phase 1 单元测试
    - 新建 `tests/test_price_analysis_engine.py`：测试统计计算正确性（均值、中位数、分位数）
    - 新建 `tests/test_revenue_analysis_engine.py`：测试收入计算公式验证
    - 新建 `tests/test_degradation_model.py`：测试各年容量衰减计算、边界条件
    - _Requirements: 11.1_

- [x] 2. Phase 1 检查点
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Phase 2: 架构重构 — 后端路由模块化
  - [x] 3.1 创建依赖注入模块 deps.py
    - 新建 `backend/deps.py`
    - 实现 `get_db()`, `get_cache()`, `get_job_orchestrator()` 单例工厂函数
    - 实现 FastAPI `Depends` 注入函数：`db_dependency()`, `cache_dependency()`
    - 从 `server.py` 提取共享实例初始化逻辑到 deps.py
    - _Requirements: 4.4_
    - _Design: deps.py 依赖注入模块_

  - [x] 3.2 创建路由模块目录结构和注册器
    - 新建 `backend/routes/__init__.py`，实现 `register_all_routes(app)` 函数
    - 实现模块加载失败的降级处理：单个模块失败不影响其他模块启动
    - 在 `/api/health` 端点报告降级模块列表
    - _Requirements: 4.5_
    - _Design: 路由注册器_

  - [x] 3.3 拆分 price_routes.py 和 revenue_routes.py
    - 新建 `backend/routes/price_routes.py`：从 server.py 迁移价格分析相关端点
    - 新建 `backend/routes/revenue_routes.py`：从 server.py 迁移收入分析相关端点
    - 集成 Phase 1 新建的 PriceAnalysisEngine 和 RevenueAnalysisEngine
    - 使用 deps.py 注入依赖
    - 保持 URL 路径、请求参数、响应格式不变
    - _Requirements: 4.1, 4.2, 4.3_
    - _Design: price_routes.py, revenue_routes.py_

  - [x] 3.4 拆分 investment_routes.py 和 fcas_routes.py
    - 新建 `backend/routes/investment_routes.py`：迁移投资分析端点，集成 DegradationModel
    - 新建 `backend/routes/fcas_routes.py`：迁移 FCAS 分析端点
    - 使用 deps.py 注入依赖
    - 保持 API 契约不变
    - _Requirements: 4.1, 4.2, 4.3_
    - _Design: investment_routes.py, fcas_routes.py_

  - [x] 3.5 拆分 data_quality_routes.py, finland_routes.py, admin_routes.py, external_api_routes.py
    - 新建 `backend/routes/data_quality_routes.py`：迁移数据质量相关端点
    - 新建 `backend/routes/finland_routes.py`：迁移芬兰市场相关端点
    - 新建 `backend/routes/admin_routes.py`：迁移系统管理端点（health, observability, jobs 等）
    - 新建 `backend/routes/external_api_routes.py`：迁移外部 API 端点
    - _Requirements: 4.1, 4.2_
    - _Design: 路由模块化拆分策略_

  - [x] 3.6 精简 server.py 为 app 入口
    - 将 server.py 精简为 < 200 行的应用入口
    - 保留 lifespan、中间件配置、CORS 设置
    - 调用 `register_all_routes(app)` 注册所有路由
    - 验证所有现有 API 端点仍可正常访问
    - _Requirements: 4.1, 4.3_

  - [x]* 3.7 编写 Property 10 属性测试（API 契约向后兼容）
    - 新建 `tests/test_api_contract_properties.py`
    - **Property 10: API 契约向后兼容** — 随机有效 API 请求参数，验证拆分前后返回相同结构响应（HTTP 状态码、JSON 字段集合、数据类型）
    - 使用 Hypothesis 生成随机查询参数组合
    - **Validates: Requirements 4.3**

- [x] 4. Phase 2: 架构重构 — 前端状态管理
  - [x] 4.1 创建 FilterContext 和 useFilters hook
    - 新建 `web/src/contexts/FilterContext.jsx`
    - 实现 `FilterProvider` 组件：使用 useReducer 管理 market, region, year, quarter, dayType, months
    - 实现 `useFilters()` hook
    - 在 App.jsx 中包裹 FilterProvider
    - _Requirements: 5.5, 6.1_
    - _Design: FilterContext (前端)_

  - [x] 4.2 拆分业务域状态 hooks
    - 新建 `web/src/hooks/usePriceAnalysis.js`：价格分析状态和 API 调用
    - 新建 `web/src/hooks/useRevenueAnalysis.js`：收入分析状态和 API 调用
    - 新建 `web/src/hooks/useFcasAnalysis.js`：FCAS 分析状态和 API 调用
    - 新建 `web/src/hooks/useInvestment.js`：投资分析状态和 API 调用
    - 新建 `web/src/hooks/useGridForecast.js`：电网预测状态和 API 调用
    - 每个 hook 订阅 FilterContext，过滤条件变更时自动重新请求
    - _Requirements: 5.1, 5.2, 5.3, 6.2_
    - _Design: 前端状态管理重构_

  - [x] 4.3 重构 App.jsx 为布局组件
    - 将 App.jsx 精简为布局和路由组件
    - 移除集中式 useState，改用各业务 hooks
    - 确保用户交互行为和界面表现不变
    - 验证各模块更新互不触发无关组件重渲染
    - 更新 `RevenueStacking.jsx` 组件：调用新的分离 API（价格分析和收入分析分别请求），移除价格/收入混合叠加逻辑
    - _Requirements: 5.1, 5.2, 5.4, 1.1_

  - [x]* 4.4 编写 Property 7 属性测试（过滤条件传播一致性）
    - 新建 `tests/test_filter_properties.py`
    - **Property 7: 过滤条件传播一致性** — 随机 FilterContext + 随机模块集，验证 API 请求包含所有支持维度参数，不支持的维度在 ignored_filters 中列出
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 4.5 实现过滤条件无数据提示和刷新时限
    - 当过滤条件变更导致无数据时，显示"当前筛选条件下无数据"提示
    - 确保过滤条件变更后 2 秒内完成所有可见模块的数据刷新
    - _Requirements: 6.4, 6.5_

- [x] 5. Phase 2 检查点
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Phase 3: 数据管道 — WEM ESS 同步与 FCAS 升级
  - [x] 6.1 实现 WemEssSyncJob 数据同步作业
    - 新建 `backend/pipelines/wem_ess_sync.py`
    - 实现 `WemEssSyncJob` 类：增量同步 WEM ESS 数据
    - 实现 `run(context)` 方法：获取 last_sync_timestamp → 拉取增量数据 → upsert → 更新时间戳
    - 实现失败处理：记录失败详情、保留旧数据、下次重试
    - 同步成功后自动更新 data_completeness 状态为 "complete"
    - 在 JobOrchestrator 中注册 WEM ESS 同步作业，配置 APScheduler cron 调度
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
    - _Design: WemEssSyncJob_

  - [x] 6.2 实现 4 秒 FCAS 数据获取和存储
    - 新建 `backend/pipelines/fcas_4s_ingest.py`
    - 实现 4 秒分辨率 FCAS 数据的获取和批量写入（AEMO 4-second FCAS data）
    - 扩展 FCAS_SERVICES 列表支持 RAISE1SEC/LOWER1SEC 服务类型（5 分钟价格数据）
    - 在 DatabaseManager 中增加 `fetch_fcas_4s_before()` 和 `replace_fcas_records()` 方法
    - 实现数据分辨率回退逻辑：4s → 5min
    - 修改 FCAS 分析 API，支持 interval_seconds=4 参数，metadata 标注实际使用分辨率
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
    - _Design: FCAS 4-Second Data Pipeline_

  - [x] 6.3 实现 FcasDataCompressor 数据压缩策略
    - 新建 `backend/pipelines/fcas_compressor.py`
    - 实现 `FcasDataCompressor` 类：90 天内保留 4 秒原始数据，超过 90 天降采样为 1 分钟
    - 实现 `_downsample()` 方法：按 1 分钟窗口取均值
    - 注册为定期作业（每日执行）
    - _Requirements: 8.5_
    - _Design: FcasDataCompressor_

  - [x]* 6.4 编写 Property 8-9 属性测试（数据分辨率与压缩）
    - 新建 `tests/test_fcas_resolution_properties.py`
    - **Property 8: 数据分辨率回退正确性** — 随机数据可用性状态，验证回退到正确分辨率（4s → 5min）且 metadata 反映实际分辨率
    - **Property 9: 数据压缩保留策略** — 随机时间戳分布的 4 秒数据，验证 90 天内不变、90 天外降采样为 1 分钟、数据点约为 1/15
    - **Validates: Requirements 8.3, 8.4, 8.5**

  - [x] 6.5 实现 BacktestConstraints 和 bess_backtest_v2
    - 新建 `backend/engines/bess_backtest_v2.py`
    - 实现 `BacktestConstraints` dataclass：物理约束（max_charge/discharge, SOC 边界, 循环效率, 辅助功耗）+ 市场约束（最小持续时间, 调度间隔对齐, 注册容量上限）
    - 实现 `validate()` 方法：检测约束冲突
    - 实现 MILP 模型构建：使用 PuLP 添加所有约束变量和约束条件
    - 实现 `BacktestV2Result` 和 `BindingConstraintRecord` 模型
    - 在结果中标注 binding_constraints 列表
    - 处理不可行解：返回 infeasible 状态 + 约束冲突列表
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
    - _Design: BacktestConstraints, BacktestV2Result_

  - [x]* 6.6 编写 Property 5-6 属性测试（SOC 边界与收入非负性）
    - 新建 `tests/test_backtest_properties.py`
    - **Property 5: SOC 边界不变量** — 随机电池参数 + 随机价格序列，验证 timeline 中每时刻 soc_mwh 满足 SOC_min ≤ soc ≤ SOC_max
    - **Property 6: 回测收入非负性** — 含正价差的随机价格序列 + 有效电池参数 + 终端 SOC 约束，验证 net_revenue ≥ 0（优化器可选择不操作）
    - **Validates: Requirements 9.1, 9.2, 9.5**

- [x] 7. Phase 3 检查点
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Phase 4: 商业化准备 — 性能优化与测试体系
  - [x] 8.1 实现 Redis 缓存策略和异步作业提交
    - 在各路由模块中集成 `RedisResponseCache`：相同参数请求在 TTL 内返回缓存结果
    - 实现计算超时检测：预计超过 5 秒的任务提交到 JobOrchestrator，返回 job_id
    - 在所有分析响应 metadata 中增加 `computation_time_ms` 字段
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
    - _Design: 性能优化策略_

  - [x]* 8.2 编写性能基准测试
    - 新建 `tests/test_performance_benchmarks.py`
    - 使用 pytest-benchmark 验证：price-trend < 3s, revenue-analysis < 3s, investment-analysis < 10s, fcas-analysis (1s) < 5s
    - 基于 1 年 5 分钟分辨率数据量
    - _Requirements: 10.1, 10.2_

  - [x] 8.3 建立集成测试套件
    - 新建 `tests/test_api_integration.py`
    - 测试路由模块拆分后所有 API 端点可达性
    - 测试过滤条件端到端传递
    - 测试 Redis 缓存命中/未命中路径
    - 测试作业队列提交和结果轮询
    - 测试路由模块加载失败的降级行为
    - _Requirements: 11.2_

  - [x]* 8.4 建立 E2E 测试（Playwright）
    - 新建 `tests/e2e/` 目录
    - 测试流程 1：登录 → 选择市场/区域 → 查看价格分析 → 切换收入分析
    - 测试流程 2：修改全局过滤条件 → 验证所有模块刷新
    - 测试流程 3：运行投资分析（含自定义衰减率）→ 验证衰减模型信息
    - 测试流程 4：WEM 市场页面 → 验证数据完整性标注
    - _Requirements: 11.4_

  - [x] 8.5 实现数据库抽象层增强
    - 修改 `backend/database.py` 的 DatabaseManager，确保业务逻辑不依赖 SQLite 方言
    - 支持通过 `AUS_ELE_DB_BACKEND` 环境变量切换 SQLite/PostgreSQL
    - 实现 PostgreSQL 连接池管理（最大连接数、超时配置）
    - 实现重连逻辑：30 秒内最多 3 次重试
    - 注意：此任务的详细设计待单独补充，当前按需求 12 的验收标准实现
    - _Requirements: 12.1, 12.2, 12.3, 12.5_

  - [x]* 8.6 编写数据迁移脚本
    - 新建 `scripts/migrate_sqlite_to_pg.py`
    - 实现 SQLite → PostgreSQL 完整数据迁移
    - 支持表结构映射和数据类型转换
    - 注意：此任务的详细设计待单独补充
    - _Requirements: 12.4_

  - [x] 8.7 建立 CI/CD 管道配置
    - 新建 `.github/workflows/ci.yml`（或等效 CI 配置）
    - 配置：Python 类型检查（mypy）、ESLint 前端检查、单元测试、集成测试
    - 配置 Docker 镜像自动构建和推送
    - 新建 `scripts/deploy.sh` 部署脚本
    - 确保测试套件 5 分钟内完成
    - 注意：此任务的详细设计待单独补充
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 11.5_

- [x] 9. 最终检查点
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP 交付
- 每个任务引用具体需求编号和设计组件，确保可追溯性
- 检查点确保增量验证，避免问题累积
- 属性测试使用 Hypothesis 库，每个属性最少 200 次迭代
- 路由模块拆分需保持 API 契约完全向后兼容
- 前端重构需保持用户交互行为和界面表现不变
- Phase 1-2 可部分并行（引擎开发与路由拆分独立），Phase 3 依赖 Phase 2 的路由结构

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "3.2"] },
    { "id": 2, "tasks": ["1.4", "1.5", "3.3", "4.1"] },
    { "id": 3, "tasks": ["1.6", "3.4", "4.2"] },
    { "id": 4, "tasks": ["3.5", "4.3"] },
    { "id": 5, "tasks": ["3.6", "4.4", "4.5"] },
    { "id": 6, "tasks": ["3.7", "6.1", "6.2"] },
    { "id": 7, "tasks": ["6.3", "6.5"] },
    { "id": 8, "tasks": ["6.4", "6.6"] },
    { "id": 9, "tasks": ["8.1", "8.5"] },
    { "id": 10, "tasks": ["8.2", "8.3", "8.6"] },
    { "id": 11, "tasks": ["8.4", "8.7"] }
  ]
}
```
