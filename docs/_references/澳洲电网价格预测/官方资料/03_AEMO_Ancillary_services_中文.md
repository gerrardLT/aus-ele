# AEMO | 辅助服务（中文整理版）

来源：[03_AEMO_Ancillary_services.md](./03_AEMO_Ancillary_services.md)

## 页面作用

本页说明 AEMO 在 NEM 中如何使用辅助服务维持系统安全、稳定和可靠运行。

## 核心定义

辅助服务用于维持电力系统的关键技术特性，包括：

- 频率
- 电压
- 网络负载水平
- 系统重启能力

## FCAS 市场

AEMO 运行 **8 个独立的 FCAS 市场**，用于频率控制辅助服务（FCAS）的交付。

此外还会通过协议采购：

- `NSCAS`
  - Network Support and Control Ancillary Services
- `SRAS`
  - System Restart Ancillary Services

付款通常包括：

- 可用性支付
- 实际交付支付

## SRAS

SRAS 用于重大供给中断或系统需要黑启动/重启的场景。

## 成本特征

辅助服务成本取决于某一时刻所需服务量。  
因为需求量会显著波动，所以成本也会明显波动。

## 页面列出的关键参考资料

- `Guide to Frequency Control Ancillary Services`
- `SO_OP_3708 - Non-market Ancillary Services`

## 与价格预测/储能研究的关系

对你的项目最重要的点有三个：

1. FCAS 不是单一市场，而是多个细分产品
2. FCAS 成本和价格具有明显时变性
3. 储能收益分析不能把 FCAS 简单等同于“附加价格”，而应结合：
   - 可用容量
   - 启用条件
   - 市场需求量
   - 实际结算口径

## 简短理解

这页是做 FCAS 研究的总入口页。  
如果你后面要补 Very Fast FCAS、做 FCAS 联合优化、或者修正现有“价格直接叠加收入”的问题，这页是官方口径起点。
