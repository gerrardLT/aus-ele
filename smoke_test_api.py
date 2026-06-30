"""后端 API 集成冒烟测试脚本"""
import os
import urllib.request
import urllib.error
import json
import time
import sys

# 复用服务器侧 deploy/scripts/lib/smoke.py 中的 evaluate_smoke，保证
# 冒烟结论判定语义（500 或连接失败=失败；非 500 的 HTTP 响应=通过）与
# verify 阶段一致。将该 lib 目录加入 import 路径。
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "deploy", "scripts", "lib"),
)
from smoke import evaluate_smoke  # noqa: E402

# BASE 支持由 SMOKE_BASE_URL 环境变量覆盖，默认指向生产 API 地址；
# SMOKE_BASE_URL 优先，其次回退到现有默认地址。
BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:18099")
TIMEOUT = 180  # 秒

endpoints = [
    # (method, path, body_or_none, description)
    ("GET", "/api/health", None, "Health"),
    ("GET", "/api/price-trend?region=NSW1&period=30d", None, "Price Trend"),
    ("GET", "/api/hourly-price-profile?region=NSW1", None, "Hourly Price Profile"),
    ("GET", "/api/peak-analysis?region=NSW1", None, "Peak Analysis"),
    ("GET", "/api/revenue-analysis?region=NSW1", None, "Revenue Analysis"),
    ("GET", "/api/fcas-analysis?region=NSW1", None, "FCAS Analysis"),
    ("GET", "/api/spike-analysis?region=NSW1", None, "Spike Analysis"),
    ("POST", "/api/investment-analysis", {"region": "NSW1", "scenario": "central"}, "Investment Analysis"),
    ("GET", "/api/forward-scenarios", None, "Forward Scenarios"),
    ("GET", "/api/forward-scenarios/NSW1", None, "Forward Scenarios NSW1"),
    ("GET", "/api/data-quality/summary", None, "Data Quality Summary"),
    ("GET", "/api/data-quality/markets", None, "Data Quality Markets"),
    ("GET", "/api/v1/outlook/cannibalization?market=NEM&region=NSW1", None, "Outlook Cannibalization"),
    ("GET", "/api/v1/outlook/fcas-collapse?market=NEM&region=NEM-wide&year=2025", None, "Outlook FCAS Collapse"),
    ("GET", "/api/v1/outlook/regional-timing?market=NEM&target_year=2026", None, "Outlook Regional Timing"),
    ("POST", "/api/v1/outlook/merchant-risk", {"market":"NEM","region":"NSW1","power_mw":100,"duration_hours":4}, "Outlook Merchant Risk"),
    ("GET", "/api/v1/narrative/investment-story?region=NSW1", None, "Narrative Investment Story"),
    ("GET", "/api/v1/narrative/calibration-status", None, "Narrative Calibration Status"),
    ("GET", "/api/v1/narrative/scenario-comparison?region=NSW1", None, "Narrative Scenario Comparison"),
    ("GET", "/api/saturation/compression-impact?region=NSW1", None, "Saturation Compression"),
    ("GET", "/api/ranking/regions", None, "Ranking Regions"),
    ("GET", "/api/v1/cost-structure/breakdown?region=NSW1", None, "Cost Structure Breakdown"),
    ("GET", "/api/v1/coopt/backtest-summary?region=NSW1", None, "Co-optimized Backtest"),
    ("GET", "/api/wem/market-summary", None, "WEM Market Summary"),
    ("GET", "/api/aggregation/cross-market", None, "Aggregation Cross-Market"),
]

results = []
errors_500 = []

print(f"开始冒烟测试，共 {len(endpoints)} 个端点...\n")

for i, (method, path, body, desc) in enumerate(endpoints, 1):
    url = BASE + path
    status_code = None
    elapsed = 0.0
    error_msg = ""
    passed = False

    try:
        start_t = time.time()
        if method == "GET":
            req = urllib.request.Request(url)
        else:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status_code = resp.status
            _ = resp.read()  # consume body
        elapsed = time.time() - start_t
        passed = True
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_t
        status_code = e.code
        if e.code == 500:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
                error_msg = err_body[:500]
                errors_500.append((desc, path, error_msg))
            except:
                error_msg = "无法读取错误体"
                errors_500.append((desc, path, error_msg))
            passed = False
        else:
            # 422, 404 等非500错误 - 路由存在
            passed = True
    except Exception as ex:
        elapsed = time.time() - start_t
        status_code = "ERR"
        error_msg = str(ex)[:200]
        passed = False

    result_str = "PASS" if passed else "FAIL"
    results.append((desc, method, path, status_code, f"{elapsed:.2f}", result_str, error_msg))
    print(f"  [{i:02d}/{len(endpoints)}] {result_str} | {status_code} | {elapsed:.1f}s | {desc}")

# 输出结果表格
print("\n" + "="*120)
print(f"{'端点':<30} | {'方法':<5} | {'状态码':<7} | {'耗时(秒)':<9} | {'结果':<5} | {'错误摘要'}")
print("-"*120)
for desc, method, path, code, elapsed, result, err in results:
    err_short = err[:60].replace("\n", " ") if err else ""
    print(f"{desc:<30} | {method:<5} | {str(code):<7} | {elapsed:<9} | {result:<5} | {err_short}")

# 统计
pass_count = sum(1 for r in results if r[5] == "PASS")
fail_count = len(results) - pass_count
print(f"\n总计: {len(results)} 个端点 | 通过: {pass_count} | 失败: {fail_count}")

# 500 错误详情
if errors_500:
    print("\n" + "="*80)
    print("500 错误详情:")
    print("="*80)
    for desc, path, body in errors_500:
        print(f"\n--- {desc} ({path}) ---")
        print(body)
        print()

print("\n冒烟测试完成。")

# 以进程退出码表达结论（供 verify 阶段判定，R6.4）：
# 存在任一 500 或连接失败 → 非零退出；否则零退出。
# 结论由 evaluate_smoke(results) 派生，与 deploy/scripts/lib/smoke.py 语义一致。
if evaluate_smoke(results):
    sys.exit(0)
else:
    sys.exit(1)
