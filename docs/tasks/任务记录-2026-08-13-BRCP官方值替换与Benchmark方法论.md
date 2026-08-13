# 任务记录-2026-08-13-BRCP官方值替换与Benchmark方法论

状态：已完成（随本提交推送）

依据：[知识库缺口与资料沉淀规划.md](../strategy/知识库缺口与资料沉淀规划.md) §2.4 + 待办"占位数据替换"

---

## 目标

1. 以 AEMO/ERA 官方口径替换 BRCP 占位值（原 11,500 示意值）
2. 补齐 benchmark 正式方法论文档与首批校准记录

## 实施内容

### 1. BRCP 官方值替换（调研发现两处原口径错误）

官方口径（AEMO BRCP 页 + ERA + pv-magazine 交叉验证）：
- **2025 BRCP = $360,700/MW/年**（适用 CY2027/28，基准资产 160MW OCGT）
- **2026 BRCP = $486,900/MW/年**（适用 CY2028/29，较 2025 +35%，基准资产 200MW/800MWh 电池）
- Modo 草稿口径 $491,700，预计电池实际可得约 $422,372/MW/年（容量盈余折减）

修正的两处错误认知：
1. 数量级：BRCP 是 **$36~49 万/MW/年**，原占位 11,500 差 30+ 倍
2. 参考资产：2027/28 起为 **200MW/800MWh**（非 1200MWh）；此前容量年为 160MW 燃气轮机

改动：`data/contract_revenue_defaults.json`（双容量年 official 条目 + 基准资产沿革）、`services/contract_revenue.py`（默认容量年 2028/29、caveat 更新）、`benchmark_routes.py` 默认参数、`data/assumptions_registry.json` 登记项、`grid_rules.json` 卡片与人读版。CIS floor 保持示例值（中标 floor 非公开，已标 status=illustrative_placeholder）。

### 2. Benchmark 方法论（bess_benchmark_v1）

新建 `docs/architecture/NEM-BESS收益基准方法论.md`：参考资产定义（登记库 wired）、理想日内循环算法 7 步、粒度推断与完整性规则、覆盖边界四 caveat、偏差来源分析、**校准记录表首批 3 条**（趋势同向 -83% vs -80%、绝对值 1.7× 偏差归因理想算子、SA1 尖峰留档）。

## 验证

- 回归：4 个测试文件 39/39 全绿
- BRCP 端点验证：默认返回 2028/29 = 486,900（official），2027/28 = 360,700（official）

## 剩余数据债

- CIS floor 75,000 仍为量级示意（中标 floor 非公开）——拿到实际投标结果后替换
- 校准记录月度追加机制（随运营节奏）
