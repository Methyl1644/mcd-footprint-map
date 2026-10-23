#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generate_mock_data.py —— 生成内置示例订单数据（data/sample-orders.mock.json）。

重要说明：
  本文件产出的 **数据结构** 与真实 order-list 返回完全一致（字段名、类型、嵌套关系均对齐实测结果），
  但 **数据内容是合成的示例数据**，仅用于无 Token / 无网络时演示 Skill 效果。

真实数据请以 `python -m mcd_footprint --source mcp` 获取，切勿把示例数据当作真实消费记录。

用法：
    python tools/generate_mock_data.py --out data/sample-orders.mock.json
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List

# 门店样例：名称遵循麦当劳真实命名惯例「麦当劳<城市><商圈/路名>餐厅」
STORES: List[Dict[str, str]] = [
    {"city": "南京", "name": "麦当劳南京广州路餐厅", "code": "1990097", "addr": "广州路14号"},
    {"city": "南京", "name": "麦当劳南京青岛路餐厅", "code": "1990696", "addr": "青岛路33号"},
    {"city": "南京", "name": "麦当劳南京南大和园餐厅", "code": "1990356", "addr": "仙林大道168号164幢1室-1"},
    {"city": "苏州", "name": "麦当劳苏州观前街餐厅", "code": "2000451", "addr": "观前街118号"},
    {"city": "苏州", "name": "麦当劳苏州园区湖东餐厅", "code": "2000477", "addr": "星湖街328号"},
    {"city": "无锡", "name": "麦当劳无锡崇安寺餐厅", "code": "2000912", "addr": "人民中路139号"},
    {"city": "上海", "name": "麦当劳上海南京东路餐厅", "code": "1900123", "addr": "南京东路720号"},
    {"city": "上海", "name": "麦当劳上海陆家嘴餐厅", "code": "1900456", "addr": "陆家嘴环路1000号"},
    {"city": "杭州", "name": "麦当劳杭州湖滨银泰餐厅", "code": "2100211", "addr": "延安路98号"},
    {"city": "宁波", "name": "麦当劳宁波天一广场餐厅", "code": "2100555", "addr": "中山东路188号"},
    {"city": "合肥", "name": "麦当劳合肥淮河路餐厅", "code": "2200136", "addr": "淮河路步行街77号"},
    {"city": "武汉", "name": "麦当劳武汉楚河汉街餐厅", "code": "2400333", "addr": "楚河汉街1号"},
    {"city": "长沙", "name": "麦当劳长沙黄兴南路餐厅", "code": "2500777", "addr": "黄兴南路445号"},
    {"city": "广州", "name": "麦当劳广州北京路餐厅", "code": "2600111", "addr": "北京路295号"},
    {"city": "深圳", "name": "麦当劳深圳华强北餐厅", "code": "2600888", "addr": "华强北路1019号"},
    {"city": "成都", "name": "麦当劳成都春熙路餐厅", "code": "2800222", "addr": "春熙路步行街1号"},
    {"city": "重庆", "name": "麦当劳重庆解放碑餐厅", "code": "2900145", "addr": "民权路28号"},
    {"city": "西安", "name": "麦当劳西安钟楼餐厅", "code": "3000077", "addr": "东大街600号"},
    {"city": "北京", "name": "麦当劳北京王府井东街餐厅", "code": "1950482", "addr": "王府井大街东街8号"},
    {"city": "天津", "name": "麦当劳天津滨江道餐厅", "code": "1960333", "addr": "滨江道209号"},
    {"city": "青岛", "name": "麦当劳青岛台东餐厅", "code": "2070111", "addr": "台东三路58号"},
    {"city": "厦门", "name": "麦当劳厦门中山路餐厅", "code": "2130222", "addr": "中山路166号"},
    {"city": "昆明", "name": "麦当劳昆明南屏街餐厅", "code": "3110444", "addr": "南屏街4号"},
    {"city": "沈阳", "name": "麦当劳沈阳中街餐厅", "code": "1660555", "addr": "中街路128号"},
]

MENU: List[Dict[str, Any]] = [
    {"code": "1100", "name": "巨无霸", "price": 28.0, "subs": []},
    {"code": "1120", "name": "双层吉士汉堡", "price": 23.0, "subs": []},
    {"code": "1700", "name": "麦辣鸡翅2块", "price": 10.9, "subs": []},
    {"code": "4810", "name": "中薯条", "price": 11.0, "subs": []},
    {
        "code": "9900016335",
        "name": "芝香脆鸡扒堡早餐两件套",
        "price": 9.9,
        "subs": [{"code": "522000", "name": "芝香脆鸡扒堡"}, {"code": "520689", "name": "小杯鲜萃咖啡"}],
    },
    {
        "code": "9900015566",
        "name": "泰式炭烤风味猪猪堡随心配",
        "price": 14.9,
        "subs": [{"code": "521879", "name": "泰式炭烤风味猪猪堡"}, {"code": "4105", "name": "菠萝派"}],
    },
    {
        "code": "9900012387",
        "name": "中薯条买一送一",
        "price": 13.5,
        "subs": [{"code": "4810", "name": "中薯条", "quantity": 2}],
    },
    {"code": "1200", "name": "麦香鱼", "price": 15.0, "subs": []},
    {"code": "3600", "name": "板烧鸡腿堡", "price": 21.5, "subs": []},
    {"code": "5100", "name": "麦旋风", "price": 9.5, "subs": []},
]

STATUS_POOL = ["订单已完成", "订单已完成", "订单已完成", "订单已取消"]


def make_order(rng: random.Random, store: Dict[str, str], when: datetime) -> Dict[str, Any]:
    n_items = rng.choice([1, 1, 1, 2])
    items: List[Dict[str, Any]] = []
    total = 0.0
    for _ in range(n_items):
        m = rng.choice(MENU)
        qty = rng.choice([1, 1, 1, 2])
        total += m["price"] * qty
        sub = [
            {"productCode": s["code"], "name": s["name"], "quantity": s.get("quantity", 1)}
            for s in m["subs"]
        ]
        items.append(
            {
                "productCode": m["code"],
                "productName": m["name"],
                "quantity": qty,
                "comboItemList": sub,
            }
        )
    order_id = f"10{rng.randint(300000000, 999999999)}{rng.randint(10000000000000, 99999999999999)}"
    return {
        "orderId": order_id,
        "orderType": "1",
        "createTime": when.strftime("%Y-%m-%d %H:%M:%S"),
        "beType": "1",
        "beCode": "",
        "storeCode": store["code"],
        "storeName": store["name"],
        "orderStatus": rng.choice(STATUS_POOL),
        "orderProductList": items,
        "realTotalAmount": f"{round(total, 1)}",
        "_mockAddress": store["addr"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sample-orders.mock.json")
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--days", type=int, default=330, help="回溯天数")
    ap.add_argument("--count", type=int, default=58, help="订单条数")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    today = datetime(2026, 10, 22)
    orders: List[Dict[str, Any]] = []

    # 给每家门店一个"首次到访日"（这座城市被点亮的时间）。
    # 少数门店安排在最近一个月内首次出现，用于演示"新增城市高亮"。
    activation = {}
    for s in STORES:
        if rng.random() < 0.22:
            activation[s["code"]] = rng.randint(2, 25)      # 最近新点亮
        else:
            activation[s["code"]] = rng.randint(60, args.days)

    def pick_store(offset: int) -> Dict[str, str]:
        # 只能选"已经被点亮"的门店，模拟真实的足迹增长过程
        pool = [s for s in STORES if activation[s["code"]] >= offset]
        return rng.choice(pool) if pool else rng.choice(STORES)

    for _ in range(args.count):
        # 越接近今天，消费越密集（更符合真实分布）
        offset = int(abs(rng.gauss(0, 0.42)) * args.days)
        offset = min(offset, args.days)
        day = today - timedelta(days=offset)
        # 时段分布：午间/傍晚为主，留出一部分深夜
        slot = rng.random()
        if slot < 0.20:
            hour = rng.randint(21, 23)
        elif slot < 0.28:
            hour = rng.randint(0, 4)
        elif slot < 0.44:
            hour = rng.randint(7, 10)
        elif slot < 0.68:
            hour = rng.randint(11, 14)
        else:
            hour = rng.randint(17, 20)
        when = day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))
        store = pick_store(offset)
        orders.append(make_order(rng, store, when))

    orders.sort(key=lambda o: o["createTime"], reverse=True)
    payload = {
        "_notice": (
            "本文件为【合成示例数据】，字段结构与麦当劳 MCP order-list 真实返回完全一致，"
            "但内容非真实消费记录，仅用于无 Token / 无网络环境演示。真实数据请使用 --source mcp。"
        ),
        "success": True,
        "code": 200,
        "message": "请求成功",
        "data": {"list": orders},
    }
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    print(f"[ok] 写出 {args.out}，共 {len(orders)} 条示例订单")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
