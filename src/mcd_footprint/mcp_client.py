#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mcp_client.py —— 麦当劳 MCP Server（Streamable HTTP）最小可用客户端。

严格依据官方接入文档实现，不臆造任何接口：
  - 接入地址：https://mcp.mcd.cn
  - 传输协议：Streamable HTTP
  - 鉴权：请求头 Authorization: Bearer <MCP_TOKEN>
  - 限流：每个 Token 每分钟最多 600 次请求，超限返回 429

调用流程（JSON-RPC 2.0）：
  1. initialize            -> 服务端返回 Mcp-Session-Id
  2. notifications/initialized（通知，无 id）
  3. tools/call            -> { name, arguments }

本模块只做「连接 + 调用 + 解析」，不含任何业务逻辑。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

DEFAULT_ENDPOINT = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"

# 本 Skill 实际会用到的工具（与 docs/CAPABILITY_MATRIX.md 保持一致）
TOOL_ORDER_LIST = "order-list"
TOOL_QUERY_ORDER = "query-order"
TOOL_NEARBY_STORES = "query-nearby-stores"
TOOL_NOW_TIME = "now-time-info"
TOOL_MALL_ORDER_LIST = "mall-order-list"


class MCPError(RuntimeError):
    """MCP 调用错误。"""

    def __init__(self, message: str, code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.code = code
        self.payload = payload


def _extract_json(text: str) -> Any:
    """从工具返回的 text 中稳健提取 JSON。

    实测发现部分工具（如 query-order）的 text 会在 JSON 前面附加一段提示语，
    因此不能直接 json.loads 整段，需要从第一个 '{' 起做括号配平扫描。
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass

    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:  # noqa: BLE001
                    return None
    return None


def _parse_sse(text: str) -> Any:
    """解析 text/event-stream 响应，取最后一个 data: 行中的 JSON-RPC 消息。"""
    last: Any = None
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload in ("[DONE]", ""):
            continue
        try:
            last = json.loads(payload)
        except Exception:  # noqa: BLE001
            continue
    return last


class McpMcdClient:
    """麦当劳 MCP Server 客户端。"""

    def __init__(
        self,
        token: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 30.0,
        min_interval: float = 0.12,
        max_retries: int = 3,
    ):
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "").strip()
        if not self.token:
            raise MCPError(
                "缺少 MCP Token：请设置环境变量 MCD_MCP_TOKEN，"
                "或参考 mcp-config.example.json 申请 Token 后传入。"
            )
        self.endpoint = (endpoint or os.environ.get("MCD_MCP_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._session_id: Optional[str] = None
        self._last_call = 0.0
        self._initialized = False

    # ---------------- 底层传输 ----------------

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
            headers["Mcp-Protocol-Version"] = PROTOCOL_VERSION

        # 简单限流：控制最小调用间隔，避免 429
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)

        req = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                    if sid:
                        self._session_id = sid
                    raw = resp.read().decode("utf-8", errors="replace")
                self._last_call = time.time()
                ctype = ""
                try:
                    ctype = (resp.headers.get("Content-Type") or "").lower()
                except Exception:  # noqa: BLE001
                    pass
                if "text/event-stream" in ctype:
                    parsed = _parse_sse(raw)
                    if parsed is not None:
                        return parsed
                try:
                    return json.loads(raw)
                except Exception:  # noqa: BLE001
                    parsed = _parse_sse(raw)
                    if parsed is not None:
                        return parsed
                    raise MCPError(f"无法解析 MCP 响应：{raw[:300]}", payload=raw)
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:300]
                except Exception:  # noqa: BLE001
                    pass
                if exc.code == 429 and attempt < self.max_retries - 1:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                last_err = MCPError(
                    f"MCP HTTP {exc.code}（401=Token 无效/过期，429=触发限流）: {detail}",
                    code=exc.code,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                time.sleep(1.2 * (attempt + 1))
        raise last_err or MCPError("MCP 调用失败")

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        res = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "mcd-footprint-map", "version": "1.0.0"},
                },
            }
        )
        if "error" in res:
            raise MCPError(f"initialize 失败: {res['error']}")
        # 通知（无 id），失败可忽略
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        except Exception:  # noqa: BLE001
            pass
        self._initialized = True

    # ---------------- 工具调用 ----------------

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """调用 MCP 工具，返回解析后的业务 data（失败时抛出 MCPError）。"""
        self._ensure_initialized()
        res = self._post(
            {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000) % 2_000_000_000,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        if "error" in res:
            raise MCPError(f"tools/call {name} 失败: {res['error']}", payload=res)

        result = res.get("result", {})
        if result.get("isError"):
            raise MCPError(f"工具 {name} 返回错误: {result}", payload=result)

        for item in result.get("content", []) or []:
            if item.get("type") != "text":
                continue
            parsed = _extract_json(item.get("text", ""))
            if isinstance(parsed, dict):
                # 统一信封：{success, code, message, data}
                if "success" in parsed:
                    if not parsed.get("success"):
                        raise MCPError(
                            f"工具 {name} 业务失败 code={parsed.get('code')} "
                            f"message={parsed.get('message')}",
                            code=parsed.get("code"),
                            payload=parsed,
                        )
                    return parsed.get("data")
                return parsed
        # 非 JSON 文本结果
        texts = [c.get("text", "") for c in result.get("content", []) or []]
        return "\n".join(t for t in texts if t)

    # ---------------- 语义化封装 ----------------

    def order_list(self) -> list:
        """历史订单（非商城）。实测返回 data.list。

        注意：order-list 无分页入参，返回条数由服务端决定（实测 10 条），
        且【不含门店地址/城市/坐标】字段 —— 需在 query-order 中补齐。
        """
        data = self.call_tool(TOOL_ORDER_LIST, {})
        if isinstance(data, dict):
            return data.get("list") or []
        return data or []

    def query_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """订单详情。含 storeAddress（门店地址）。

        实测：部分历史订单会返回 code=610303「订单号不存在！」，调用方必须容错降级。
        """
        try:
            data = self.call_tool(TOOL_QUERY_ORDER, {"orderId": str(order_id)})
        except MCPError:
            return None
        return data if isinstance(data, dict) else None

    def now_time(self) -> Optional[Dict[str, Any]]:
        """服务器当前时间（用于对齐"今天"的时区口径）。"""
        try:
            data = self.call_tool(TOOL_NOW_TIME, {})
        except MCPError:
            return None
        return data if isinstance(data, dict) else None

    def nearby_stores(self, city: str, keyword: str, be_type: int = 1) -> list:
        """按城市 + 关键词查询门店。

        实测返回 address / distance，但 longitude 与 latitude 恒为 0.0，
        无法用于地图打点 —— 详见 docs/CAPABILITY_MATRIX.md 的降级说明。
        """
        try:
            data = self.call_tool(
                TOOL_NEARBY_STORES,
                {"beType": be_type, "searchType": 2, "city": city, "keyword": keyword},
            )
        except MCPError:
            return []
        return data if isinstance(data, list) else []
