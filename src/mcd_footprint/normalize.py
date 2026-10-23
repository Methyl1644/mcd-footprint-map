#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
normalize.py —— 把 MCP 原始订单归一化为统一记录结构。

统一记录（Record）字段：
  order_id      订单编码            <- order-list.orderId
  created_at    下单时间(ISO)       <- order-list.createTime / query-order.createTime
  store_code    门店编码            <- order-list.storeCode
  store_name    门店名称            <- order-list.storeName
  address       门店地址            <- query-order.storeAddress（可能缺失，见降级说明）
  city/province/lon/lat  城市与坐标  <- cities.CityResolver 解析
  city_source   城市来源（address/store_name/override/mcp_probe/unknown）
  status        订单状态            <- order-list.orderStatus
  take_way      取餐方式            <- query-order.takeWay
  amount        实付金额            <- realTotalAmount
  items[]       订单内容            <- orderProductList[].productName + comboItemList
  is_late_night 是否深夜（>=21:00） <- 由 created_at 推导，不臆造

关于「订单内容」：order-list 的 comboItemList 子元素字段是 name/quantity，
而 query-order 的 comboItemList 子元素字段是 itemName/itemQuantity —— 两者都要兼容。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

LATE_NIGHT_HOUR = 21  # 21:00 及之后视为深夜时段


@dataclass
class Item:
    name: str = ""
    quantity: int = 1
    subitems: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Record:
    order_id: str = ""
    created_at: str = ""          # "YYYY-MM-DD HH:MM:SS"
    date: str = ""                # "YYYY-MM-DD"
    time: str = ""                # "HH:MM"
    hour: int = 0
    is_late_night: bool = False
    store_code: str = ""
    store_name: str = ""
    address: str = ""
    city: Optional[str] = None
    province: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    adcode: Optional[int] = None
    city_source: str = "unknown"
    city_confidence: float = 0.0
    status: str = ""
    take_way: str = ""
    amount: float = 0.0
    items: List[Item] = field(default_factory=list)
    enriched: bool = False        # 是否成功用 query-order 补齐过详情

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["items"] = [i.to_dict() for i in self.items]
        return d


def _to_float(v: Any) -> float:
    try:
        return float(str(v).strip())
    except Exception:  # noqa: BLE001
        return 0.0


def _to_int(v: Any, default: int = 1) -> int:
    try:
        return int(float(str(v).strip()))
    except Exception:  # noqa: BLE001
        return default


def _parse_items(order_product_list: List[Dict[str, Any]]) -> List[Item]:
    """兼容 order-list(name/quantity) 与 query-order(itemName/itemQuantity) 两种子项字段名。"""
    items: List[Item] = []
    for p in order_product_list or []:
        name = str(p.get("productName") or "").strip()
        qty = _to_int(p.get("quantity"), 1)
        subs: List[str] = []
        for c in p.get("comboItemList") or []:
            sub_name = str(c.get("name") or c.get("itemName") or "").strip()
            sub_qty = _to_int(c.get("quantity") or c.get("itemQuantity"), 1)
            if not sub_name:
                continue
            subs.append(f"{sub_name}×{sub_qty}" if sub_qty > 1 else sub_name)
        items.append(Item(name=name, quantity=qty, subitems=subs))
    return items


def _parse_dt(create_time: str) -> Optional[datetime]:
    create_time = (create_time or "").strip()
    if not create_time:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(create_time, fmt)
        except Exception:  # noqa: BLE001
            continue
    try:
        return datetime.fromisoformat(create_time)
    except Exception:  # noqa: BLE001
        return None


def build_record(
    raw: Dict[str, Any],
    detail: Optional[Dict[str, Any]] = None,
    city_info: Optional[Dict[str, Any]] = None,
) -> Optional[Record]:
    """从 order-list 条目（+ 可选 query-order 详情）构建 Record。"""
    create_time = str(raw.get("createTime") or (detail or {}).get("createTime") or "").strip()
    dt = _parse_dt(create_time)
    if dt is None:
        return None

    store_name = str(raw.get("storeName") or (detail or {}).get("storeName") or "").strip()
    store_code = str(raw.get("storeCode") or "").strip()
    address = str((detail or {}).get("storeAddress") or "").strip()

    product_list = (detail or {}).get("orderProductList") or raw.get("orderProductList") or []

    rec = Record(
        order_id=str(raw.get("orderId") or "").strip(),
        created_at=dt.strftime("%Y-%m-%d %H:%M:%S"),
        date=dt.strftime("%Y-%m-%d"),
        time=dt.strftime("%H:%M"),
        hour=dt.hour,
        is_late_night=dt.hour >= LATE_NIGHT_HOUR,
        store_code=store_code,
        store_name=store_name,
        address=address,
        status=str(raw.get("orderStatus") or (detail or {}).get("orderStatus") or "").strip(),
        take_way=str((detail or {}).get("takeWay") or "").strip(),
        amount=_to_float(raw.get("realTotalAmount") or (detail or {}).get("realTotalAmount")),
        items=_parse_items(product_list),
        enriched=bool(detail),
    )
    if city_info:
        rec.city = city_info.get("city")
        rec.province = city_info.get("province")
        rec.lon = city_info.get("lon")
        rec.lat = city_info.get("lat")
        rec.adcode = city_info.get("adcode")
        rec.city_source = city_info.get("source", "unknown")
        rec.city_confidence = city_info.get("confidence", 0.0)
    return rec
