# NEMSEER README（中文整理版）

来源：[02_NEMSEER_README.md](./02_NEMSEER_README.md)

## 项目简介

NEMSEER 是一个用于下载和处理 AEMO 历史预测数据的 Python 包。  
重点不是历史实际出清结果，而是 **AEMO 当时发布的 forecast / ahead-process 数据**。

## 安装

```bash
pip install nemseer
```

很多使用场景还需要安装 NEMOSIS：

```bash
pip install nemosis
```

## 它解决的核心问题

NEMSEER 让你可以访问 AEMO 的以下历史预测数据：

- pre-dispatch
- PASA

并将数据整理成：

- pandas DataFrame
- xarray Dataset

## 重点概念

### PASA

PASA 更偏向资源充足性评估，回答类似问题：

- 预测窗口内是否能满足运行需求？
- 预留裕度是否足够？

### Pre-dispatch

pre-dispatch 会结合最新的市场报价，因此能给出：

- 区域电价预测
- FCAS 价格预测

这比单纯的实际历史价格更接近“市场当时能看到的信息”。

## NEMSEER 支持的 forecast 类型

1. `P5MIN`
   - 5 分钟 pre-dispatch
2. `PREDISPATCH`
   - 传统 pre-dispatch
3. `PDPASA`
   - pre-dispatch PASA
4. `STPASA`
   - Short Term PASA
5. `MTPASA`
   - Medium Term PASA

## ST PASA Replacement

README 特别提醒：

- PD PASA 和 ST PASA 的方法论仍在调整
- AEMO 的 ST PASA Replacement 项目会把 PD PASA 与 ST PASA 进一步整合

因此做长期研究时，要注意规则和流程变迁。

## 文档部分

- glossary：术语和流程说明
- quick start：快速上手
- examples：使用示例

## 对你项目的价值

如果说：

- `NEMOSIS` 负责“历史真实市场数据”
- 那么 `NEMSEER` 更适合负责“历史预测数据”

这对价格预测项目尤其重要，因为它能支撑：

1. AEMO 官方预测基线对比
2. 预测误差分析
3. 价格收敛分析
4. 用“当时可得信息”做滚动回测

## 一句话理解

NEMSEER 是你做“预测侧数据层”的关键工具。  
如果没有它，你的回测很容易退化成事后诸葛亮式的 perfect foresight 分析。
