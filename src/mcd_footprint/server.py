#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
server.py —— 本地服务模式（仅用标准库）。

存在的唯一理由：**让 MCP_TOKEN 可以在页面里填写并立刻生效**。
生成的 HTML 是静态文件，浏览器无法直连 https://mcp.mcd.cn（跨域 + 需要 Bearer 鉴权），
因此由本机服务代持 Token 并代为调用 MCP，浏览器只与 127.0.0.1 通信。

接口：
    GET  /                  页面（每次请求都用当前数据重新渲染）
    GET  /api/state         当前状态：Token 是否已配置（脱敏）、数据来源、统计摘要
    POST /api/token         {token, endpoint?} 保存 Token 到本机
    DELETE /api/token       清除本机 Token
    GET  /api/footprint     当前足迹数据
    POST /api/refresh       {source?} 用当前 Token 重新拉取并重建足迹

安全边界：
    - 仅监听 127.0.0.1，不对外暴露；
    - /api/state 只返回脱敏 Token，任何接口都不回传明文；
    - Token 落盘在 ~/.mcd-footprint-map/token.json，不写入产物 HTML。
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .config import TokenStore, resolve_token
from .mcp_client import MCPError
from .pipeline import DATA_DIR, Options, build_footprint, default_source
from .render import render_html_string

OUTLINE_DEFAULT = os.path.join(DATA_DIR, "china-outline.json")


class FootprintApp:
    """持有当前足迹数据与 Token 状态，供 HTTP handler 使用。"""

    def __init__(self, source: str = "auto", state_path: Optional[str] = None):
        self.source = source
        self.state_path = state_path
        self.lock = threading.RLock()
        self.footprint: Dict[str, Any] = {}
        self.error: str = ""
        self.updated_at: str = ""
        self.refresh()

    # ---------------- 数据 ----------------

    def refresh(self, source: Optional[str] = None) -> Dict[str, Any]:
        src = source or self.source
        if src == "auto":
            src = default_source()
        if src == "mcp" and not resolve_token():
            self.error = "尚未配置 MCP_TOKEN，请在页面右上角「设置 Token」中填写。"
            return {"ok": False, "error": self.error}

        opt = Options(source=src, state=self.state_path, log=None)
        try:
            fp = build_footprint(opt)
        except MCPError as exc:
            self.error = f"MCP 调用失败：{exc}"
            return {"ok": False, "error": self.error}
        except Exception as exc:  # noqa: BLE001
            self.error = f"重建足迹失败：{exc}"
            return {"ok": False, "error": self.error}

        with self.lock:
            self.footprint = fp
            self.error = ""
            self.updated_at = fp.get("meta", {}).get("today", "")
        return {"ok": True, "source": src, "stats": fp.get("stats", {})}

    def state(self) -> Dict[str, Any]:
        store = TokenStore()
        st = store.public_state()
        stats = self.footprint.get("stats", {}) or {}
        st.update(
            {
                "server": True,
                "source": self.footprint.get("meta", {}).get("source", ""),
                "source_label": self.footprint.get("meta", {}).get("source_label", ""),
                "order_count": stats.get("order_count", 0),
                "lit_cities": stats.get("lit_cities", 0),
                "error": self.error,
            }
        )
        return st

    def render_page(self) -> str:
        with self.lock:
            fp = self.footprint or {"meta": {}, "stats": {}, "cities": [], "days": []}
            fp = dict(fp)
        meta = dict(fp.get("meta") or {})
        meta["server_mode"] = True
        fp["meta"] = meta
        return render_html_string(fp, OUTLINE_DEFAULT)


class _Handler(BaseHTTPRequestHandler):
    app: FootprintApp  # 由 make_server 注入

    # ---------------- 基础 ----------------

    def log_message(self, fmt: str, *args: Any) -> None:
        # 安静一点：只打印接口调用，不打印每个静态请求
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _html(self, text: str) -> None:
        self._send(200, text.encode("utf-8"), "text/html; charset=utf-8")

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    # ---------------- 路由 ----------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._html(self.app.render_page())
            elif path == "/api/state":
                self._json(self.app.state())
            elif path == "/api/footprint":
                self._json(self.app.footprint)
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"{exc}"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._body()
        try:
            if path == "/api/token":
                token = str(body.get("token") or "").strip()
                if not token:
                    self._json({"ok": False, "error": "Token 不能为空"}, 400)
                    return
                endpoint = body.get("endpoint") or None
                TokenStore().save(token, endpoint)
                saved = {
                    "ok": True,
                    "token_saved": True,          # 明确区分「已保存」与「取数是否成功」
                    "message": "Token 已保存到本机",
                    **self.app.state(),
                }
                # 保存后立刻尝试用它取数，让「保存」与「生效」是一件事
                if str(body.get("refresh", "1")) != "0":
                    res = self.app.refresh("mcp")
                    saved.update(res)
                self._json(saved)
                return

            if path == "/api/refresh":
                res = self.app.refresh(body.get("source") or None)
                self._json({**res, **self.app.state()}, 200 if res.get("ok") else 400)
                return

            self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"{exc}"}, 500)

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/token":
                TokenStore().clear()
                self.app.refresh("mock")
                self._json({"ok": True, "message": "已清除 Token", **self.app.state()})
                return
            self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"{exc}"}, 500)


def make_server(app: FootprintApp, host: str = "127.0.0.1", port: int = 8765):
    handler = type("Handler", (_Handler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)


def serve(
    source: str = "auto",
    host: str = "127.0.0.1",
    port: int = 8765,
    state_path: Optional[str] = None,
    open_browser: bool = True,
) -> None:
    app = FootprintApp(source=source, state_path=state_path)
    httpd = make_server(app, host, port)
    url = f"http://{host}:{port}/"
    print("=" * 62)
    print("  麦麦足迹地图 · 本地服务已启动")
    print(f"  访问：{url}")
    print("  在页面右上角「⚙ 设置 Token」填写你的 MCP_TOKEN 并保存，")
    print("  足迹会立即基于你自己的账号重新生成。")
    print("  按 Ctrl+C 停止。")
    print("=" * 62)
    if app.error:
        print(f"  [提示] {app.error}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[ok] 已停止。")
    finally:
        httpd.server_close()
