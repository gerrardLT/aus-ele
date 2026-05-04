# P1 Regime Compact Contract Spec

**日期**: 2026-05-01  
**状态**: Draft / Implemented-first contract freeze  
**关联文档**:
- [2026-04-30-global-grid-model-roadmap-design.md](/g:/project/aus-ele/docs/superpowers/specs/2026-04-30-global-grid-model-roadmap-design.md)
- [2026-04-30-p0-data-foundation-design.md](/g:/project/aus-ele/docs/superpowers/specs/2026-04-30-p0-data-foundation-design.md)

---

## 1. 目标

为 P1 regime layer 定义一个稳定、轻量、面向消费端的输出契约：

- 不替代完整 `regime_layer`
- 不要求前端或外部 API 解析大对象
- 不把研究型驱动细节直接暴露为页面耦合
- 允许后续 P1/P2 演进而不频繁打破消费方

本 spec 对应的稳定消费字段名为：

- `regime_compact`

---

## 2. 设计原则

### 2.1 双层输出

P1 输出分为两层：

1. `regime_layer`
   - 完整研究版
   - 包含完整 driver、active regime、score map、metadata
   - 用于研究、调试、回溯、深入解释

2. `regime_compact`
   - 轻量消费版
   - 字段有限、语义稳定
   - 用于前端总览、摘要卡片、外部轻量客户端

### 2.2 加法兼容

- 已有 `regime_layer` 保持不删不改
- 新增 `regime_compact`
- 已有消费者不需要立刻迁移
- 新消费者默认只读 `regime_compact`

### 2.3 明确 unavailable 语义

当 P1 依赖的底层表不存在、覆盖不足、或运行环境不完整时：

- 主分析接口不能因此报 500
- 必须返回一个可消费的 `regime_compact`
- 消费端通过 `availability_status` 和 `warnings` 判断可用性

---

## 3. 契约定义

### 3.1 顶层位置

在消费型分析接口中：

- 保留 `regime_layer`
- 新增顶层 `regime_compact`

在直接 regime 接口中：

- `/api/p1/regime-layer` 保留原始 `regime_layer` 顶层字段
- 新增 `compact`

### 3.2 字段结构

`regime_compact` / `compact` 结构如下：

```json
{
  "availability_status": "available",
  "primary_regime": {
    "regime": "scarcity",
    "score": 67.0,
    "confidence": 0.74
  },
  "active_regimes": [
    {
      "regime": "scarcity",
      "score": 67.0,
      "confidence": 0.74
    }
  ],
  "regime_score_map": {
    "scarcity": 67.0
  },
  "top_drivers": [
    {
      "headline": "Load tightness signal 22.4",
      "driver_type": "load_tightness"
    }
  ],
  "transition_hints": [
    "Reserve stress can escalate into broader scarcity if shortfalls persist."
  ],
  "warnings": []
}
```

### 3.3 字段说明

#### `availability_status`

枚举值：

- `available`
  - regime 计算成功
- `unavailable`
  - regime 计算失败或输入层不足，返回占位结果

当前版本不单独引入 `partial`。如果后续需要，可在不破坏现有值的前提下追加。

#### `primary_regime`

当前最主要的 regime：

- `regime`
- `score`
- `confidence`

如果 unavailable，可为 `null`。

#### `active_regimes`

已激活 regime 的轻量列表：

- 最多返回前 3 个
- 每个元素只保留：
  - `regime`
  - `score`
  - `confidence`

不在 compact 层返回完整 drivers。

#### `regime_score_map`

完整的 regime 到 score 映射：

- `oversupply`
- `scarcity`
- `negative_price`
- `reserve_stress`
- `congestion`
- `transmission_separation`

消费端可以用它做小型雷达图、条形图或 heat strip。

#### `top_drivers`

对 `drivers` 的轻量抽取：

- 最多 3 条
- 每条只保留：
  - `headline`
  - `driver_type`

不保留更深层解释，避免消费端直接耦合研究字段。

#### `transition_hints`

最多 3 条字符串提示，用于表达：

- 当前状态联动
- 潜在升级方向
- 跨 regime 的解释桥接

#### `warnings`

当前 compact contract 的消费级 warning：

首批保留：

- `regime_layer_unavailable`

后续允许追加，但不应移除已存在语义。

---

## 4. 可用性语义

### 4.1 `available`

含义：

- P1 成功构建
- `primary_regime` 可读
- `regime_score_map` 可读
- `top_drivers` 和 `transition_hints` 可作为摘要解释

### 4.2 `unavailable`

含义：

- 底层数据缺失、测试环境不完整、或 P1 构建失败
- 主分析接口本身仍有效
- 页面或外部客户端应降级展示，而不是报错

消费端行为建议：

- 不显示 regime 颜色结论或强结论标签
- 显示 “regime unavailable / insufficient context”
- 仍可展示主图、主分析结果和 metadata

---

## 5. 输出边界

### 5.1 compact 层不负责

- 暴露完整 driver 栈
- 暴露 regime 内部构造公式
- 暴露过多调试字段
- 暴露底层 source lineage 明细

这些能力保留在 `regime_layer` 和 `metadata`。

### 5.2 compact 层负责

- 当前状态摘要
- 状态强度
- 状态置信度
- 主要驱动摘要
- 状态联动提示
- 是否可用

---

## 6. 当前接入范围

当前已接入 `regime_layer + regime_compact` 的内部消费接口：

- `/api/event-overlays`
- `/api/grid-forecast`
- `/api/price-trend`
- `/api/peak-analysis`
- `/api/hourly-price-profile`
- `/api/fcas-analysis`

当前已接入的外部 v1 路由：

- `/api/v1/events`
- `/api/v1/prices`
- `/api/v1/fcas`

直接 regime 接口：

- `/api/p1/regime-layer`

---

## 7. 前端消费约束

前端后续默认只读取：

- `regime_compact.availability_status`
- `regime_compact.primary_regime`
- `regime_compact.active_regimes`
- `regime_compact.regime_score_map`
- `regime_compact.top_drivers`
- `regime_compact.transition_hints`
- `regime_compact.warnings`

前端不应默认依赖：

- `regime_layer.drivers`
- `regime_layer.active_regimes[*].drivers`
- `regime_layer.metadata.coverage`

这些字段视为研究/调试层，不保证页面稳定语义。

---

## 8. 外部 API 消费约束

对外 API 默认建议：

- 轻量客户端使用 `regime_compact`
- 深度客户端可选择读取 `regime_layer`

外部文档中应强调：

- `regime_compact` 是稳定字段集
- `regime_layer` 是扩展字段集

---

## 9. 演进规则

后续允许：

- 在 `regime_layer` 中增加更多研究字段
- 在 `regime_score_map` 中增加新 regime
- 在 `warnings` 中增加新 warning code

后续不应轻易做：

- 删除 `regime_compact` 现有字段
- 修改 `availability_status` 既有值含义
- 把 `top_drivers` 改成深层嵌套对象
- 让页面重新依赖完整 `regime_layer`

---

## 10. 完成标准

此 spec 生效后，P1 compact contract 的完成标准是：

- 关键分析接口稳定输出 `regime_compact`
- v1 外部 API 稳定透传 `regime_compact`
- unavailable 场景不会打断主分析接口
- 前端新实现默认只绑定 `regime_compact`

