# AEMO | Pre-dispatch（中文整理版）

来源：[02_AEMO_Pre_dispatch.md](./02_AEMO_Pre_dispatch.md)

## 页面作用

本页介绍 AEMO 的预调度数据（Pre-dispatch）和 5 分钟预调度数据（P5MIN）的公开下载方式与字段范围。

## 核心说明

AEMO 以逗号分隔的平面文件提供市场数据，便于公众访问。  
最近文件放在：

- `Current reports`
- `Archive reports`

旧文件会转入归档目录。  
文件中的价格均为**不含 GST**。

文件名带有：

- 日期
- 时间戳
- 唯一标识符

示例：

`PUBLIC_DISPATCHIS_200511081245_0000000068650088.ZIP`

## 30 分钟 Pre-dispatch

该文件提供：

- 按区域划分的 30 分钟预调度（预测）数据
- 预测范围到**下一市场日结束**
- **每半小时更新一次**

覆盖内容包括：

- 联络线潮流预测
- 约束
- 区域参考电价（RRP）
- 需求
- 可调度发电
- 可调度负荷
- 辅助服务数据

下载入口：

- `Predispatch`
  - 当前目录，约 4MB
  - 14 天滚动窗口
- `Archive files`
  - 周文件归档

## 5 分钟 Pre-dispatch

该文件提供：

- 按区域划分的 5 分钟预调度（预测）数据
- 展示未来 **1 小时** 的短期价格和需求预测
- **每 5 分钟更新一次**

下载入口：

- `5 Minute Predispatch`
  - 当前目录，约 1MB
  - 2 天滚动窗口
- `Archive files`
  - 日文件归档

## 特殊说明

页面特别说明了两个机组/负荷对象在市场分类和报送口径上的特殊性：

- `YARWUN_1`
  - 注册分类不是标准的 scheduled generator
  - 但在调度报价、目标和出力上按 scheduled generator 处理
- `SNOWYP`
  - Tumut 3 Pumps 不被分类为 scheduled load
  - 但在调度报价、目标和负荷消耗上按 scheduled load 处理

## 免责声明

该数据仅用于信息参考，不构成商业用途依据。  
AEMO 不保证数据在任何时刻都准确或持续可用。

## 对你项目的意义

这页非常关键，因为它直接对应：

- `PREDISPATCH`
- `P5MIN`

这两类数据是做：

- 电价预测基线
- 价格收敛分析
- 预测误差研究
- 基于“当时可见信息”的滚动回测

时最重要的官方输入。
