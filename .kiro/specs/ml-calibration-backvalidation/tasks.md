# Implementation Plan: ML Calibration Backvalidation

## Overview

精简版实现：修复过拟合（1 行改动）、添加反推验证端点（内联辅助函数）、扩展基准数据、前端展示校准状态。

## Tasks

- [x] 1. 修复 MLCalibrationEngine 过拟合
  - [x] 1.1 从 `backend/engines/ml_calibration_engine.py` 的 `_train_model` 方法中移除 feature_cols 列表里的 "lag_30_spread"
  - [x] 1.2 从 `_generate_calibrated_params` 方法中移除 feature_cols 列表里的 "lag_30_spread"
  - [x] 1.3 确认 R² > 0.85 时的 warning 日志已存在（当前代码已有质量检查逻辑，确认阈值正确）
  - [x] 1.4 在 `tests/test_ml_calibration_engine.py` 中添加测试：验证 feature_cols 不包含 "lag_30_spread" 且包含 "lag_1_spread" 和 "lag_7_spread"
    - _Requirements: 1.1, 1.2_

- [x] 2. 扩展基准数据和添加反推验证端点
  - [x] 2.1 在 `data/financial_evidence.json` 中添加 `modo_benchmarks` 字段，包含 2024_full、2025_H1、2025_H2 三个期间的 NSW1/QLD1/VIC1/SA1/NEM_AVG 收入基准值
    - _Requirements: 2.2, 2.3_
  - [x] 2.2 在 `backend/routes/narrative_routes.py` 中添加辅助函数 `_compute_backvalidation(engine, region)` 和 `_get_modo_benchmark(region)` — 实现反推公式和基准加载
    - _Requirements: 2.1, 2.2, 2.4_
  - [x] 2.3 添加 GET /api/v1/narrative/backvalidation/summary 端点（路由定义在 /{region} 之前）— 返回 4 区域结果 + 摘要计数
    - _Requirements: 3.1, 2.5, 2.6_
  - [x] 2.4 添加 GET /api/v1/narrative/backvalidation/{region} 端点 — 返回单区域结果
    - _Requirements: 3.2, 3.3, 3.4_
  - [x] 2.5 编写 `tests/test_backvalidation_routes.py` 集成测试（5 个用例：正常响应、无效区域 422、摘要端点、偏差计算、排序验证）
    - _Requirements: 3.3_

- [x] 3. 前端校准状态与验证展示
  - [x] 3.1 在 ForwardSpreadCurve.jsx 中添加 calibration-status API 调用，渲染 "AI 校准" badge（绿色=calibrated，琥珀色=failed/insufficient）
    - _Requirements: 4.1_
  - [x] 3.2 添加精度指标面板（R², MAE $/MWh, 方向准确率 %）显示在图表标题下方
    - _Requirements: 4.2_
  - [x] 3.3 添加 backvalidation/summary API 调用，渲染验证摘要（model revenue vs benchmark + 偏差颜色编码 + "数据来源: Modo Energy"）
    - _Requirements: 4.3, 4.4_
  - [x] 3.4 添加错误降级处理（API 失败时隐藏面板）和 zh/en 本地化标签
    - _Requirements: 4.5, 4.6_

- [x] 4. 验证与收尾
  - [x] 4.1 运行 ML 校准确认 R² 从 ~0.99 降到合理范围（0.3-0.85）
  - [x] 4.2 运行全部测试确保无回归
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 不新建独立 BackvalidationEngine 类，反推逻辑内联在 narrative_routes.py
- 不新建 modo_benchmark.json，扩展现有 financial_evidence.json
- Requirement 4（前瞻预测模式）已移除，作为独立后续优化
- PBT 属性测试精简为 3 个非平凡属性，可在 test_backvalidation_routes.py 中一并实现

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1"] },
    { "id": 1, "tasks": ["1.4", "2.2"] },
    { "id": 2, "tasks": ["2.3", "2.4"] },
    { "id": 3, "tasks": ["2.5", "3.1", "3.2"] },
    { "id": 4, "tasks": ["3.3", "3.4"] },
    { "id": 5, "tasks": ["4.1", "4.2"] }
  ]
}
```
