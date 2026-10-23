#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_pipeline.py —— 最小验证（仅用标准库 unittest，无需 pytest）。

覆盖：
  1. 城市解析：门店名锚定匹配、地址「市」字约束（防止路名误判）
  2. 聚合统计：点亮城市数、覆盖率、新增城市差分
  3. 深夜追问：21:00 触发、措辞克制、结果稳定
  4. 渲染：占位符替换、JS 安全转义
  5. 端到端：mock 数据跑通全链路

运行：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mcd_footprint.aggregate import FootprintState, aggregate  # noqa: E402
from mcd_footprint.cities import CityResolver  # noqa: E402
from mcd_footprint.narrative import build_all_days, build_timeline, late_night_prompt  # noqa: E402
from mcd_footprint.normalize import build_record  # noqa: E402
from mcd_footprint.render import render_html  # noqa: E402
from mcd_footprint.sources import load_mock  # noqa: E402

DATA = os.path.join(ROOT, "data")
CENTROIDS = os.path.join(DATA, "city-centroids.json")
OUTLINE = os.path.join(DATA, "china-outline.json")


def _rec(date: str, hour: int, store: str, city: str, province: str = "江苏省", **kw):
    raw = {
        "orderId": "T" + date.replace("-", "") + str(hour),
        "createTime": f"{date} {hour:02d}:30:00",
        "storeCode": kw.pop("store_code", "0001"),
        "storeName": store,
        "orderStatus": "订单已完成",
        "orderProductList": [
            {"productCode": "1100", "productName": "巨无霸", "quantity": 1, "comboItemList": []}
        ],
        "realTotalAmount": "28",
    }
    info = {
        "city": city,
        "province": province,
        "lon": 118.7,
        "lat": 32.0,
        "adcode": 320100,
        "source": "store_name",
        "confidence": 0.9,
    }
    return build_record(raw, detail=None, city_info=info)


class TestCityResolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = CityResolver(CENTROIDS, os.path.join(DATA, "city-overrides.json"))

    def test_store_name_anchored(self):
        """门店名：剥去品牌前缀后城市名位于开头。"""
        self.assertEqual(self.r.resolve(store_name="麦当劳南京广州路餐厅")["city"], "南京市")
        self.assertEqual(self.r.resolve(store_name="麦当劳广州北京路餐厅")["city"], "广州市")
        self.assertEqual(self.r.resolve(store_name="麦当劳厦门中山路餐厅")["city"], "厦门市")
        self.assertEqual(self.r.resolve(store_name="麦当劳重庆解放碑餐厅")["city"], "重庆市")

    def test_road_name_not_misread(self):
        """回归：路名不得被误判为城市（广州路≠广州市，中山路≠中山市，延安路≠延安市）。"""
        self.assertNotEqual(self.r.resolve(address="广州路14号")["city"], "广州市")
        self.assertNotEqual(self.r.resolve(address="中山路166号")["city"], "中山市")
        self.assertNotEqual(self.r.resolve(address="延安路98号")["city"], "延安市")

    def test_address_requires_city_suffix(self):
        """地址含显式市名时才命中。"""
        self.assertEqual(
            self.r.resolve(store_name="某某餐厅", address="南京市玄武区珠江路2-5号")["city"], "南京市"
        )

    def test_override_priority(self):
        """人工纠偏优先级最高。"""
        self.assertEqual(self.r.resolve(store_code="1990398", store_name="无法识别的店")["city"], "南京市")

    def test_hk_macao_taiwan_excluded(self):
        """港澳台及海外不计入统计。"""
        out = self.r.resolve(store_name="麦当劳香港铜锣湾餐厅")
        self.assertIsNone(out["city"])
        self.assertEqual(out["source"], "excluded")

    def test_totals(self):
        self.assertEqual(self.r.total_provinces, 31)
        self.assertGreater(self.r.total_cities, 330)


class TestAggregate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = CityResolver(CENTROIDS)

    def test_stats_and_new_city_diff(self):
        recs = [
            _rec("2026-10-01", 12, "麦当劳南京广州路餐厅", "南京市"),
            _rec("2026-10-02", 22, "麦当劳苏州观前街餐厅", "苏州市", "江苏省"),
            _rec("2026-10-02", 9, "麦当劳南京广州路餐厅", "南京市"),
        ]
        agg = aggregate(recs, self.resolver, today="2026-10-22")
        s = agg["stats"]
        self.assertEqual(s["lit_cities"], 2)
        self.assertEqual(s["order_count"], 3)
        self.assertEqual(s["covered_provinces"], 1)
        self.assertEqual(s["late_night_count"], 1)
        self.assertAlmostEqual(s["city_coverage"], round(2 / self.resolver.total_cities * 100, 2))
        self.assertEqual(set(s["new_cities"]), {"南京市", "苏州市"})  # 30 天内首亮 => 新增

        # 第二次运行：state 中已有城市 => 不再标记为新增
        with tempfile.TemporaryDirectory() as td:
            st_path = os.path.join(td, "state.json")
            st = FootprintState(st_path)
            st.save(["南京市", "苏州市"], "2026-10-22")
            agg2 = aggregate(recs, self.resolver, state=FootprintState(st_path), today="2026-10-22",
                             new_city_days=30)
            self.assertEqual(agg2["stats"]["new_cities"], [])

    def test_unresolved_not_lit(self):
        recs = [_rec("2026-10-01", 12, "未知门店", None)]
        recs[0].city = None
        agg = aggregate(recs, self.resolver, today="2026-10-22")
        self.assertEqual(agg["stats"]["lit_cities"], 0)
        self.assertEqual(len(agg["unresolved"]), 1)


class TestNarrative(unittest.TestCase):
    def test_late_night_prompt(self):
        late = {"is_late_night": True, "date": "2026-08-30", "time": "22:10", "store_name": "A店"}
        day = {"is_late_night": False, "date": "2026-08-30", "time": "12:10", "store_name": "A店"}
        p = late_night_prompt(late)
        self.assertTrue(p.endswith("？"))          # 必须是问句（开放、不臆造）
        self.assertEqual(late_night_prompt(day), "")  # 非深夜不追问
        self.assertEqual(p, late_night_prompt(late))  # 稳定：同输入同输出

    def test_timeline_sorted_desc(self):
        recs = [
            _rec("2026-09-01", 12, "A", "南京市").to_dict(),
            _rec("2026-10-05", 23, "B", "苏州市").to_dict(),
        ]
        tl = build_timeline(recs)
        self.assertEqual([d["date"] for d in tl], ["2026-10-05", "2026-09-01"])
        days = build_all_days(tl)
        self.assertTrue(days[0]["memories"][0]["is_late_night"])
        self.assertTrue(days[0]["memories"][0]["late_night_prompt"])


class TestRender(unittest.TestCase):
    def test_placeholder_replaced_and_escaped(self):
        footprint = {
            "meta": {"source_label": "t</script><b>x</b>"},
            "stats": {},
            "cities": [],
            "days": [],
        }
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "a.html")
            render_html(footprint, OUTLINE, out)
            with open(out, encoding="utf-8") as fp:
                html = fp.read()
            self.assertNotIn("__FOOTPRINT_DATA__", html)
            self.assertNotIn("__OUTLINE_DATA__", html)
            self.assertNotIn("</script><b>x</b>", html)  # 已转义


class TestTokenStore(unittest.TestCase):
    """Token 本地持久化：保存 → 读取 → 脱敏 → 清除。"""

    def test_save_load_mask_clear(self):
        from mcd_footprint.config import TokenStore

        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("MCD_FOOTPRINT_HOME")
            os.environ["MCD_FOOTPRINT_HOME"] = td
            try:
                st = TokenStore()
                self.assertFalse(st.exists())
                st.save("abcdefghijklmnopqrstuvwxyz012345")
                self.assertTrue(st.exists())
                self.assertEqual(st.token, "abcdefghijklmnopqrstuvwxyz012345")
                pub = st.public_state()
                self.assertTrue(pub["token_set"])
                self.assertNotIn("abcdefghijklmnopqrstuvwxyz012345", json.dumps(pub))  # 不回传明文
                self.assertEqual(pub["token_masked"], "abcd****2345")
                st.clear()
                self.assertFalse(st.exists())
            finally:
                if old is None:
                    os.environ.pop("MCD_FOOTPRINT_HOME", None)
                else:
                    os.environ["MCD_FOOTPRINT_HOME"] = old

    def test_override_contains_match(self):
        """人工纠偏支持「门店名包含」匹配，用于带后缀的门店名。"""
        r = CityResolver(CENTROIDS, os.path.join(DATA, "city-overrides.json"))
        r.name_overrides["南京火车站北广场"] = "南京市"
        out = r.resolve(store_name="南京火车站北广场快捷小站")
        self.assertEqual(out["city"], "南京市")
        self.assertEqual(out["source"], "override")


class TestServerApp(unittest.TestCase):
    """本地服务：用 mock 源构建，不依赖网络与真实 Token。"""

    def test_build_and_state(self):
        from mcd_footprint.server import FootprintApp

        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("MCD_FOOTPRINT_HOME")
            os.environ["MCD_FOOTPRINT_HOME"] = td
            try:
                app = FootprintApp(source="mock")
                self.assertTrue(app.footprint["cities"])
                st = app.state()
                self.assertTrue(st["server"])
                self.assertEqual(st["source"], "mock")
                self.assertFalse(st["token_set"])          # 未配置时不回传任何 Token
                page = app.render_page()
                self.assertIn("设置 Token", page)
                self.assertNotIn("__FOOTPRINT_DATA__", page)
            finally:
                if old is None:
                    os.environ.pop("MCD_FOOTPRINT_HOME", None)
                else:
                    os.environ["MCD_FOOTPRINT_HOME"] = old


class TestCityOrderLinkage(unittest.TestCase):
    """「先点城市、再看订单」所需的数据结构必须齐备。"""

    @classmethod
    def setUpClass(cls):
        cls.orders = load_mock()
        cls.r = CityResolver(CENTROIDS, os.path.join(DATA, "city-overrides.json"))
        recs = []
        for o in cls.orders:
            info = cls.r.resolve(
                store_name=o.get("storeName", ""),
                address=o.get("_mockAddress", ""),
                store_code=o.get("storeCode", ""),
            )
            rec = build_record(o, detail=None, city_info=info)
            if rec:
                rec.address = o.get("_mockAddress", "")
                recs.append(rec)
        cls.recs = recs
        cls.days = build_all_days(build_timeline([x.to_dict() for x in recs]))

    def test_every_memory_has_city_and_source(self):
        """每条订单都要能归属到具体城市，并标注定位来源。"""
        for d in self.days:
            for m in d["memories"]:
                self.assertTrue(m["city"], "订单缺少城市，无法按城市筛选")
                self.assertIn(m["city_source"],
                              ("store_name", "address", "override", "mcp_probe", "unknown"))

    def test_city_filter_is_possible(self):
        """任意城市都能筛出非空订单集合。"""
        agg = aggregate(self.recs, self.r, today="2026-10-22")
        for c in agg["cities"]:
            mems = [m for d in self.days for m in d["memories"] if m["city"] == c["name"]]
            self.assertEqual(len(mems), c["order_count"], f"{c['name']} 订单数对不上")


class TestEndToEnd(unittest.TestCase):
    def test_mock_pipeline(self):
        orders = load_mock()
        self.assertGreater(len(orders), 0)
        r = CityResolver(CENTROIDS, os.path.join(DATA, "city-overrides.json"))
        recs = []
        for o in orders:
            info = r.resolve(
                store_name=o.get("storeName", ""),
                address=o.get("_mockAddress", ""),
                store_code=o.get("storeCode", ""),
            )
            rec = build_record(o, detail=None, city_info=info)
            if rec:
                rec.address = o.get("_mockAddress", "")
                recs.append(rec)
        self.assertEqual(len(recs), len(orders))
        agg = aggregate(recs, r, today="2026-10-22")
        self.assertGreater(agg["stats"]["lit_cities"], 0)
        self.assertEqual(agg["stats"]["total_provinces"], 31)
        # 每个被点亮的城市都必须有坐标，否则无法打点
        for c in agg["cities"]:
            self.assertIsNotNone(c["lon"])
            self.assertIsNotNone(c["lat"])
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "b.html")
            render_html({"meta": {}, "stats": agg["stats"], "cities": agg["cities"],
                         "days": build_all_days(build_timeline([x.to_dict() for x in recs]))},
                        OUTLINE, out)
            self.assertGreater(os.path.getsize(out), 100 * 1024)


if __name__ == "__main__":
    unittest.main(verbosity=2)
