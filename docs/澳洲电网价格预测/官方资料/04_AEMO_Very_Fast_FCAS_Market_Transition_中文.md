# AEMO | Very Fast FCAS 市场过渡（中文整理版）

来源：[04_AEMO_Very_Fast_FCAS_Market_Transition.md](./04_AEMO_Very_Fast_FCAS_Market_Transition.md)

## 关键结论

`Very Fast Raise` 和 `Very Fast Lower` 两类应急 FCAS 服务于 **2023-10-09** 正式引入。

这也是你项目里为什么不能再只保留旧 8 类 FCAS 的直接依据。

## 官方说明

页面指出，Very Fast Contingency FCAS（VF FCAS）的采购量取决于：

- 最大可信事故（largest credible contingency）的规模
- 假设的负荷切除量（assumed load relief）
- 系统运行惯量水平（operating inertia levels）

## 页面结构

该页面主要包含以下部分：

- `Background`
  - 背景说明
- `Market transition arrangements`
  - 市场过渡安排
- `Current allowed requirement volumes`
  - 当前允许的需求量
- `South Australia island requirement volumes`
  - 南澳孤网情形需求量
- `South Australia risk-of-island requirement volumes`
  - 南澳孤网风险情形需求量
- `Queensland island requirement volumes`
  - 昆州孤网情形需求量
- `Queensland risk-of-island requirement volumes`
  - 昆州孤网风险情形需求量
- `Understanding underlying requirement volumes`
  - 底层需求量解释
- `Reference information`
  - 参考资料

## 对你项目的直接影响

如果你的系统还只抓：

- 6 秒 Raise/Lower
- 60 秒 Raise/Lower
- 5 分钟 Raise/Lower
- Regulation Raise/Lower

那么从 **2023-10-09** 之后开始，口径已经不完整。

你需要补：

- `Very Fast Raise`
- `Very Fast Lower`

## 建议落地动作

1. 扩展数据表字段
2. 扩展抓取逻辑
3. 对 2023-10-09 前后做分段分析
4. 前端和报告里明确区分：
   - 旧 8 类 FCAS 口径
   - 新 10 类 FCAS 口径
