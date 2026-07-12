# NEMOSIS README（中文整理版）

来源：[01_NEMOSIS_README.md](./01_NEMOSIS_README.md)

## 项目简介

NEMOSIS 是一个 Python 包，用于下载和处理 AEMO 发布的澳大利亚国家电力市场（NEM）历史数据。

## 它能做什么

NEMOSIS 主要用于访问 NEM 的历史 MMS/Nemweb 数据，适合：

- 电价研究
- 机组调度研究
- SCADA 数据抓取
- FCAS / 出清 / 约束分析

## 安装

```bash
pip install nemosis
```

## 文档与资源

- GitHub Wiki：详细文档
- Worked Examples：示例
- AEMO 表清单：可下载的数据表
- 列定义说明：字段解释
- 公开视频教程
- NEMOSIS 论文

## README 中给出的典型用途

- 查找发电机的 DUID 并下载 SCADA 数据
- 可视化发电机报价行为
- 复现 AEMO 关于电池调度精度的分析

## 两类主要数据

### 1. Dynamic tables

带时间列的数据表，可以按起止时间筛选。

例如：

- `DISPATCHPRICE`
- `DISPATCHLOAD`
- `DISPATCH_UNIT_SCADA`

### 2. Static tables

不依赖时间窗口、相对静态的数据表。

## 两种工作流

### `dynamic_data_compiler`

适合：

- 直接在 Python 中分析
- GUI 与 API 共享缓存

特点：

- 自动从 NEMWeb 下载 CSV
- 保存到本地缓存
- 自动转成 feather
- 后续查询会优先复用缓存

示例：

```python
from nemosis import dynamic_data_compiler

start_time = '2017/01/01 00:00:00'
end_time = '2017/01/01 00:05:00'
table = 'DISPATCHPRICE'
raw_data_cache = 'C:/Users/your_data_storage'

price_data = dynamic_data_compiler(start_time, end_time, table, raw_data_cache)
```

### `cache_compiler`

适合：

- 主要为了缓存
- 后续交给外部程序处理
- feather/parquet 为主的数据流水线

## 对你项目的价值

相对你当前的手写抓取逻辑，NEMOSIS 的优势在于：

- 表结构适配更成熟
- 历史数据抓取更系统
- 更适合长期维护
- 便于接入更多 MMSDM 表

## 建议用法

如果你的目标是“澳洲电网价格预测平台”，NEMOSIS 最适合承担：

1. 历史现货价抓取
2. FCAS 历史表抓取
3. 机组/区域/需求相关表抓取
4. 本地缓存层

它更像是你的**历史市场数据底座**。
