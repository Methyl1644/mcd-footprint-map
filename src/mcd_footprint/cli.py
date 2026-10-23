#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cli.py —— 「麦麦足迹地图」命令行入口。

用法示例：
    # 1) 启动本地服务（推荐）：浏览器里可直接填写并保存自己的 MCP_TOKEN
    python -m mcd_footprint --serve --port 8765
    #   然后打开 http://127.0.0.1:8765 ，点右上角「设置 Token」

    # 2) 真实 MCP 数据（需要 MCD_MCP_TOKEN 或已保存的 Token）
    export MCD_MCP_TOKEN=你的Token
    python -m mcd_footprint --source mcp --out out/footprint.html

    # 3) 本地 JSON（例如由 WorkBuddy 调用 MCP 工具后落盘的结果）
    python -m mcd_footprint --source file --input orders.json --out out/footprint.html

    # 4) 内置示例数据（无 Token / 无网络演示）
    python -m mcd_footprint --source mock --out out/footprint.html

Token 相关：
    python -m mcd_footprint --save-token 你的Token     # 保存到本机，之后默认生效
    python -m mcd_footprint --show-token               # 查看当前生效的 Token（脱敏）

可选参数：
    --enrich / --no-enrich      是否用 query-order 补齐门店地址（默认开启）
    --probe-mcp                 门店名解析不出城市时，尝试 query-nearby-stores 反查（默认关闭）
    --new-city-days N           无历史状态时，N 天内首次点亮视为新增（默认 30）
    --state PATH                已知城市状态文件（用于识别新增城市）
    --json-out PATH             同时导出聚合后的 JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .config import TokenStore, resolve_endpoint, resolve_token
from .mcp_client import MCPError
from .pipeline import DATA_DIR, Options, build_footprint, default_source
from .render import render_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def run(args: argparse.Namespace) -> int:
    # ---------- Token 管理 ----------
    if args.show_token:
        store = TokenStore()
        tok = resolve_token(args.token)
        print("Token 配置：", "已配置 " + TokenStore.mask(tok) if tok else "未配置")
        print("配置文件：", store.path)
        print("接入地址：", resolve_endpoint(args.endpoint))
        return 0

    if args.save_token is not None:
        store = TokenStore()
        token = args.save_token
        if not token:
            # 交互式输入：不回显，避免 Token 留在 shell 历史里
            import getpass

            print("请粘贴你的麦当劳 MCP Token（输入不回显，直接回车确认）：")
            if sys.stdin.isatty():
                token = (getpass.getpass("> ") or "").strip()
            else:
                token = (sys.stdin.readline() or "").strip()
        if not token:
            print("[error] Token 为空，未保存。", file=sys.stderr)
            return 2
        store.save(token, args.endpoint)
        print(f"[ok] Token 已保存到 {store.path}（{TokenStore.mask(token)}），后续运行默认生效。")
        print("[next] python -m mcd_footprint --source mcp --out out/footprint.html")
        print("[next] 或启动本地服务在页面里查看：python -m mcd_footprint --serve")
        return 0

    if args.clear_token:
        TokenStore().clear()
        print("[ok] 已清除本机保存的 Token。")
        return 0

    # ---------- 本地服务 ----------
    if args.serve:
        from .server import serve

        serve(
            source=args.source,
            host=args.host,
            port=args.port,
            state_path=args.state,
            open_browser=not args.no_open,
        )
        return 0

    # ---------- 一次性渲染 ----------
    opt = Options(
        source=args.source,
        input=args.input,
        token=args.token,
        endpoint=args.endpoint,
        enrich=args.enrich,
        max_enrich=args.max_enrich,
        probe_mcp=args.probe_mcp,
        probe_cities=args.probe_cities,
        new_city_days=args.new_city_days,
        state=args.state,
        centroids=args.centroids,
        outline=args.outline,
        overrides=args.overrides,
        today=args.today,
        log=lambda m: print("[pipeline] " + m),
    )

    try:
        footprint = build_footprint(opt)
    except MCPError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fp:
            json.dump(footprint, fp, ensure_ascii=False, indent=2)
        print(f"[out] 写出 JSON -> {args.json_out}")

    out = render_html(
        footprint,
        outline_path=args.outline or _default_path("china-outline.json"),
        out_path=args.out,
    )
    size_kb = os.path.getsize(out) / 1024
    print(f"[out] 写出 HTML -> {out}（{size_kb:.0f} KB）")

    if footprint["unresolved"]:
        print(
            f"[warn] {len(footprint['unresolved'])} 条记录无法判定城市，已列入 unresolved，"
            f"可在 data/city-overrides.json 中人工纠偏。",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcd-footprint-map",
        description="麦麦足迹地图：用吃麦当劳的记录点亮走过的城市",
    )
    p.add_argument("--source", choices=["mcp", "file", "mock", "auto"], default="auto",
                   help="数据来源（默认 auto：有 Token 走 MCP，否则用示例数据）")
    p.add_argument("--input", help="file/mock 模式的输入 JSON 路径")
    p.add_argument("--token", default=None, help="MCP Token（默认读环境变量，再读本机保存的 Token）")
    p.add_argument("--save-token", nargs="?", const="", default=None, metavar="TOKEN",
                   help="把 Token 保存到本机并退出；不带参数则以交互方式输入（不回显）")
    p.add_argument("--show-token", action="store_true", help="查看当前生效的 Token（脱敏）")
    p.add_argument("--clear-token", action="store_true", help="清除本机保存的 Token")
    p.add_argument("--endpoint", default=None, help="MCP 接入地址（默认 https://mcp.mcd.cn）")

    p.add_argument("--serve", action="store_true", help="启动本地服务（可在线设置 Token 并刷新数据）")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true", help="启动服务但不自动打开浏览器")

    p.add_argument("--enrich", dest="enrich", action="store_true", default=True)
    p.add_argument("--no-enrich", dest="enrich", action="store_false")
    p.add_argument("--max-enrich", type=int, default=40, help="最多补齐多少条订单详情")
    p.add_argument("--probe-mcp", action="store_true", help="用 query-nearby-stores 反查城市（较慢）")
    p.add_argument("--probe-cities", nargs="*", default=None, help="反查时指定的候选城市")
    p.add_argument("--new-city-days", type=int, default=30)
    p.add_argument("--state", default=None, help="已知城市状态文件（识别新增城市）")
    p.add_argument("--centroids", default=None)
    p.add_argument("--outline", default=None)
    p.add_argument("--overrides", default=_default_path("city-overrides.json"))
    p.add_argument("--today", default=None, help="指定『今天』（默认取 MCP 服务器时间或本机日期）")
    p.add_argument("--json-out", default=None)
    p.add_argument("--out", default=os.path.join(ROOT, "out", "footprint.html"))
    return p


def main(argv: Optional[List[str]] = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
