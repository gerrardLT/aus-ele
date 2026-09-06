"""路由注册基线守卫（R0.3 从一次性探针转为常备测试，2026-09-06）。

为什么值得常驻：R1/R3/R4 要新增 9 个 route 模块，而 FastAPI/Starlette 的匹配规则是
**先注册者胜** —— 后注册的重复 path 不会报错，只会静默变成不可达的死代码。这类缺陷
没有运行期症状（端点照样 200），只有「你以为改了、实际没生效」，正是 P0 安全修复最
不能碰上的坑。

必须探 ``app:app`` 而不是 ``server:app``：生产 CMD 是 ``gunicorn app:app``
（Dockerfile.backend:33），而 app.py:247-252 只把 server 里「尚未被路由模块占用」的
path 追加进来。实测（2026-09-06）：``server.app`` 有 228 个路由对象、只有 206 个唯一
method+path —— 即 **22 组重复**（含 ``/api/investment-analysis``、``/api/finland/board/*``
全部 4 个、``/api/jobs`` 3 个、``/api/data-quality/*`` 4 个等）；而生产 ``app:app``
上重复为 0，因为路由模块版本先注册、server 的那份在追加时被 path 去重挡掉。

结论：**server.py 里这 22 个端点函数在生产中不可达**。只改 server.py 副本的安全修复
等于没改；直调它们做断言的测试（如 ``test_investment_backtest_driver`` 调
``server.investment_analysis``）也不覆盖生产路径。迁移动作登记在 R4。
"""

import unittest
from collections import Counter

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fastapi.routing import APIRoute  # noqa: E402

from app import app  # noqa: E402


def _method_path_pairs():
    pairs = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(m for m in (route.methods or set()) if m not in {"HEAD", "OPTIONS"}):
            pairs.append((method, route.path, route.endpoint.__module__))
    return pairs


class RouteBaselineTests(unittest.TestCase):
    def test_no_silent_route_shadowing_on_served_app(self):
        """生产 app 上任意 (method, path) 只能有一个注册。"""
        pairs = [(m, p) for m, p, _module in _method_path_pairs()]
        dupes = sorted({pair for pair, count in Counter(pairs).items() if count > 1})
        self.assertEqual(
            dupes,
            [],
            "重复的 method+path 会让后注册者静默变成死代码；若确需覆盖，"
            "必须先删掉旧实现而不是再加一条。",
        )

    def test_route_count_floor_catches_unregistered_module(self):
        """数量下界：某个 route 模块 import 失败/忘记 include 时，这里先红。

        刻意用下界而不是精确值 —— R1~R6 会持续新增端点，精确值会制造无意义 churn。
        """
        self.assertGreaterEqual(len(_method_path_pairs()), 190)

    def test_p0_security_endpoints_are_served_by_expected_module(self):
        """把"哪个副本在服役"钉死，防止安全修复被接到低优先级的重复注册上。

        动机（2026-09-06）：``/api/investment-analysis`` 同时在 routes.investment_routes
        与 server.py 里定义。若哪天路由模块的注册顺序变了，P0.7 的 in-flight 外置会
        安静地失效，而所有单测照样绿（它们直调 server 里那份死副本）。
        """
        expectations = {
            ("POST", "/api/investment-analysis"): "routes.investment_routes",
            ("GET", "/api/v1/account/me"): "routes.account_routes",
            # 尚未迁出 server.py 的遗留端点：显式记录归属，迁移时改这里
            ("GET", "/api/auth/oidc/callback"): "server",
        }
        owners = {(m, p): module for m, p, module in _method_path_pairs()}
        for pair, module in expectations.items():
            self.assertIn(pair, owners, f"{pair} 未注册 —— 端点消失比走错模块更严重")
            self.assertEqual(owners[pair], module, f"{pair} 的服役实现从 {module} 变成了 {owners[pair]}")


if __name__ == "__main__":
    unittest.main()
