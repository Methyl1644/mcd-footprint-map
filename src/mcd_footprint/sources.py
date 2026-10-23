#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sources.py —— 三种数据来源：mcp（真实调用）/ file（本地 JSON）/ mock（内置样例）。

所有来源最终都产出 **原始 order-list 结构** 的记录列表，
再由 normalize.build_record 统一归一化，保证后续逻辑与来源无关。

字段结构严格对齐实测的 order-list 返回（不臆造字段）：
{
  "orderId": str, "orderType": str, "createTime": str,
  "beType": str, "beCode": str, "storeCode": str, "storeName": str,
  "orderStatus": str,
  "orderProductList": [{"productCode","productName","quantity","comboItemList":[{"productCode","name","quantity"}]}],
  "realTotalAmount": str
}
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple


def _as_order_list(payload: Any) -> List[Dict[str, Any]]:
    """把多种可能的 JSON 形态统一成 order-list 条目列表。"""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("list"), list):
            return [x for x in payload["list"] if isinstance(x, dict)]
        if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("list"), list):
            return [x for x in payload["data"]["list"] if isinstance(x, dict)]
        # 单条订单
        if "orderId" in payload:
            return [payload]
    return []


def load_from_file(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return _as_order_list(payload)


def load_mock(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """加载内置样例数据（结构与真实 order-list 一致，内容为合成的示例数据）。"""
    if path is None:
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "sample-orders.mock.json",
        )
    return load_from_file(path)


def load_from_mcp(
    client: Any,
    enrich: bool = True,
    max_enrich: int = 40,
    on_progress=None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """调用真实 MCP：order-list 拿列表，query-order 逐条补齐门店地址。

    返回 (orders, meta)。meta 记录补齐成功率等，用于透明展示降级情况。

    降级说明（实测）：
      - order-list 无分页参数，返回条数由服务端决定；
      - query-order 对部分历史订单返回 code=610303「订单号不存在！」，此处容错跳过，
        该订单将退化为「用门店名推断城市」。
    """
    raw_orders = client.order_list()
    meta: Dict[str, Any] = {
        "order_list_count": len(raw_orders),
        "enrich_attempted": 0,
        "enrich_ok": 0,
        "enrich_failed": 0,
        "enrich_skipped": 0,
        "now_time": None,
    }

    if not enrich:
        meta["enrich_skipped"] = len(raw_orders)
        return raw_orders, meta

    total = min(len(raw_orders), max_enrich)
    for i, o in enumerate(raw_orders[:total]):
        meta["enrich_attempted"] += 1
        if on_progress:
            on_progress(i + 1, total)
        detail = client.query_order(o.get("orderId", ""))
        if detail:
            o["_detail"] = detail
            meta["enrich_ok"] += 1
        else:
            meta["enrich_failed"] += 1
    meta["enrich_skipped"] = len(raw_orders) - total

    try:
        meta["now_time"] = client.now_time()
    except Exception:  # noqa: BLE001
        pass
    return raw_orders, meta
