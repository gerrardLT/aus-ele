# 论文中文信息卡

来源：[03_Scenarios_modelling_for_forecasting_day_ahead_electricity_prices_Crossref.json](./03_Scenarios_modelling_for_forecasting_day_ahead_electricity_prices_Crossref.json)

## 标题

用于日前电价预测的情景建模：澳大利亚案例研究

## 基本信息

- DOI：`10.1016/j.apenergy.2021.118296`
- 期刊：`Applied Energy`
- 发布时间：`2022-02`
- 作者：
  - Xin Lu
  - Jing Qiu
  - Gang Lei
  - Jianguo Zhu

## 主题翻译

这篇论文关注的不是单一电价点预测，而是**情景建模（scenario modelling）**。  
也就是说，作者试图生成一组可能的价格路径或价格场景，用它们来支持更稳健的预测与决策，而不是只押一个点值。

## 对澳洲电网研究的意义

对 NEM 这种高波动、高尖峰、强非线性的市场，情景预测通常比单点预测更有实际价值，因为它更适合：

- 风险评估
- 策略优化
- 储能调度
- 收益分布分析

## 对你项目的直接启发

这篇论文最值得借鉴的方向是：

1. 从“预测一个价格”转向“预测一组可能价格场景”
2. 让下游策略模块接收概率/情景输入
3. 把价格预测和 BESS 优化更自然地连接起来

## 建议用法

如果你后面升级系统，可以把这篇论文作为：

- 概率预测/情景预测模块的理论依据
- 从可视化平台走向交易级回测框架的过渡参考

## 备注

- 本目录里还有作者稿 PDF：
  - [06_Scenarios_modelling_for_forecasting_day_ahead_electricity_prices_author_manuscript_UTS.pdf](./06_Scenarios_modelling_for_forecasting_day_ahead_electricity_prices_author_manuscript_UTS.pdf)
