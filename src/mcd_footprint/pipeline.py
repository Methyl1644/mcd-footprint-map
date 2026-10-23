#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pipeline.py —— 「取数 → 归一化 → 城市解析 → 聚合 → 时间轴」的完整流水线。

CLI 与本地服务（server.py）共用同一条流水线，保证两条入口产出的数据结构完全一致。

定位逻辑（保持不变，见 cities.CityResolver）：
    订单 → 订单所属门店（storeCode / storeName）
         → query-order 补齐 storeAddress
         → 以「门店名」为主、「地址」为辅匹配地级市
         → 取地级行政中心坐标打点
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from .aggregate import FootprintState, aggregate
from .cities import CityResolver
from .config import resolve_endpoint, resolve_token
from .mcp_client import McpMcdClient, MCPError
from .narrative import build_all_days, build_timeline
from .normalize import build_record
from .sources import load_from_file, load_from_mcp, load_mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA_DIR = os.path.join(ROOT, "data")

MOCK_DISCLAIMER = (
    "当前为【内置示例数据】：字段结构与 MCP order-list 真实返回一致，但内容为合成的演示数据，"
    "非真实消费记录。在设置面板填入自己的 MCP_TOKEN 并保存后即可切换为真实数据。"
)
MCP_DISCLAIMER = (
    "数据来自麦当劳 MCP 真实接口（order-list + query-order）。"
    "order-list 不返回地址/城市/经纬度，城市由门店名与门店地址推断，"
    "坐标取自地级行政中心（MCP 的 longitude/latitude 实测恒为 0.0）。"
)


@dataclass
class Options:
    """流水线参数（CLI 与 server 共用）。"""

    source: str = "mock"                     # mcp / file / mock / auto
    input: Optional[str] = None
    token: Optional[str] = None
    endpoint: Optional[str] = None
    enrich: bool = True
    max_enrich: int = 40
    probe_mcp: bool = False
    probe_cities: Optional[List[str]] = None
    new_city_days: int = 30
    state: Optional[str] = None
    centroids: Optional[str] = None
    outline: Optional[str] = None
    overrides: Optional[str] = None
    today: Optional[str] = None
    log: Optional[Callable[[str], None]] = field(default=None, repr=False)

    def say(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def paths(self) -> Dict[str, str]:
        return {
            "centroids": self.centroids or os.path.join(DATA_DIR, "city-centroids.json"),
            "outline": self.outline or os.path.join(DATA_DIR, "china-outline.json"),
            "overrides": self.overrides or os.path.join(DATA_DIR, "city-overrides.json"),
        }


def default_source() -> str:
    """auto 模式：有 Token 就走真实 MCP，否则退回示例数据。"""
    return "mcp" if resolve_token() else "mock"


def build_footprint(opt: Options) -> Dict[str, Any]:
    """执行完整流水线，返回可直接渲染的 footprint 字典。"""
    p = opt.paths()
    source = opt.source
    if source == "auto":
        source = default_source()

    meta: Dict[str, Any] = {"source": source}
    client: Optional[McpMcdClient] = None

    # ---------- 1. 取数 ----------
    if source == "mcp":
        token = resolve_token(opt.token)
        try:
            client = McpMcdClient(token=token, endpoint=resolve_endpoint(opt.endpoint))
        except MCPError as exc:
            raise MCPError(str(exc))
        raw_orders, m = load_from_mcp(client, enrich=opt.enrich, max_enrich=opt.max_enrich)
        meta.update(m)
        meta["source_label"] = "麦当劳 MCP（真实接口）"
        meta["disclaimer"] = MCP_DISCLAIMER
    elif source == "file":
        if not opt.input:
            raise ValueError("--source file 需要 --input 指定 JSON 文件")
        raw_orders = load_from_file(opt.input)
        meta["source_label"] = f"本地文件 {os.path.basename(opt.input)}"
        meta["disclaimer"] = (
            "数据来自本地 JSON 文件，结构与 MCP order-list 对齐；"
            "若文件由真实 MCP 结果导出则为真实数据。"
        )
    else:
        raw_orders = load_mock(opt.input)
        meta["source_label"] = "内置示例数据（mock）"
        meta["disclaimer"] = MOCK_DISCLAIMER

    if not raw_orders:
        raise RuntimeError("未取到任何订单记录")
    opt.say(f"取到 {len(raw_orders)} 条原始订单（source={source}）")

    # ---------- 2. 归一化 + 城市解析 ----------
    resolver = CityResolver(centroids_path=p["centroids"], overrides_path=p["overrides"])
    records = []
    unresolved_names = 0
    for o in raw_orders:
        detail = o.get("_detail")
        info = resolver.resolve(
            store_name=o.get("storeName", ""),
            address=(detail or {}).get("storeAddress", o.get("_mockAddress", "")),
            store_code=o.get("storeCode", ""),
            probe_cities=opt.probe_cities if opt.probe_mcp else None,
            client=client if opt.probe_mcp else None,
        )
        rec = build_record(o, detail=detail, city_info=info)
        if rec is None:
            continue
        if detail is None and o.get("_mockAddress"):
            rec.address = o["_mockAddress"]
            rec.enriched = True
        if not info.get("city"):
            unresolved_names += 1
        records.append(rec)
    opt.say(f"归一化 {len(records)} 条；无法判定城市 {unresolved_names} 条")

    # ---------- 3. 聚合 ----------
    today = opt.today or (meta.get("now_time") or {}).get("date") or date.today().isoformat()
    state = FootprintState(opt.state) if opt.state else None
    agg = aggregate(records, resolver, state=state, today=today, new_city_days=opt.new_city_days)
    if state is not None:
        state.save([c["name"] for c in agg["cities"]], today)

    # ---------- 4. 时间轴 / 当日回忆 ----------
    rec_dicts = [r.to_dict() for r in records]
    days = build_all_days(build_timeline(rec_dicts))

    meta["today"] = today
    if source == "mcp":
        meta["source_note"] = f"order-list {meta.get('order_list_count', 0)} 条"

    footprint = {
        "meta": meta,
        "stats": agg["stats"],
        "cities": agg["cities"],
        "days": days,
        "unresolved": agg["unresolved"],
    }
    opt.say(
        f"点亮 {agg['stats']['lit_cities']} 座城市 / {agg['stats']['total_cities']}，"
        f"覆盖 {agg['stats']['covered_provinces']} 个省份，"
        f"新增 {len(agg['stats']['new_cities'])} 座"
    )
    return footprint
