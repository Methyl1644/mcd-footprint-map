#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
aggregate.py —— 按地级市聚合消费记录，产出地图点亮数据与统计指标。

统计口径（与麦当劳 MCP 服务范围一致）：
  - 仅统计中国大陆地区（不含港澳台及海外）；
  - 粒度为地级市（含地区/自治州/盟/省直辖县级行政区）；
  - 北京/天津/上海/重庆四个直辖市各作为 1 个统计单元，不再细分市辖区；
  - city 为 None（无法判定）的记录不计入点亮，单独列入 unresolved。

「新增城市」判定：
  与上一次运行持久化的已知城市集合求差集；若无历史状态，则退化为
  "最近 N 天（默认 30 天）内首次点亮"的城市同样标记为新增。
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set

NEW_CITY_FALLBACK_DAYS = 30


def _date_diff_days(a: str, b: str) -> Optional[int]:
    """两个 YYYY-MM-DD 之间相差天数（a - b）。"""
    from datetime import date

    try:
        da = date.fromisoformat(a)
        db = date.fromisoformat(b)
    except Exception:  # noqa: BLE001
        return None
    return (da - db).days


class FootprintState:
    """持久化已知城市集合，用于识别「新增城市」。"""

    def __init__(self, path: str):
        self.path = path
        self.known: Set[str] = set()
        self.last_run: Optional[str] = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                self.known = set(data.get("known_cities") or [])
                self.last_run = data.get("last_run")
            except Exception:  # noqa: BLE001
                pass

    def save(self, cities: Iterable[str], today: str) -> None:
        self.known = set(self.known) | set(cities)
        self.last_run = today
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fp:
            json.dump(
                {"known_cities": sorted(self.known), "last_run": today},
                fp,
                ensure_ascii=False,
                indent=2,
            )


def aggregate(
    records: List[Any],
    resolver: Any,
    state: Optional[FootprintState] = None,
    today: str = "",
    new_city_days: int = NEW_CITY_FALLBACK_DAYS,
) -> Dict[str, Any]:
    """把 Record 列表聚合为 {cities, stores, stats, unresolved}。"""
    by_city: Dict[str, Dict[str, Any]] = {}
    by_store: Dict[str, Dict[str, Any]] = {}
    unresolved: List[Dict[str, Any]] = []

    for r in records:
        rec = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        if not rec.get("city"):
            unresolved.append(
                {
                    "order_id": rec.get("order_id"),
                    "store_name": rec.get("store_name"),
                    "address": rec.get("address"),
                    "date": rec.get("date"),
                    "source": rec.get("city_source"),
                }
            )
            continue

        city = rec["city"]
        c = by_city.setdefault(
            city,
            {
                "name": city,
                "province": rec.get("province"),
                "lon": rec.get("lon"),
                "lat": rec.get("lat"),
                "adcode": rec.get("adcode"),
                "visit_count": 0,
                "order_count": 0,
                "first_visit": rec["date"],
                "last_visit": rec["date"],
                "stores": {},
                "dates": set(),
                "late_night_count": 0,
                "amount": 0.0,
                "items": [],
            },
        )
        c["visit_count"] += 1
        c["order_count"] += 1
        c["amount"] += float(rec.get("amount") or 0)
        c["dates"].add(rec["date"])
        if rec.get("is_late_night"):
            c["late_night_count"] += 1
        if rec["date"] < c["first_visit"]:
            c["first_visit"] = rec["date"]
        if rec["date"] > c["last_visit"]:
            c["last_visit"] = rec["date"]

        store_key = rec.get("store_code") or rec.get("store_name") or "unknown"
        s = by_city[city]["stores"].setdefault(
            store_key,
            {
                "store_code": rec.get("store_code"),
                "store_name": rec.get("store_name"),
                "address": rec.get("address"),
                "city": city,
                "city_source": rec.get("city_source"),
                "lon": rec.get("lon"),
                "lat": rec.get("lat"),
                "order_count": 0,
                "first_visit": rec["date"],
                "last_visit": rec["date"],
                "items": [],
            },
        )
        s["order_count"] += 1
        if rec["date"] < s["first_visit"]:
            s["first_visit"] = rec["date"]
        if rec["date"] > s["last_visit"]:
            s["last_visit"] = rec["date"]

        bkey = f"{city}::{store_key}"
        bs = by_store.setdefault(bkey, dict(s))
        bs["order_count"] = s["order_count"]
        bs["first_visit"] = s["first_visit"]
        bs["last_visit"] = s["last_visit"]

        for it in rec.get("items") or []:
            nm = it.get("name")
            if nm:
                c["items"].append(nm)
                if nm not in s["items"]:
                    s["items"].append(nm)

    # ---------- 新增城市 ----------
    # 语义优先级：
    #   有历史状态 -> 严格差集（"上次之后新点亮的城市"），这才是"新增"的准确含义；
    #   无历史状态 -> 退化为"最近 new_city_days 天内首次点亮"，让首次运行也有高亮可看。
    new_cities: Set[str] = set()
    if state is not None and state.known:
        new_cities = set(by_city.keys()) - set(state.known)
    elif today:
        for name, c in by_city.items():
            diff = _date_diff_days(today, c["first_visit"])
            if diff is not None and 0 <= diff <= new_city_days:
                new_cities.add(name)

    cities_out: List[Dict[str, Any]] = []
    for name, c in by_city.items():
        c["dates"] = sorted(c["dates"])
        c["stores"] = sorted(c["stores"].values(), key=lambda x: -x["order_count"])
        # 保留出现频次最高的若干菜品用于详情展示
        freq: Dict[str, int] = defaultdict(int)
        for nm in c["items"]:
            freq[nm] += 1
        c["top_items"] = [n for n, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:6]]
        del c["items"]
        c["is_new"] = name in new_cities
        c["amount"] = round(c["amount"], 2)
        cities_out.append(c)
    cities_out.sort(key=lambda x: (x["first_visit"], x["name"]))

    provinces = sorted({c["province"] for c in cities_out if c.get("province")})
    total_cities = resolver.total_cities
    total_provinces = resolver.total_provinces

    stats = {
        "lit_cities": len(cities_out),
        "total_cities": total_cities,
        "city_coverage": round(len(cities_out) / total_cities * 100, 2) if total_cities else 0.0,
        "covered_provinces": len(provinces),
        "total_provinces": total_provinces,
        "province_coverage": (
            round(len(provinces) / total_provinces * 100, 2) if total_provinces else 0.0
        ),
        "provinces": provinces,
        "new_cities": sorted(new_cities),
        "order_count": sum(c["order_count"] for c in cities_out),
        "store_count": len({s["store_name"] for c in cities_out for s in c["stores"]}),
        "unresolved_count": len(unresolved),
        "late_night_count": sum(c["late_night_count"] for c in cities_out),
        "date_range": (
            {
                "start": min((c["first_visit"] for c in cities_out), default=""),
                "end": max((c["last_visit"] for c in cities_out), default=""),
            }
            if cities_out
            else {"start": "", "end": ""}
        ),
    }

    return {
        "cities": cities_out,
        "stats": stats,
        "unresolved": unresolved,
    }
