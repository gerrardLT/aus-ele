"""天枢 MCP 集成包（2026-08-15）。

config.py  — 服务器清单与启用判定
client.py  — McpGateway：stdio/http 连接管理 + 健康状态机 + 优雅降级
adapter.py — 把 MCP 工具注册进既有 ToolRegistry（async executor 包装）
"""
