"""端到端验证脚本：运行 ForwardPriceEngine 完整流程并输出结果。

验证内容：
1. 引擎初始化（含 ML 校准尝试）
2. 三情景 20 年预测（NSW1, SA1）
3. 新增字段验证（FCAS, structural_risks, duration_efficiency, peak_demand）
4. Modo Energy 基准对比
5. 数学不变量检查
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from engines.forward_price_engine import ForwardPriceEngine
from models.forward_price_models import ScenarioType
from models.financial_params import BatterySpecs


def main():
    print("=" * 70)
    print("Forward Model Accuracy Upgrade - 端到端验证")
    print("=" * 70)

    # 1. 初始化引擎
    print("\n[1] 初始化 ForwardPriceEngine...")
    try:
        engine = ForwardPriceEngine()
        print(f"    ✓ 引擎初始化成功")
        print(f"    ML 校准状态: {engine._calibration.get('status', 'unknown')}")
        if engine._calibrated_spreads:
            print(f"    校准区域: {list(engine._calibrated_spreads.keys())}")
        else:
            print(f"    校准区域: 无（使用默认参数）")
    except Exception as e:
        print(f"    ✗ 初始化失败: {e}")
        return

    # 2. 定义电池参数
    battery = BatterySpecs(
        power_mw=100.0,
        duration_hours=4.0,
        round_trip_efficiency=0.87,
        calendar_degradation_rate=0.025,
    )
    print(f"\n[2] 电池参数: {battery.power_mw}MW / {battery.duration_hours}h / RTE={battery.round_trip_efficiency}")

    # 3. 运行三情景预测
    regions = ["NSW1", "SA1"]
    scenarios = [ScenarioType.CENTRAL, ScenarioType.HIGH, ScenarioType.LOW]

    print("\n[3] 20 年三情景预测结果:")
    print("-" * 70)

    for region in regions:
        print(f"\n  === {region} ===")
        for scenario in scenarios:
            try:
                projection = engine.generate_20year_projection(
                    region=region,
                    scenario=scenario,
                    battery=battery,
                )

                # 提取关键指标
                year1 = projection.annual_projections[0]
                year5 = projection.annual_projections[4]
                year10 = projection.annual_projections[9]
                year20 = projection.annual_projections[19]

                print(f"\n  [{scenario.value.upper()}]")
                print(f"    Total Revenue/MW (20yr): ${projection.total_revenue_per_mw:,.0f}")
                print(f"    NPV/MW (8% discount):   ${projection.npv_per_mw:,.0f}")
                print(f"    Year 1:  ${year1.estimated_revenue_per_mw:,.0f}/MW | "
                      f"spread={year1.mean_spread:.1f} | capture={year1.capture_rate:.3f} | "
                      f"FCAS=${year1.fcas_revenue_per_mw or 0:.0f}/MW")
                print(f"    Year 5:  ${year5.estimated_revenue_per_mw:,.0f}/MW | "
                      f"spread={year5.mean_spread:.1f} | capture={year5.capture_rate:.3f}")
                print(f"    Year 10: ${year10.estimated_revenue_per_mw:,.0f}/MW | "
                      f"spread={year10.mean_spread:.1f} | capture={year10.capture_rate:.3f}")
                print(f"    Year 20: ${year20.estimated_revenue_per_mw:,.0f}/MW | "
                      f"spread={year20.mean_spread:.1f} | capture={year20.capture_rate:.3f}")

                # 新增字段验证
                print(f"    --- 新增字段 ---")
                print(f"    duration_efficiency_factor: {year1.duration_efficiency_factor:.3f}")
                print(f"    effective_peak_demand (Y1): {year1.effective_peak_demand:,.0f} MW")
                print(f"    effective_peak_demand (Y20): {year20.effective_peak_demand:,.0f} MW")
                print(f"    structural_risks (Y1): {year1.structural_risks}")
                print(f"    structural_risks (Y5): {year5.structural_risks}")
                print(f"    metadata.structural_risks: {projection.metadata.get('structural_risks', [])}")

            except Exception as e:
                print(f"  [{scenario.value.upper()}] ✗ 失败: {e}")

    # 4. 数学不变量检查
    print("\n\n[4] 数学不变量检查:")
    print("-" * 70)

    projection = engine.generate_20year_projection(
        region="NSW1", scenario=ScenarioType.CENTRAL, battery=battery
    )

    # 4.1 capture_rate 范围
    all_capture_rates = [p.capture_rate for p in projection.annual_projections]
    cr_ok = all(0.10 <= cr <= 0.55 for cr in all_capture_rates)
    print(f"  capture_rate ∈ [0.10, 0.55]: {'✓' if cr_ok else '✗'} "
          f"(range: [{min(all_capture_rates):.3f}, {max(all_capture_rates):.3f}])")

    # 4.2 mean_spread 非负
    all_spreads = [p.mean_spread for p in projection.annual_projections]
    spread_ok = all(s >= 0 for s in all_spreads)
    print(f"  mean_spread ≥ 0: {'✓' if spread_ok else '✗'} "
          f"(range: [{min(all_spreads):.1f}, {max(all_spreads):.1f}])")

    # 4.3 P10 ≤ P50 ≤ P90 (如果 ML 校准成功)
    print(f"  P10 ≤ P50 ≤ P90: (需要 ML 校准成功才能验证)")

    # 4.4 duration_efficiency_factor 一致性
    def_values = set(p.duration_efficiency_factor for p in projection.annual_projections)
    def_ok = len(def_values) == 1  # 同一电池所有年份应相同
    print(f"  duration_efficiency 一致性: {'✓' if def_ok else '✗'} (value: {def_values.pop():.3f})")

    # 4.5 effective_peak_demand 单调递增
    demands = [p.effective_peak_demand for p in projection.annual_projections]
    demand_mono = all(demands[i] <= demands[i+1] for i in range(len(demands)-1))
    print(f"  effective_peak_demand 单调递增: {'✓' if demand_mono else '✗'} "
          f"(Y1={demands[0]:,.0f}, Y20={demands[-1]:,.0f})")

    # 4.6 structural_risks 条件
    risks_y1 = projection.annual_projections[0].structural_risks  # 2027
    risks_y5 = projection.annual_projections[4].structural_risks  # 2031
    risk_ok = (len(risks_y1) == 0 or projection.annual_projections[0].year > 2028) and \
              (len(risks_y5) > 0 if projection.annual_projections[4].year > 2028 else len(risks_y5) == 0)
    print(f"  structural_risks 条件逻辑: {'✓' if risk_ok else '✗'} "
          f"(Y1[{projection.annual_projections[0].year}]={len(risks_y1)} risks, "
          f"Y5[{projection.annual_projections[4].year}]={len(risks_y5)} risks)")

    # 5. Modo Energy 基准对比
    print("\n\n[5] Modo Energy 基准对比:")
    print("-" * 70)
    try:
        benchmark_result = engine.validate_against_benchmarks()
        if benchmark_result["results"]:
            for r in benchmark_result["results"]:
                status = "✓" if abs(r["deviation_pct"]) <= 30 else "✗"
                print(f"  {status} {r['region']} ({r['period']}): "
                      f"model=${r['model_revenue']:,.0f} vs benchmark=${r['benchmark_revenue']:,.0f} "
                      f"→ {r['deviation_pct']:+.1f}%")
            print(f"\n  总体: {'✓ PASS' if benchmark_result['all_within_threshold'] else '✗ FAIL'} "
                  f"(最大偏差: {benchmark_result['max_deviation_pct']:.1f}%)")
        else:
            print("  ⚠ 无基准数据可用（financial_evidence.json 缺失或为空）")
    except Exception as e:
        print(f"  ✗ 基准验证失败: {e}")

    print("\n" + "=" * 70)
    print("验证完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
