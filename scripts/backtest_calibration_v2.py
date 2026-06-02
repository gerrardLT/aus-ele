"""回测对比脚本：ML 校准引擎 v1 vs v2（历史参考）。

对比修改前后的校准指标：
- v1: 目标=daily_spread(MAX-MIN), 特征含当天avg_price/spike_ratio（数据泄漏）
- v2: 目标=peak_offpeak_spread(峰谷价差), 特征全部使用滞后值（无泄漏）
- v3 (当前): 目标=daily_spread(winsorized MAX-MIN, clip [-100,500]),
  与 ForwardPriceEngine 的 mean_spread 统一，无需缩放因子

注意：此脚本为 v1→v2 的历史对比，v3 已将目标变量改回 daily_spread（winsorized 版本）。

运行方式: python scripts/backtest_calibration_v2.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def run_backtest():
    """运行 v2 校准并输出对比结果。"""
    from deps import get_db
    from engines.ml_calibration_engine import MLCalibrationEngine

    print("=" * 70)
    print("ML 校准引擎回测对比: v1 (旧) vs v2 (新)")
    print("=" * 70)
    print()

    # v1 基线指标（修改前的运行结果）
    v1_metrics = {
        "target": "daily_spread (MAX-MIN)",
        "features_leaked": "avg_price, spike_ratio (当天信息)",
        "r2": 0.579,
        "mae": 731.0,
        "direction_accuracy": 0.615,
    }

    print("【v1 基线（修改前）】")
    print(f"  目标变量: {v1_metrics['target']}")
    print(f"  数据泄漏: {v1_metrics['features_leaked']}")
    print(f"  R²:       {v1_metrics['r2']:.4f}")
    print(f"  MAE:      ${v1_metrics['mae']:.1f}")
    print(f"  方向准确率: {v1_metrics['direction_accuracy']:.1%}")
    print()

    # 运行 v2 校准
    print("【v2 校准（修改后）- 正在运行...】")
    db = get_db()
    engine = MLCalibrationEngine(db)
    result = engine.calibrate()
    status = engine.get_calibration_status()

    print(f"  目标变量: peak_offpeak_spread (峰时均价 - 谷时均价)")
    print(f"  数据泄漏: 无（全部使用滞后特征）")
    print(f"  状态:     {status['status']}")
    print(f"  训练期:   {status.get('train_period', 'N/A')}")
    print(f"  验证期:   {status.get('validation_period', 'N/A')}")
    print(f"  样本数:   {status.get('sample_count', 0)}")
    print()

    v2_r2 = status.get("validation_r2")
    v2_mae = status.get("validation_mae")
    v2_dir = status.get("direction_accuracy")

    if v2_r2 is not None:
        print(f"  R²:       {v2_r2:.4f}")
        print(f"  MAE:      ${v2_mae:.1f}")
        print(f"  方向准确率: {v2_dir:.1%}")
    else:
        print("  ⚠️ 验证指标不可用（数据不足或校准失败）")
        print()
        return

    print()
    print("-" * 70)
    print("【对比总结】")
    print("-" * 70)
    print(f"{'指标':<12} {'v1 (旧)':<15} {'v2 (新)':<15} {'变化':<15} {'评价'}")
    print(f"{'-'*12} {'-'*15} {'-'*15} {'-'*15} {'-'*10}")

    # R² 对比
    r2_change = v2_r2 - v1_metrics["r2"]
    r2_pct = r2_change / v1_metrics["r2"] * 100 if v1_metrics["r2"] != 0 else 0
    r2_eval = "✅ 提升" if r2_change > 0 else ("⚠️ 下降" if r2_change < -0.05 else "➡️ 持平")
    print(f"{'R²':<12} {v1_metrics['r2']:<15.4f} {v2_r2:<15.4f} {r2_change:+.4f} ({r2_pct:+.1f}%)  {r2_eval}")

    # MAE 对比
    mae_change = v2_mae - v1_metrics["mae"]
    mae_pct = mae_change / v1_metrics["mae"] * 100 if v1_metrics["mae"] != 0 else 0
    mae_eval = "✅ 下降" if mae_change < 0 else ("⚠️ 上升" if mae_change > 50 else "➡️ 持平")
    print(f"{'MAE ($)':<12} {v1_metrics['mae']:<15.1f} {v2_mae:<15.1f} {mae_change:+.1f} ({mae_pct:+.1f}%)  {mae_eval}")

    # 方向准确率对比
    dir_change = v2_dir - v1_metrics["direction_accuracy"]
    dir_pct = dir_change / v1_metrics["direction_accuracy"] * 100 if v1_metrics["direction_accuracy"] != 0 else 0
    dir_eval = "✅ 提升" if dir_change > 0.02 else ("⚠️ 下降" if dir_change < -0.05 else "➡️ 持平")
    print(f"{'方向准确率':<10} {v1_metrics['direction_accuracy']:<15.1%} {v2_dir:<15.1%} {dir_change:+.1%} ({dir_pct:+.1f}%)  {dir_eval}")

    print()
    print("【关键改进说明】")
    print("  1. 数据泄漏修复: avg_price/spike_ratio → lag_1_avg_price/lag_1_spike_ratio")
    print("     v1 的 R²=0.579 部分来自数据泄漏（用当天信息预测当天），实际部署时性能会更差")
    print("  2. 目标变量改进: daily_spread(MAX-MIN) → peak_offpeak_spread(峰谷均价差)")
    print("     去除极端尖峰主导（$15,000+），更接近 BESS 实际可捕获的套利空间")
    print("  3. MAE 大幅下降是因为目标变量量级不同:")
    print(f"     daily_spread 均值 ~$800-1500 (含极端尖峰)")
    print(f"     peak_offpeak_spread 均值 ~$30-80 (更稳定)")
    print()

    # 输出校准参数
    if result:
        print("【校准参数（各区域）】")
        for region, params in sorted(result.items()):
            if isinstance(params, dict) and "base_spread" in params:
                print(f"  {region}: base_spread=${params['base_spread']:.1f}, spike_freq={params.get('spike_frequency', 0):.4f}")
        if "compression_curve" in result:
            cc = result["compression_curve"]
            print(f"  压缩曲线: coefficient={cc.get('coefficient', 0):.1f}, exponent={cc.get('exponent', 0):.3f}")
    print()


if __name__ == "__main__":
    run_backtest()
