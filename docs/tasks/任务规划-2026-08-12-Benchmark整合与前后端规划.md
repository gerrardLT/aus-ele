# 任务规划-2026-08-12-Benchmark整合与前后端规划

状态：已实施（2026-08-12 三期全部完成，待提交）

依据：
- [调研-竞品动态与BESS收益基准-关键词多轮深度调研-2026-08-12.md](../research/调研-竞品动态与BESS收益基准-关键词多轮深度调研-2026-08-12.md)
- 用户决策（2026-08-12）：① 先写入规划文档再实施；② Benchmark **仅作为 Agent 对话工具**呈现，不新增独立 UI

---

## 1. 目标

把调研结论中的 P0/P1 能力缺口落进现有系统，原则：
- 复用既有引擎与数据，不新建数据管线
- 新增能力以"新 engine + 新 route + Agent 工具"的加法方式接入，不动存量主链
- 每个输出一律带 P4 治理 metadata（source/freshness/data_grade/coverage_mode）

---

## 2. 可复用资产盘点（2026-08-12 代码现状）

| 资产 | 位置 | 复用用途 |
|---|---|---|
| RevenueAnalysisEngine | `backend/engines/revenue_analysis_engine.py` | benchmark 月度指数的收益口径计算（价格序列+电池参数→$） |
| fcas_collapse_engine | `backend/engines/fcas_collapse_engine.py` | FCAS 压缩风险标签（Phase 2 直接接线） |
| merchant_risk_engine | `backend/engines/merchant_risk_engine.py` | "项目 vs 市场"对照的风险分层 |
| financial_model + tax_model | `backend/engines/` | CIS 收益桶扩展（Phase 3） |
| NEM 结算价 / FCAS 10 价格 / WEM ESS 5 服务 | 数据库既有表 | benchmark 数据基础，无需新爬虫 |
| agent_routes 工具注册机制 | `backend/routes/agent_routes.py` | benchmark 以工具形式暴露 |
| AgentPage KpiCard | `web/src/pages/AgentPage.jsx` | 工具结果自动提取 KPI，无需前端改动 |
| data_completeness | `backend/data_completeness.py` | benchmark 缺月告警 |

---

## 3. 分期实施计划

### Phase 1：NEM BESS 收益 Benchmark（仅 Agent 工具）

**后端**：
1. 新建 `backend/engines/benchmark_engine.py`
   - 输入：region、months（默认滚动 12 个月）、电池参考参数（默认 100MW/200MWh、RTE 0.85，与 Modo 参考资产同量级）
   - 计算：月度结算价序列 → RevenueAnalysisEngine 理想套利口径 → `$k/MW/年` 月度指数
   - 输出：月度序列、区域对比、当前月 vs 12 月均值、`FCAS revenue compression` 提示（引用 FCAS 占比事实）
   - metadata：`data_grade=derived`、`coverage_mode=arbitrage-only, FCAS not included`、`source_name=AEMO settlement`、`freshness_ts`
2. 新建 `backend/routes/benchmark_routes.py`
   - `GET /api/benchmark/nem-bess-index?region=NSW1&months=12`（供外部 API 与 Agent 共用）
   - 注册入 `routes/__init__.py`
3. Agent 工具注册：在 agent_routes 工具清单新增 `bess_revenue_benchmark`，工具描述明确口径与 caveat

**前端**：无改动（AgentPage 现有 KPI 提取与工具结果渲染即可承载）。

**验收**：
- API 返回 2025-08 ~ 2026-07 的 NSW1/QLD1/SA1/VIC1 月度指数，缺月有告警字段
- Agent 对话"当前市场基准收益如何"能调用该工具并产出 KPI 卡
- 数值与调研数据交叉验证：方向上应体现 2026 年收益压缩趋势（与 Modo $148k→$29k 同向，绝对值因口径差异偏低且已标注）

### Phase 2：FCAS 压缩适配与统一风险标签

1. `investment_routes` / `revenue_routes` 响应接入 `fcas_collapse_engine` 输出 → `fcas_revenue_compression` 风险标签 + 当前 FCAS 收益占比
2. 投资分析下调 FCAS 默认权重假设（显式参数化，不再隐藏）
3. Agent 工具 `investment_analysis` 的 KPI/文本输出补充压缩提示

**验收**：投资分析响应含风险标签字段；Agent 投资分析结论中出现 FCAS 压缩 caveat。

### Phase 3：CIS 收益桶 + WEM BRCP 锚

1. `financial_model` 新增 `cis_floor_value` 独立 value stream（输入：CIS 投标参数，JSON 配置先行，不建爬虫）
2. WEM 容量收益引入 ERA BRCP 年度锚（200MW/1200MWh 官方口径，人工配置年度更新）
3. Agent 工具 `investment_analysis` 支持 `include_cis=true` 参数

**验收**：带 CIS 的投资测算能输出 floor 前后 NPV 对照；WEM 收益口径含 BRCP caveat。

---

## 4. 明确不做

- 不做独立 Benchmark 页面/tab（用户已决策：仅 Agent 工具）
- 不做 CIS/BRCP 自动爬虫（低频数据，配置化维护）
- 不碰执行端投标能力（竞品红海，见调研 §1.4）

---

## 5. 风险与口径约定

| 风险 | 处置 |
|---|---|
| 理想套利口径系统性低于 Modo 实际收益指数 | 输出强制带 `data_grade=derived` 与口径说明，禁止与 Modo 绝对值直接对比 |
| 结算数据缺月导致指数失真 | 复用 data_completeness，响应中带 completeness 字段与告警 |
| Agent 工具描述不清导致误用 | 工具 description 写明：参考资产参数、覆盖价值流、不适用于执行决策 |

---

## 6. 实施记录

### Phase 1 — 已完成（2026-08-12）

新增/修改：
- 新建 `backend/engines/benchmark_engine.py`：滚动月度基准指数（理想日内循环套利口径：每日最高/最低价各取电池时长对应时段充放，粒度从数据推断，无利日不循环），完整月阈值 95%，跨分年表容错
- 新建 `backend/routes/benchmark_routes.py`：`GET /api/benchmark/nem-bess-index`、`/api/benchmark/nem-bess-region-compare`、`/api/benchmark/wem-brcp-anchor`；P4 metadata（data_grade=derived）+ 6h 响应缓存
- `agent/tools.py`：新工具 `bess_revenue_benchmark`（Stage 2），`tool_profiles` 接入 stage2_revenue/stage6_financial + 关键词路由，`prompts.py` 标签，`orchestrator.py` 推理叙事
- `web/src/pages/AgentPage.jsx`：extractKpis 新增基准收益 KPI 卡
- 新建 `tests/test_benchmark_engine.py`：13 用例全绿

实施中的口径修正（相对规划的偏差）：
1. 验收发现初版"正价满放"口径高估约 100 倍，改为理想日内循环套利（充电成本显式建模）
2. 库内价格为 5 分钟粒度（非 30 分钟结算），时间粒度与完整性分母改为从数据推断

真实数据验收（NSW1，滚动 12 个月）：2025-11 峰值 297 → 2026-06 50 kAUD/MW/年，与 Modo 同期 $44k→$29k 创新低同向；2026-07 不完整月被正确排除。

### Phase 2 — 已完成（2026-08-12）

- 新建 `backend/services/fcas_compression.py`：`fcas_revenue_compression` 风险标签（10 分钟缓存，失败降级）
- `investment_routes` / `revenue_routes` 响应挂 `fcas_compression` 字段
- Agent `investment_analysis`：FCAS 基线显式乘压缩因子 0.3（`fcas_compression_factor` 随输出暴露），叙事层补充压缩提示
- 真实验证：severity=high，10/10 FCAS 服务 collapsed，天花板 0 kAUD/MW/年——与调研"FCAS 枯竭"一致

### Phase 3 — 已完成（2026-08-12）

- 新建 `data/contract_revenue_defaults.json`（CIS floor 示例锚点 75,000 AUD/MW/年 + WEM BRCP 2026/27 占位 11,500，人工年度更新）
- 新建 `backend/services/contract_revenue.py`：CIS/BRCP 配置读取 + caveat
- Agent `investment_analysis` 新增 `include_cis` 参数：floor 高于 merchant 基线时抬升套利桶重算，输出 floor 前后 NPV 对照；orchestrator 叙事同步
- `/api/benchmark/wem-brcp-anchor` 端点
- 端到端验证：NSW1 2026 基线已高于 floor（binding=false，逻辑正确）；BRCP 锚点返回带 caveat

### 回归与构建

- `tests/test_benchmark_engine.py` 13/13、`test_revenue_analysis_engine.py`、`test_agent_golden_trajectories.py`（profile 子集）、`test_fcas_collapse_property.py`、`test_investment_architecture.py`、`test_fcas_compressor.py` 全绿（合计 65+ 用例）
- 前端 `vite build` 通过

### 待办（后续任务）

- CIS floor / BRCP 占位值待官方数据替换（配置化，改 JSON 即可）
- 生产部署后在 Agent 页验收 benchmark KPI 卡与工具调用链路
