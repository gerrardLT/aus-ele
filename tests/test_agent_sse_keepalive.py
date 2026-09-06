"""chat-stream SSE 心跳（_stream_with_keepalive）单元测试。

背景：生产步骤 9 co_optimized_backtest 执行期间 SSE 长时间空闲，
云侧防火墙/NAT 按空闲超时掐断 TCP → 前端 "network error"。
心跳包装必须：① 空闲时发心跳标记；② 事件原样透传；③ 编排器异常
转为 error 事件帧；④ 客户端断开取消时不损伤仍在运行的生产者语义。
"""

import asyncio
import sys
import unittest

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from routes import agent_routes


def _run(coro):
    try:
        return asyncio.run(coro)
    finally:
        # pytest-asyncio 缺席时手动清理事件循环，避免污染后续用例
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except RuntimeError:
            pass


async def _collect(events_source, interval):
    original = agent_routes._SSE_KEEPALIVE_INTERVAL_SECONDS
    agent_routes._SSE_KEEPALIVE_INTERVAL_SECONDS = interval
    try:
        items = []
        async for item in agent_routes._stream_with_keepalive(events_source()):
            items.append(item)
        return items
    finally:
        agent_routes._SSE_KEEPALIVE_INTERVAL_SECONDS = original


class StreamKeepaliveTests(unittest.TestCase):
    def test_events_pass_through_in_order(self):
        async def source():
            yield {"type": "start", "execution_id": "x"}
            yield {"type": "tool_call", "name": "co_optimized_backtest"}
            yield {"type": "done"}

        items = _run(_collect(source, interval=5.0))
        self.assertEqual([i.get("type") for i in items if i is not None],
                         ["start", "tool_call", "done"])
        self.assertNotIn(None, items)  # 无空闲 → 无心跳

    def test_idle_gap_emits_heartbeat_markers(self):
        async def source():
            yield {"type": "start"}
            await asyncio.sleep(0.25)  # 远大于心跳间隔 → 至少 2 个心跳
            yield {"type": "done"}

        items = _run(_collect(source, interval=0.1))
        heartbeats = sum(1 for i in items if i is None)
        self.assertGreaterEqual(heartbeats, 2)
        self.assertEqual(items[0], {"type": "start"})
        self.assertEqual(items[-1], {"type": "done"})

    def test_source_exception_becomes_error_event(self):
        async def source():
            yield {"type": "start"}
            raise RuntimeError("boom")

        items = _run(_collect(source, interval=5.0))
        types_seen = [i.get("type") for i in items if i is not None]
        self.assertEqual(types_seen, ["start", "error"])

    def test_producer_not_cancelled_on_normal_completion(self):
        """正常消费完毕后生产者生成器应正常走完 finally（而非被取消）。"""
        finished = {"producer": False}

        async def source():
            try:
                yield {"type": "start"}
                yield {"type": "done"}
            finally:
                finished["producer"] = True

        items = _run(_collect(source, interval=5.0))
        self.assertEqual([i.get("type") for i in items], ["start", "done"])
        self.assertTrue(finished["producer"])


if __name__ == "__main__":
    unittest.main()
