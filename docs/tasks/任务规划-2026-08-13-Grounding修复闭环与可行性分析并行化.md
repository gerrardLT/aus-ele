# 任务规划-2026-08-13-Grounding修复闭环与可行性分析并行化

状态：已完成（2026-08-13 实施完毕）

依据：[调研-2026前沿Agent架构收敛分析.md](../research/调研-2026前沿Agent架构收敛分析.md)——落地其中两个最高 ROI 缺口。

---

## 1. Generate → Verify → Repair 数值溯源修复闭环

**现状**：`_apply_grounding_check` 只观测——ungrounded_ratio 高时打风险标记，不回炉。

**方案**（确定性修复，最多一次重生成）：
1. `grounding.py` 新增两个纯函数：
   - `should_repair(check, min_checked=4, ratio_threshold=0.5)` → 与风险标记同阈值
   - `build_repair_feedback(samples)` → 修复指令文本（要求删除或替换为工具结果中真实数值，禁止编造）
2. `synthesizer.synthesize_report` 增加 `repair_feedback` 可选参数，追加到 user prompt 尾部
3. `orchestrator._synthesize` 内嵌修复环：
   - 首次合成 → grounding 检查 → 超阈值且 LLM 可用且 env 开关开启（AUS_ELE_AGENT_GROUNDING_REPAIR，默认开）→ 带反馈重合成一次
   - 取两次中 ungrounded_ratio 更低者（修复无效则保留原版，绝不劣化）
   - 返回第 5 个值 `grounding_repair` 元信息（attempted/used/before/after/improved），5 个调用点写入 report.metadata
4. 护栏原则不变：修复环自身异常只降级不阻断；规则合成路径（LLM 不可用）不触发修复

**成本评估**：仅在"超阈值"的运行上多一次合成 LLM 调用；常规运行零增量。

## 2. full_investment_feasibility 收入深潜组扩容

**现状**：模板模式已实现 asyncio.gather 组内并行（既有能力），收入深潜组 [price_trend, peak, fcas] 缺尖峰与基准两个独立工具。

**方案**：
- steps 插入 `spike_profit_analysis` 与 `bess_revenue_benchmark`（收入深潜段）
- parallel_groups：[0,1] / **[2,3,4,5,6]** / [7,8,9] / [10] / [11,12]（索引顺延）
- `_exec_bess_revenue_benchmark` 加 WEM 守卫（WEM 返回 no_data 结构化提示而非抛错——benchmark 仅覆盖 NEM 大陆区）

**token 成本评估**：合成上下文每工具摘要上限 2000 字符，+2 工具 ≈ +4k 字符（约 1.3k tokens），仅完整可行性模板触发，可接受；收益是尖峰捕获与基准锚定纳入统一深潜。

**不改 ReAct 自由模式**：LLM 自主决定工具顺序的场景不做强制并行（动态路径并行需 planner 支持，超出本轮范围）。

## 3. 验收

- 新增单测：should_repair/build_repair_feedback 纯函数；synthesize_report repair_feedback 注入；模板步骤/并行组完整性与索引合法性（复用既有断言族）
- 回归：orchestrator/golden trajectories/profile 一致性全绿
- 端到端：构造高 ungrounded 场景验证修复环触发路径（元数据 grounding_repair.attempted=true）

## 4. 实施记录（2026-08-13）

### 修复环（Generate → Verify → Repair）

- `grounding.py`：新增 `should_repair`（阈值与风险标记一致：checked≥4 且 ratio>0.5）与 `build_repair_feedback`（删除/替换指令，禁止编造）两个纯函数
- `synthesizer.py`：`synthesize_report`/`_llm_synthesize` 新增 `repair_feedback` 可选参数，非空时追加到提示词尾部；补 Optional 导入
- `orchestrator._synthesize`：内嵌一次修复环（env 开关 AUS_ELE_AGENT_GROUNDING_REPAIR 默认开），取两次中 ratio 更低者绝不劣化；返回 5 元组，第 5 位 `grounding_repair` 元信息（attempted/used/improved/before/after）
- 5 个合成调用点全部适配（含 fallback 分支）；`_apply_grounding_check` 新增可选参数把修复元信息写入 `report.metadata["grounding_repair"]`

### 并行化

- `full_investment_feasibility`：11 → 13 步，收入深潜组扩为 [price_trend, peak, fcas, spike, benchmark] 五工具 asyncio.gather 并行；既有模板执行器无需改动
- `_exec_bess_revenue_benchmark` 加 WEM 守卫（返回 not_covered 结构化提示而非抛错）

### 验证

- 新增 `tests/test_grounding_repair.py` 18 用例：纯函数、提示词注入、修复环集成（触发/不触发/env 关闭/绝不劣化）、模板步骤与并行组合法性、WEM 守卫——全绿
- 既有 `test_full_investment_has_correct_step_count` 断言 11→13 同步更新；TestWorkflowTemplates 全绿
- 回归：profile/parallel 一致性 6/6（114 subtests）；知识库五件套 48/48

### 过程中发现

- "绝不劣化"测试构造教训：grounding 对小整数（≤20）豁免，修复版掺小整数会稀释 ratio 导致误判更优——测试用例需用均超豁免阈值的大数字构造真劣化场景
- test_agent_orchestrator 全套约 6 分钟且部分用例依赖网络健康检查偏 flaky，建议后续拆快慢两层

### 成本确认

- 修复环：仅超阈值运行多一次合成调用，常规零增量
- 并行组：+2 工具结果进合成上下文 ≈ +4k 字符（~1.3k tokens），仅完整可行性模板触发
