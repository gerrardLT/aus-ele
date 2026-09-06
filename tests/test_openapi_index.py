"""⌘K 端点索引的 OpenAPI 契约（R3.4，2026-09-06）。

为什么这条端点值得一个测试文件，而不是「反正 FastAPI 自带 /openapi.json」：

生产形态下 ``/openapi.json`` **拿不到文档**。``deploy/nginx/default.conf`` 只有
``location /api/`` 代理后端，其余一律 ``try_files $uri $uri/ /index.html``；Vite dev server
同样只转发 ``/api``。所以浏览器侧消费者打 ``/openapi.json`` 得到的是 **200 + index.html**。
JSON.parse 抛错被面板的 catch 消化成「只剩页面项」—— 属于「功能缺失但不报错」最难发现
那一类。这里断言 content-type，就是要把这个静默失败变成红。

另一半断言针对另一个经典坑：返回「自己那份子文档」。路由挂在子 APIRouter 上时，若实现
写成 ``router.openapi()`` 之类，端点照样 200、照样是合法 JSON，只是里面只有一个路径 ——
面板会安静地搜不到任何端点，而没有任何人会报错。所以这里比对的是**整份 app 文档**。
"""

import json
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fastapi.routing import APIRoute  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

INDEX_PATH = "/api/openapi.json"

# 实测（2026-09-06）生产 app 的规模：219 paths / 234 operations / 32 tags。
# 取一个远低于实测、又远高于「只有一份子文档」的下界：新批次只加端点不减，
# 一旦数字掉到这个量级，说明返回的不再是整份文档。
MIN_PATHS = 150


def _count_operations(document: dict) -> int:
    http_methods = {"get", "put", "post", "patch", "delete"}
    return sum(
        1
        for item in (document.get("paths") or {}).values()
        for key in (item or {})
        if key in http_methods
    )


class OpenApiIndexTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_index_is_registered_on_the_served_app(self):
        """必须真的注册在生产 app 上（routes/__init__.py 单模块失败不阻断 = 静默不上线）。"""
        paths = {
            route.path
            for route in app.routes
            if isinstance(route, APIRoute)
        }
        self.assertIn(INDEX_PATH, paths)

    def test_index_returns_json_not_the_spa_fallback(self):
        response = self.client.get(INDEX_PATH)
        self.assertEqual(response.status_code, 200)
        # 这条是本文件存在的核心理由：拿到 HTML 时 status 一样是 200。
        self.assertTrue(
            response.headers.get("content-type", "").startswith("application/json"),
            f"content-type={response.headers.get('content-type')!r}：会被 SPA fallback 兜成 index.html",
        )
        payload = response.json()
        self.assertIsInstance(payload, dict)
        self.assertIn("paths", payload)

    def test_index_is_the_whole_application_document(self):
        """排除「返回子路由那份」：必须是与 app.openapi() 等价的内容。"""
        with self.client as client:
            delivered = client.get(INDEX_PATH).json()
        reference = app.openapi()
        self.assertEqual(set(delivered.get("paths") or {}), set(reference.get("paths") or {}))
        self.assertGreaterEqual(len(delivered.get("paths") or {}), MIN_PATHS)
        self.assertGreaterEqual(_count_operations(delivered), MIN_PATHS)
        self.assertEqual(delivered.get("openapi"), reference.get("openapi"))

    def test_index_itself_requires_no_auth(self):
        """面板必须在未登录时也能拉索引（⌘K 是发现入口，不该要求先认证）。"""
        delivered = self.client.get(INDEX_PATH).json()
        index_op = (delivered.get("paths") or {}).get(INDEX_PATH, {}).get("get", {})
        self.assertFalse(index_op.get("security"), "索引自身不得要求鉴权，否则未登录时面板永远为空")

    def test_document_declares_a_usable_security_scheme(self):
        """面板据此决定 curl 要不要带 Authorization 头；缺了这个标记就永远不带。"""
        document = self.client.get(INDEX_PATH).json()
        schemes = (document.get("components") or {}).get("securitySchemes") or {}
        self.assertTrue(schemes, "securitySchemes 为空：所有端点都会被判定为免鉴权")
        protected = [
            f"{method.upper()} {path}"
            for path, item in (document.get("paths") or {}).items()
            for method, operation in (item or {}).items()
            if isinstance(operation, dict) and operation.get("security")
        ]
        self.assertTrue(protected, "没有任何带 security 的操作：面板的鉴权判定无输入")

    def test_every_path_starts_with_the_api_prefix(self):
        """前端拼 curl 时只取 origin（不重复前缀），前提就是文档里的 path 自带 /api。
        若哪天有人把路由前缀改掉，curl 生成会静默指向错误地址。"""
        document = self.client.get(INDEX_PATH).json()
        strays = [path for path in (document.get("paths") or {}) if not path.startswith("/api")]
        self.assertEqual(strays, [], f"存在 /api 之外的路径：{strays[:5]}")

    def test_document_is_stable_across_calls(self):
        """面板每次打开都会拉一次；两份逐字相同的 JSON 才算可缓存、可比对。"""
        first = self.client.get(INDEX_PATH).text
        second = self.client.get(INDEX_PATH).text
        self.assertEqual(json.loads(first), json.loads(second))

    def test_document_title_comes_from_the_brand_layer(self):
        """info.title 是会直接给用户看的字段（/developer 页与 ⌘K 面板页脚都渲染它）。

        为什么不靠 tests/test_brand_consistency.py 的扫描器：它按 FORMER_BRAND_NAMES 词表
        匹配字符串，而 `"AEMO NEM Data API"` 不在词表里 —— 于是它在改名后一路静默存活。
        这里改成锁「活文档里的值必须等于品牌常量的投影」，比再往词表里塞一个字符串强：
        词表靠人记得加，这条不认字面量、只认两个来源是否同源。
        """
        from brand import BRAND_DISPLAY

        delivered = self.client.get(INDEX_PATH).json()
        title = (delivered.get("info") or {}).get("title") or ""
        self.assertIn(BRAND_DISPLAY, title, f"OpenAPI info.title 未走品牌常量层：{title!r}")

    def test_document_title_does_not_lead_with_a_third_party_acronym(self):
        """以数据源机构缩写命名的对外契约会被读成「官方接口」。

        AEMO 作为数据源名必须保留（Spec R2.7），但不得充当产品标题的主语。
        """
        delivered = self.client.get(INDEX_PATH).json()
        title = ((delivered.get("info") or {}).get("title") or "").strip()
        self.assertFalse(title.upper().startswith("AEMO"), f"对外契约标题以第三方缩写开头：{title!r}")


if __name__ == "__main__":
    unittest.main()
