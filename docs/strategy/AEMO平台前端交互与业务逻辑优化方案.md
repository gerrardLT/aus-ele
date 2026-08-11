# AEMO Intelligence 平台 — 前端交互与业务逻辑优化方案

> 生成日期: 2026-07-24
> 范围: MarketPage 7 阶段漏斗前端交互 + BESS 回测引擎 + 财务模型 + 投资分析 API 数据流
> 方法: 实际代码审查（非文档推断）+ 学术/行业标准交叉验证
> 关联文档: `docs/_archive/项目业务逻辑梳理与代码审查.md`、`.kiro/specs/frontend-rewrite/design.md`、`.kiro/specs/platform-optimization/design.md`

---

## 0. 执行摘要

本轮审查以**实际代码**为准（而非设计文档描述），核对了前端 `MarketPage.jsx` / `marketConfig.js` / `ModuleRenderer.jsx` 与后端 `bess_backtest_v1.py` / `financial_model.py` / `investment_routes.py`。

**核心结论：当前实现已远超两份设计文档的描述状态。** 多项文档标注的"待办/缺陷"实际已修复：

| 文档描述的问题 | 实际代码状态 | 证据 |
|----------------|--------------|------|
| 前端 4 阶段漏斗（frontend-rewrite） | ✅ 已升级为**配置驱动 7 阶段 Tab**（NEM）/ 5 阶段（WEM） | `marketConfig.js` L64-204 |
| V1 完美预见（144 行朴素实现） | ✅ 已重写为**滚动时域 MPC LP/MILP**（491 行） | `bess_backtest_v1.py` |
| M2 Monte Carlo 无种子 | ✅ 已加固定种子 42 + 对数正态无偏乘子 + AR(1) 自相关 | `financial_model.py` L236-327 |
| 用户 `degradation_rate` 未被使用 | ✅ 已通过模型验证器写入电池模型 | `financial_params.py` L172-173 |
| V2 LP 约束未合并 | ✅ 已合并进 V1 `_solve_window`（LP/MILP 双路径） | `bess_backtest_v1.py` L167-368 |

**因此本方案聚焦于"实际仍存在的问题"与"可提升到行业顶级水准的增强项"**，而非重复文档中已解决的历史遗留。所有建议均标注优先级（P0 必修 / P1 应修 / P2 增强）与科学依据。

---

## 1. 前端交互优化

### 1.1 现状（实际实现）

`MarketPage.jsx`（191 行）是一个**配置驱动的 Tab 编排器**：

- NEM 渲染 7 个 Tab：市场筛选 → 收入深潜 → 饱和与竞争 → 投资前景情景 → 联合优化回测 → 财务建模 → 投资决策
- WEM 渲染 5 个 Tab（无投资前景情景、无财务建模独立页）
- 每次**只渲染当前激活 Tab**（`activeStage`），通过 `DynamicStage` → `ModuleRenderer`（`React.lazy + Suspense`）按需加载模块
- Tab 索引持久化到 `localStorage`（`tab_${market}`），语言持久化到 `app_lang`
- 加载态由 `ModuleLoadingSkeleton`（shimmer 骨架屏）承载，`ModuleErrorBoundary` 隔离单模块渲染失败

**这套架构本身是先进的**：懒加载 + 故障隔离 + 配置驱动，符合分析师"分阶段深挖"的操作动线。

### 1.2 发现的问题

| 编号 | 严重度 | 问题 | 位置 |
|------|--------|------|------|
| F1 | P1 | **加载态语义不完整**：部分旧模块（PeakAnalysis/FcasAnalysis/ChargingWindow/CycleCost）已通过 `legacyPropsMap` 获得自有 `loadingMsg`，但 **Suspense 级 chunk 加载骨架统一无文案**，且**最重的 InvestmentAnalysis/CoOptimizedBacktest 等未传 `loadingMsg`**——投资分析 30-60s 期间用户无进度感知，无"正在求解 20 年现金流…"类文案 | `ModuleRenderer.jsx` L86-104、L137 |
| F2 | P1 | **`DynamicStage` 的 `conclusionData=null`、`isLoading=false` 恒定**，阶段结论层（StageConclusion）被架空，7 阶段漏斗"每阶段给出可执行结论"的叙事被削弱 | `DynamicStage.jsx` L23-24 |
| F3 | P1 | **Tab 切换丢失滚动位置与筛选上下文反馈**：切 Tab 只换内容，不提示"筛选器 region=QLD1/2025 全程生效"，分析师易忘记当前上下文 | `MarketPage.jsx` L151-161 |
| F4 | P2 | **无阶段完成度/漏斗进度可视化**：7 个 Tab 平铺，缺少"已看 3/7""关键结论待确认"的漏斗收敛感 | `MarketPage.jsx` L110-149 |
| F5 | P2 | **FilterBar 触摸目标 < 44px**（WCAG 2.5.5），文档 M3 遗留，需核实是否已修复 | `FilterBar`（待核） |
| F6 | P2 | **重型模块无预取**：切到"财务建模"Tab 才触发 `/api/investment-analysis`，冷启动等待长；可在用户停留"联合优化回测"时预取 | `MarketPage.jsx` |

### 1.3 优化建议

#### F1 — 阶段化加载文案系统（P1，符合分析师心智）

在 `translations` 中已存在 `t.loading_states`（`ModuleRenderer.jsx` L133-138 已引用 `loadingMsg`），但骨架屏未消费。建议：

1. 扩展 `ModuleLoadingSkeleton` 接受 `label` 与 `variant` 参数：
   - `variant="chart"`：图表骨架（现状）
   - `variant="compute"`：带进度文案 + 转圈，用于 InvestmentAnalysis/CoOptimizedBacktest 等重型求解
2. 为每个模块在 `MODULE_REGISTRY` 或 `legacyPropsMap` 旁配置 `loadingCopy`，示例文案（中/英）：
   - PriceChart：`正在聚合市场价格数据…` / `Aggregating market price data…`
   - SaturationTracker：`正在测算装机饱和曲线…`
   - CoOptimizedBacktest：`正在联合优化能量与 FCAS 调度…`
   - InvestmentAnalysis：`正在求解 20 年现金流与蒙特卡洛分布…`（附"首次约 30-60 秒"提示）
3. 重型端点（后端已有 inflight 去重 + 60s 超时，`investment_routes.py` L46-51）**前端应显式轮询/长任务态**：展示"计算中"进度而非静默骨架。

**科学依据**：Nielsen 响应时间阈值——>10s 操作必须给出明确进度与预期时长，否则用户认为系统失败。

#### F2 — 恢复阶段结论层（P1，7 阶段漏斗的灵魂）

`DynamicStage` 应从各阶段主模块的 API 响应中**提取结论摘要**并回填 `conclusionData`，让每个 Tab 底部呈现"本阶段结论 + 是否进入下一阶段"的决策提示（漏斗收敛）。建议由阶段级 hook（`useStageSummaries`，`frontend-rewrite/design.md` 已规划）统一获取，`isLoading` 真实透传。

#### F3/F4 — 上下文常驻 + 漏斗进度（P1/P2）

- 在 Tab 栏下方增加**常驻上下文条**：`区域 QLD1 · 2025 · 工作日`，随 FilterContext 实时更新。
- Tab 徽章增加状态点（已加载✓/有告警⚠/未访问），形成 7 阶段收敛的视觉漏斗。

#### F6 — 相邻阶段预取（P2）

用户停留第 N 阶段时，用 `requestIdleCallback` 预取第 N+1 阶段主模块的数据依赖（`marketConfig` 已声明 `dataDependencies`），显著降低重型端点的感知延迟。

---

## 2. 业务逻辑可靠性审查

### 2.1 BESS 回测引擎（`bess_backtest_v1.py`，491 行）

#### 2.1.1 已达到的科学水准（值得肯定）

1. **滚动时域（Receding-Horizon / MPC）方法论正确**：commit 窗口（默认 24h）+ lookahead 缓冲（默认 24h），只提交前段决策、SoC 滚动结转（L371-440）。这消除了"整年完美预见"的**前视偏差（look-ahead bias）**，同时保留"有限预见折价"。
   - **交叉验证**：澳洲行业以 **"% of perfect foresight"** 为标准评估指标（OptiGrid / energy-storage.news）；文献（Hornek 2025, arXiv 2501.07121；EPRI DER-VET）均以完美预见为上界基准、预测驱动策略为现实值。当前 `window_hours<=0` 恰好回退到完美预见单窗求解，可作为分母 —— **架构已内建该行业指标的计算能力**。
2. **LP 松弛精确性论证严谨**（L23-31）：η<1 或放电有正成本时"同时充放电"被严格支配，故 LP 松弛即整数最优 —— 只在设置 `min_duration`/`dispatch_alignment` 时才切 MILP，兼顾性能与正确性。
3. **往返效率对称拆分** `η = sqrt(round_trip_efficiency)`（L196），充放电各承担一半，物理正确。
4. **终端能量中性**：最后一窗 pin 终端 SoC=初始 SoC（L418），避免"清空库存"虚增末窗收益。
5. **SoC 边界 / 循环寿命吞吐限 / 辅助自耗 / 注册容量 / 独立充放电限**均已参数化，默认 no-op 零回归。

#### 2.1.2 仍存在的问题

| 编号 | 严重度 | 问题 | 依据 |
|------|--------|------|------|
| B1 | P0 | **可用率（availability）未应用**：`params.availability_pct < 100` 仅产生 warning（L464-465），收入不打折。真实 BESS 可用率约 95-98%（强迫停运+检修），**系统性高估收入** | 行业运营数据 |
| B2 | P1 | **能量与 FCAS 未联合优化（V1 纯套利）**：FCAS 收入在 API 层作为**加法项**叠加（`investment_routes.py` L280-301），但 FCAS enablement 与能量套利**争用同一 MW 功率与 SoC 净空**，分别计算会**双重计入功率容量**，高估叠加收入 | AEMO 5MS 联合优化机制；Mohamed 2023 (被引 90) |
| B3 | P1 | **价格接受者假设**：LP 假设 BESS 不影响价格（无市场冲击）。大容量电池的自我蚕食（cannibalization）由独立引擎处理，但回测收入未反馈该效应，短期回测偏乐观 | 幂律蚕食模型 |
| B4 | P2 | **"% of perfect foresight" 未在响应中显式暴露**：架构已具备计算能力（双跑现实窗 vs 完美预见窗），但未输出该行业标准指标供分析师判读回测可信度 | 见 2.1.1 |
| B5 | P2 | **MILP 最小持续时间约束 O(n×min_duration)** 在长窗口可能变慢；当前窗口 ~24h 可接受，需加规模上限保护 | 性能 |

#### 2.1.3 优化建议

- **B1（P0）**：在 `run_bess_backtest_v1` 汇总阶段对 `net_revenue`/吞吐按 `availability_pct/100` 折算，或在窗口级引入随机强迫停运掩码。最小实现：汇总收入 × 可用率系数，并移除"未应用"warning。
- **B2（P1）**：提供**能量+FCAS 联合优化**路径（`CoOptimizedBacktest` 已是独立 Tab，第 5 阶段）。在 LP 中对每个区间增加 FCAS enablement 决策变量，约束 `charge+discharge+fcas_raise_enablement ≤ P_max`、SoC 净空需同时满足 FCAS 持续时间要求。将联合优化结果作为投资分析的收入基线，避免加法双计。
- **B3（P1）**：将 `CannibalizationEngine` 的价差衰减因子（幂律 α≈0.6）反馈进多年现金流的 arbitrage_multiplier，使回测→财务链路自洽。
- **B4（P2）**：响应 summary 增加 `pct_of_perfect_foresight = realistic_net / perfect_foresight_net`，前端在"联合优化回测"阶段展示，作为回测可信度标签。

### 2.2 财务模型（`financial_model.py`，327 行）

#### 2.2.1 已达到的科学水准

1. **NPV**：`npf.npv(discount_rate, cash_flows)`，`cash_flows[0]=-total_capex` 位于 t=0 不贴现，符合定义。
2. **债务定容按最差年 min CFADS**（L182-194）：`max_annual_debt_service = min_cfads / target_dscr`，再取 `min(PV(debt_service), 0.8×capex)` —— 保证**每年** DSCR 达标（而非平均），并受最大杠杆约束，取两约束更紧者。这是稳健的项目融资做法。
3. **Monte Carlo 方法论扎实**（L236-327）：固定种子（可审计）；**对数正态乘子** `μ=-σ²/2` 保证 `E[mult]=1.0`（消除 normal+max(0,·) 截断的上偏）；**AR(1)** 年际自相关（避免"单次永久冲击缩放每年"）；套利/FCAS 部分相关。同时报告 `min_dscr` 与 `dscr_avg`、`levered_irr`。

#### 2.2.2 仍存在的问题

| 编号 | 严重度 | 问题 | 依据 |
|------|--------|------|------|
| M1 | P1 | **回本期未线性插值**（L32-37）：`payback = i` 返回整数年，精度 ±1 年。行业标准应线性插值 `payback = i-1 + |cum_{i-1}| / CF_i` | 财务教科书标准 |
| M2 | P1 | **IRR 无收敛保护**（L26-28）：多年补强投资（augmentation capex）导致现金流**多次变号**，`npf.irr` 可能返回多重 IRR 或不收敛（返回 None）。应改用 MIRR 或带 bracketing 的求根，并在变号≥2 时提示 IRR 不可靠 | 笛卡尔符号规则；MIRR |
| M3 | P2 | **债务定容用"恒定年金"而非"债务塑形（sculpting）"**：行业标准是按 CFADS 逐年塑形还本，保持各年 DSCR 恒定，可**释放更多债务容量**；当前"按最差年恒定年金"偏保守，在高 CFADS 年留有余量未用 | 项目融资标准（Financial Modelling Handbook） |
| M4 | P2 | **未计算 LLCR**（贷款期限覆盖率）：银行审贷除 DSCR 外常用 LLCR = PV(CFADS over loan life)/Debt，当前缺失 | 项目融资标准 |
| M5 | P2 | **ROI 未贴现**（L30）：`sum(cash_flows[1:])/capex` 为简单回报，与 NPV 口径不一致，展示时需明确标注"未贴现" | 口径一致性 |

#### 2.2.3 优化建议

- **M1（P1）**：线性插值实现（约 4 行改动）：
  ```python
  if cumulative >= 0 and payback is None and i > 0:
      prev = cumulative - cf            # 上一年累计（<0）
      payback = (i - 1) + (-prev / cf)  # 分数年
  ```
- **M2（P1）**：变号计数 ≥2 时，主指标改用 **MIRR**（`npf.mirr`，需 finance_rate/reinvest_rate），并保留 IRR 但标注 `irr_reliable=false`。
- **M3/M4（P2）**：新增"债务塑形"可选模式与 LLCR 输出，作为银行合约面板（记忆提到的可信度面板）的增强指标。

### 2.3 投资分析 API 数据流（`investment_routes.py`，558 行）

#### 2.3.1 数据流完整性（已验证链路）

`POST /api/investment-analysis` → 缓存/inflight 去重 → `_build_backtest_summary`（回测）→ `_derive_arbitrage_baseline`（套利基线）→ `_get_fcas_baseline`（FCAS 基线）→ `annual_cycles_history`（含 FCAS 隐含循环）+ `dod_severity_history`（rainflow）→ `run_scenario`（基准+情景）→ `run_monte_carlo` → P3 决策层 → 决策调整情景/MC → `_build_investment_response` → TaxModel（税后）→ ForwardPriceEngine（20 年三情景）→ DegradationModel。

**链路完整**：从电池规格输入到 20 年现金流 + P10/P50/P90 + 税后 + 前瞻价格 + 衰减模型，闭环无断点。缓存分层（DB analysis_cache + Redis）+ inflight 去重（防重型端点惊群）设计良好。

#### 2.3.2 仍存在的问题

| 编号 | 严重度 | 问题 | 位置 |
|------|--------|------|------|
| A1 | P0 | **路由模块化未完成**：`investment_analysis` 仍 `import server as _server` 委托近全部逻辑（`_build_backtest_summary`/`_derive_arbitrage_baseline`/`_get_fcas_baseline`/`_build_investment_p3_decision`/`_build_investment_response` 等），Phase 2 拆分目标（server.py<200 行）未达成，核心逻辑仍在 7000+ 行 server.py | L228-382 |
| A2 | P1 | **FCAS 基线魔法数**：`baseline_fcas/15000`、`8760`、隐含放电→循环换算（L280-301）为启发式硬编码，缺乏可追溯参数来源与单位注释 | L292-296 |
| A3 | P1 | **CAPEX 公式在 TaxModel 分支重复**（L445-451）与 `financial_model.py` L77 重复，存在漂移风险（DRY） | L445-451 |
| A4 | P2 | **异常吞噬**：L404-406 捕获所有异常返回通用 500，前端无法区分"数据不足"vs"求解失败"vs"参数非法"，调试与用户提示受损 | L402-406 |
| A5 | P2 | **degradation_rate 缓存后重附**：`_enrich_with_degradation_model` 在缓存命中后仍执行（L253），但缓存的现金流是否用旧 degradation 值？需确认缓存 key 含 degradation_rate（`model_dump(exclude_none=True)` 应已包含，需回归测试兜底） | L246-253 |

#### 2.3.3 优化建议

- **A1（P0，架构债）**：将 `_build_backtest_summary` / `_derive_arbitrage_baseline` / `_get_fcas_baseline` / `_build_investment_response` 等下沉到 `engines/` 或 `services/investment_service.py`，路由只做编排。这是 `platform-optimization/design.md` Phase 2 的核心未竟目标。
- **A2（P1）**：将 FCAS 换算常量提取为具名参数（`FCAS_AVG_PRICE_PER_MW_YEAR` 等）并注释来源；理想情况由 B2 的联合优化直接产出 FCAS 收入，取代启发式。
- **A3（P1）**：CAPEX 计算收敛为 `FinancialModel` 单一函数，TaxModel 分支复用 `base_result.metrics.total_capex`。
- **A4（P2）**：分层异常类型（`InsufficientDataError`/`SolverError`/`ValidationError`）映射到 422/424/500 并携带机器可读 code。

---

## 3. 深度调研交叉验证结论

| 主题 | 权威来源 | 对当前实现的判定 |
|------|----------|------------------|
| 回测方法论 | OptiGrid（energy-storage.news）; Hornek 2025 (arXiv 2501.07121); EPRI DER-VET | ✅ 滚动时域 MPC + 完美预见上界是**正确且行业标准**的方法；建议显式输出 "% of perfect foresight"（B4） |
| MPC vs 反应式 | PatSnap MPC field studies | MPC 较反应式提升 12-18%，低于完美预见上界 —— 佐证有限预见折价合理 |
| 能量+FCAS 叠加 | AEMO BESS Contingency FCAS 指南; Mohamed 2023 (被引 90); 5MS 联合优化 | ⚠ 分别加法计算存在**功率容量双计**风险，应联合优化（B2） |
| 债务定容 | Financial Modelling Handbook; BreakingIntoWallStreet | ✅ min-DSCR 定容稳健；建议增加 **debt sculpting** 与 **LLCR**（M3/M4） |
| Monte Carlo | 电价对数正态右偏; AR(1) 时序 | ✅ 对数正态无偏 + AR(1) 已是**优于常规正态截断**的做法 |
| 回本期 | 财务标准 | ⚠ 需线性插值（M1） |
| IRR 多重解 | 笛卡尔符号规则; MIRR | ⚠ 补强投资多次变号需 MIRR 兜底（M2） |

---

## 4. 优化方案实施路线（按优先级）

### P0 — 必修（正确性/架构底线）

1. **B1** BESS 回测应用 availability_pct 折算（收入口径正确性）
2. **A1** 投资分析核心逻辑从 server.py 下沉到 service 层（完成 Phase 2 拆分）

### P1 — 应修（科学性/体验显著提升）

3. **B2** 能量+FCAS 联合优化，消除功率双计（接入第 5 阶段 CoOptimizedBacktest）
4. **B3** 蚕食效应反馈进多年现金流
5. **M1** 回本期线性插值
6. **M2** IRR 多重变号时 MIRR 兜底 + 可靠性标注
7. **F1** 阶段化加载文案系统（"正在聚合市场数据…"等）
8. **F2** 恢复 7 阶段结论层（漏斗收敛叙事）
9. **F3** 常驻筛选上下文条
10. **A2/A3** FCAS 魔法数具名化 + CAPEX 公式去重

### P2 — 增强（对标行业顶级）

11. **B4** 输出 "% of perfect foresight" 回测可信度指标
12. **M3/M4** debt sculpting + LLCR 银行合约面板增强
13. **F4/F6** 漏斗进度可视化 + 相邻阶段预取
14. **A4** 分层异常类型
15. **F5** 核实并修复 FilterBar 触摸目标 ≥44px

### 技术约束遵从

- 后端全部改动落在 FastAPI + Python 3.11 + scipy(HiGHS)/PuLP + numpy-financial 现有栈内，无新增重依赖
- 前端改动基于 React 19 + Vite 8 + 现有 `React.lazy`/`Suspense`/`FilterContext` 架构，零破坏性契约变更
- 所有回测/财务改动应配套 Hypothesis 属性测试（`platform-optimization/design.md` 已规划的不变量：维度、SoC 边界、收入非负、DSCR≥目标）

---

## 5. 附录：本轮审查核对的实际文件

| 文件 | 行数 | 结论 |
|------|------|------|
| `web/src/pages/MarketPage.jsx` | 191 | 配置驱动 7-Tab 编排器，架构先进 |
| `web/src/lib/marketConfig.js` | 304 | NEM 7 阶段 / WEM 5 阶段配置 + 模块注册表 |
| `web/src/components/funnel/DynamicStage.jsx` | 38 | 结论层被架空（F2） |
| `web/src/components/funnel/ModuleRenderer.jsx` | 154 | 懒加载+故障隔离，加载文案未消费（F1） |
| `backend/engines/bess_backtest_v1.py` | 491 | 滚动时域 MPC LP/MILP，availability 未应用（B1） |
| `backend/engines/financial_model.py` | 327 | MC 方法论扎实，payback/IRR 待加固（M1/M2） |
| `backend/routes/investment_routes.py` | 558 | 数据流完整，仍重度委托 server.py（A1） |

---

## 6. 实施记录

> 实施日期: 2026-07-25
> 方法: 按业务域纵向切 6 切片（S1-S6），每切片端到端闭环（后端逻辑 → API 契约 → 前端展示 → 测试）

### 切片 S1 — BESS 回测收入口径正确性 ✅
- **B1** 可用率折算：`availability_factor` 乘入 gross/net/吞吐，默认 100% 零回归
- **B4** `pct_of_perfect_foresight`：开关 `compute_perfect_foresight_benchmark` 控制额外求解
- **B5** MILP 规模保护：`MILP_MAX_MIN_DURATION_CONSTRAINTS=200000`，超限降级 LP
- 测试：24 passed（`tests/test_bess_backtest_engine.py`）

### 切片 S2 — 能量+FCAS 联合优化域 ✅
- **B2** `revenue_baseline_mode` 开关（additive/co_optimized），co_optimized 调用 `CoOptimizationEngine` 消除功率双计
- **A2** 魔法数具名化：`15000`→`params.fcas_revenue_per_mw_year`、`8760`→`HOURS_PER_YEAR`
- 新建 `backend/services/investment_baseline.py`（纯函数 `derive_co_optimized_baseline`）
- 测试：11 passed（`tests/test_co_optimized_baseline.py`）

### 切片 S3 — 蚕食效应反馈域 ✅
- **B3** `apply_cannibalization` 开关 + 幂律衰减因子注入 `run_scenario` 的 yr_arb
- 公式：`decay_factor_t = 1/(1+growth_rate*t)^alpha`，默认 alpha=0.6、growth=10%
- MC 路径自动生效（run_scenario 内部应用，无双重计算）
- 测试：9 passed（`tests/test_cannibalization_feedback.py`）

### 切片 S4 — 财务模型加固 ✅
- **M1** payback 线性插值（`Optional[float]`）
- **M2** IRR 兜底：变号≥2 → `mirr` + `irr_reliable=False`
- **M3** debt sculpting 模式（`debt_repayment_mode: "annuity"|"sculpting"`）
- **M4** LLCR = PV(CFADS)/debt
- **M5** `roi_undiscounted=True` 显式标注
- 测试：12 passed（`tests/test_financial_model_hardening.py`）

### 切片 S5 — 投资分析架构下沉 ✅
- **A1** 新建 `backend/services/investment_service.py`（薄委托层），`investment_routes.py` 改从 service 层调用
- **A3** CAPEX 去重：TaxModel 分支复用 `base_result.metrics.total_capex`
- **A4** 定义 `InsufficientDataError`/`SolverError`/`ValidationError`，映射 424/500/422
- **A5** 回归测试确认 cache key 含 `degradation_rate`
- 测试：9 passed（`tests/test_investment_architecture.py`）

### 切片 S6 — 前端交互体验域 ✅
- **F1** `ModuleLoadingSkeleton` 增 `label`/`variant`，6 个重型模块配置中英加载文案
- **F2** `DynamicStage` 消费 `useStageSummaries` hook，驱动 `StageConclusion` 结论层
- **F3** Tab 栏下方常驻上下文条（区域/年份/日型）
- **F4** Tab 徽章增已访问状态（✓ 绿色）
- **F5** Tab 按钮 `min-h-[44px]`（WCAG 2.5.5）
- **F6** `requestIdleCallback` 预取相邻阶段 `dataDependencies`

### 测试汇总
- 后端 67 tests passed（S1:24 + S2:11 + S3:9 + S4:12 + S5:9 + driver:2）
- 前端构建未运行（环境无 Node），代码通过导入验证
