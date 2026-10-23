#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
narrative.py —— 时间轴、当日回忆与深夜追问。

设计约束（严格遵守）：
  - 只陈述数据中存在的事实：门店名、地址、下单时间、订单内容。
  - 深夜（21:00 及之后）记录追加一句「轻松、克制」的辅助性追问，
    用于唤起回忆，**不臆造任何事实**（不猜原因、不编心情、不编同行人）。
  - 追问句从固定词库中按 (日期+门店) 稳定选取，保证同一天多次渲染结果一致。
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

LATE_NIGHT_HOUR = 21

# 深夜追问词库：均为开放式、无事实预设的问句，语气克制
LATE_NIGHT_PROMPTS = [
    "那天那么晚在想什么呢？",
    "这么晚的一顿，还记得为什么出门吗？",
    "夜深了还亮着灯的那家店，现在还在吗？",
    "那天回家路上，应该挺安静的吧？",
    "这么晚吃的这顿，是加班的尾巴还是夜宵的开头？",
    "那只是一次普通的深夜，还是有点什么不一样？",
]

# 白天不带追问，只给出中性提示（不臆造）
DAY_LABELS = [
    (5, 10, "清晨"),
    (10, 14, "午间"),
    (14, 17, "下午"),
    (17, 21, "傍晚"),
    (21, 24, "深夜"),
    (0, 5, "凌晨"),
]


def time_slot(hour: int) -> str:
    for start, end, label in DAY_LABELS:
        if start <= hour < end:
            return label
    return "深夜"


def _stable_index(seed: str, n: int) -> int:
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % n


def late_night_prompt(rec: Dict[str, Any]) -> str:
    """为深夜记录生成一句稳定、克制的追问。非深夜返回空串。"""
    if not rec.get("is_late_night"):
        return ""
    seed = f"{rec.get('date','')}|{rec.get('time','')}|{rec.get('store_name','')}"
    return LATE_NIGHT_PROMPTS[_stable_index(seed, len(LATE_NIGHT_PROMPTS))]


def build_timeline(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按日期倒序聚合：{date, weekday, records[], stores[], items[], late_night[]}。"""
    import datetime as _dt

    buckets: Dict[str, Dict[str, Any]] = {}
    for r in records:
        d = r.get("date")
        if not d:
            continue
        b = buckets.setdefault(
            d,
            {
                "date": d,
                "weekday": "",
                "records": [],
                "stores": [],
                "items": [],
                "late_night": [],
                "city": None,
                "order_count": 0,
                "amount": 0.0,
            },
        )
        b["records"].append(r)
        b["order_count"] += 1
        b["amount"] += float(r.get("amount") or 0)
        if r.get("store_name") and r["store_name"] not in b["stores"]:
            b["stores"].append(r["store_name"])
        if r.get("city") and not b["city"]:
            b["city"] = r["city"]
        for it in r.get("items") or []:
            nm = it.get("name")
            if nm and nm not in b["items"]:
                b["items"].append(nm)
        if r.get("is_late_night"):
            b["late_night"].append(r)

    out: List[Dict[str, Any]] = []
    for d, b in buckets.items():
        try:
            dt = _dt.date.fromisoformat(d)
            b["weekday"] = "周一 周二 周三 周四 周五 周六 周日".split()[dt.weekday()]
        except Exception:  # noqa: BLE001
            b["weekday"] = ""
        b["amount"] = round(b["amount"], 2)
        b["records"].sort(key=lambda x: x.get("created_at", ""))
        out.append(b)
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def build_day_detail(day: Dict[str, Any]) -> Dict[str, Any]:
    """把某一天的时间轴条目展开成「当日回忆」结构。"""
    memories: List[Dict[str, Any]] = []
    for r in day.get("records", []):
        prompt = late_night_prompt(r)
        memories.append(
            {
                "time": r.get("time"),
                "hour": r.get("hour"),
                "slot": time_slot(int(r.get("hour") or 0)),
                "store_name": r.get("store_name"),
                "store_code": r.get("store_code"),
                "address": r.get("address"),
                "city": r.get("city"),
                "city_source": r.get("city_source"),
                "status": r.get("status"),
                "take_way": r.get("take_way"),
                "amount": r.get("amount"),
                "items": r.get("items") or [],
                "is_late_night": bool(r.get("is_late_night")),
                "late_night_prompt": prompt,
                "order_id": r.get("order_id"),
            }
        )
    return {
        "date": day.get("date"),
        "weekday": day.get("weekday"),
        "city": day.get("city"),
        "stores": day.get("stores"),
        "order_count": day.get("order_count"),
        "amount": day.get("amount"),
        "memories": memories,
        "has_late_night": bool(day.get("late_night")),
    }


def build_all_days(timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [build_day_detail(d) for d in timeline]
