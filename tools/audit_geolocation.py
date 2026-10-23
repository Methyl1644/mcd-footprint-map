#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
audit_geolocation.py —— 定位逻辑体检。

回答一个问题：「订单 → 门店 → 门店名/地址匹配城市」这条链路，当前是否完整可用？

做法：把数据源里的**每一条订单**都过一遍真实解析链路，统计
  - 解析成功率
  - 各定位来源（门店名 / 门店地址 / 人工纠偏 / MCP 反查）的占比
  - 无法定位的订单清单（可据此补 data/city-overrides.json）
  - 每座城市是否有坐标（没坐标就无法在地图上打点）

用法：
    python tools/audit_geolocation.py --source mock
    python tools/audit_geolocation.py --source mcp        # 需要 Token
    python tools/audit_geolocation.py --source file --input orders.json

退出码：0 = 全部订单都能定位；1 = 存在无法定位的订单（会打印清单）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mcd_footprint.cities import CityResolver  # noqa: E402
from mcd_footprint.config import resolve_token  # noqa: E402
from mcd_footprint.mcp_client import McpMcdClient  # noqa: E402
from mcd_footprint.sources import load_from_file, load_from_mcp, load_mock  # noqa: E402

DATA = os.path.join(ROOT, "data")
SRC_LABEL = {
    "store_name": "门店名",
    "address": "门店地址",
    "override": "人工纠偏",
    "mcp_probe": "MCP 反查",
    "unknown": "未识别",
    "excluded": "不计入（港澳台/海外）",
}


def collect(source: str, input_path: str | None, enrich: bool) -> List[Dict[str, Any]]:
    if source == "mcp":
        client = McpMcdClient(token=resolve_token())
        orders, meta = load_from_mcp(client, enrich=enrich)
        print(f"MCP：order-list {meta['order_list_count']} 条，"
              f"详情补齐成功 {meta['enrich_ok']} / 尝试 {meta['enrich_attempted']}")
        return orders
    if source == "file":
        return load_from_file(input_path)
    return load_mock(input_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mock", "file", "mcp"], default="mock")
    ap.add_argument("--input", default=None)
    ap.add_argument("--no-enrich", action="store_true")
    args = ap.parse_args()

    orders = collect(args.source, args.input, enrich=not args.no_enrich)
    if not orders:
        print("没有可取到的订单。")
        return 1
    print(f"共 {len(orders)} 条订单，开始逐条解析城市…\n")

    r = CityResolver(
        centroids_path=os.path.join(DATA, "city-centroids.json"),
        overrides_path=os.path.join(DATA, "city-overrides.json"),
    )

    src_counter: Counter = Counter()
    unresolved: List[Dict[str, str]] = []
    city_orders: Dict[str, int] = defaultdict(int)
    no_coord: List[str] = []

    for o in orders:
        detail = o.get("_detail") or {}
        store = str(o.get("storeName") or "").strip()
        addr = str(detail.get("storeAddress") or o.get("_mockAddress") or "").strip()
        code = str(o.get("storeCode") or "").strip()
        info = r.resolve(store_name=store, address=addr, store_code=code)
        src_counter[info["source"]] += 1
        if not info.get("city"):
            unresolved.append({"store": store, "code": code, "address": addr,
                               "source": info["source"]})
            continue
        city_orders[info["city"]] += 1
        if info.get("lon") is None or info.get("lat") is None:
            no_coord.append(info["city"])

    total = len(orders)
    ok = total - len(unresolved)
    print("—" * 60)
    print(f"可定位：{ok}/{total}（{ok / total * 100:.1f}%）")
    print("定位来源分布：")
    for k, n in src_counter.most_common():
        print(f"  {SRC_LABEL.get(k, k):<16} {n:>4} 条  {n / total * 100:5.1f}%")
    print(f"\n解析出的城市 {len(city_orders)} 座：" +
          "、".join(sorted(city_orders)[:20]) + ("…" if len(city_orders) > 20 else ""))
    if no_coord:
        print(f"[严重] {len(set(no_coord))} 座城市缺坐标，无法打点：{sorted(set(no_coord))}")
    else:
        print("坐标：全部城市均有经纬度 ✓")

    if unresolved:
        print(f"\n[待处理] {len(unresolved)} 条订单无法定位（已排除在点亮之外）：")
        seen = set()
        for u in unresolved:
            key = (u["store"], u["code"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  - 门店“{u['store']}”(code={u['code']}) 地址“{u['address']}” [{u['source']}]")
        print("\n处理方式：把门店编码/门店名 → 城市 写进 data/city-overrides.json，"
              "例如 {\"storeCodes\": {\"1990398\": \"南京市\"}}")
        return 1

    print("\n结论：定位链路完整可用 —— 全部订单都能判定城市且都有坐标。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
