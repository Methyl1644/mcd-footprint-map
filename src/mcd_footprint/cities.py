#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cities.py —— 地级市坐标查表 + 从门店名/地址推断城市（多级降级）。

设计前提（来自实测，不臆造）：
  - MCP 的 order-list 不返回城市、地址、经纬度；
  - query-order 返回 storeAddress，但部分历史订单会报 610303「订单号不存在」；
  - query-nearby-stores 返回 longitude/latitude，但实测恒为 0.0，无法用于打点。

因此城市解析采用「多级降级」，且每一级都在结果里记录来源 city_source，便于追溯与纠偏。

降级链（**门店名优先于地址**，这是实测后的顺序，原因见 _match_in_text 注释）：
  L1 override     人工纠偏表 data/city-overrides.json
                  L1a storeCode 精确匹配（最高优先级）
                  L1b storeNames 精确匹配 / 包含匹配
  L2 store_name   从门店名中匹配（麦当劳门店命名惯例："麦当劳<城市><商圈/路名>餐厅"）
                  L2a 剥掉品牌前缀后城市名位于开头（confidence 0.9）
                  L2b 全文最靠前匹配（confidence 0.75）
  L3 address      从 query-order 的 storeAddress 中匹配，且必须显式带「市」字
  L4 mcp_probe    调用 query-nearby-stores 反查（需网络 + 候选城市，默认关闭）
  L5 unknown      无法判定 -> 归入「待确认」，不计入点亮
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 统计口径：不含港澳台及海外（麦当劳 MCP 服务本身限定中国大陆地区）
EXCLUDED_TOKENS = ("香港", "澳门", "台湾", "Hong Kong", "Macao", "Taiwan")

# 门店名中需要跳过的品牌前缀
BRAND_PREFIXES = ("麦当劳", "McDonald", "McDonald's", "麦麦")


class CityResolver:
    """把门店名/地址解析为地级市，并给出坐标。"""

    def __init__(self, centroids_path: str, overrides_path: Optional[str] = None):
        with open(centroids_path, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        self.cities: List[Dict[str, Any]] = raw.get("cities", [])
        self.alias: Dict[str, str] = dict(raw.get("alias", {}))
        self._by_name: Dict[str, Dict[str, Any]] = {c["name"]: c for c in self.cities}

        # 省份 -> 是否计入统计
        self.province_in_stats: Dict[str, bool] = {}
        for c in self.cities:
            prov = c.get("province")
            if prov and prov not in self.province_in_stats:
                self.province_in_stats[prov] = True

        # 别名按长度倒序，保证长名优先匹配
        self._alias_sorted: List[Tuple[str, str]] = sorted(
            self.alias.items(), key=lambda kv: -len(kv[0])
        )

        self.overrides: Dict[str, str] = {}
        if overrides_path and os.path.exists(overrides_path):
            with open(overrides_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            # 支持 {"storeCodes": {"1990398":"南京市"}, "storeNames": {"xxx":"南京市"}}
            self.overrides = {
                str(k): v for k, v in (data.get("storeCodes") or {}).items()
            }
            self.name_overrides = {
                str(k): v for k, v in (data.get("storeNames") or {}).items()
            }
        else:
            self.name_overrides = {}

    # ---------------- 基础查询 ----------------

    @property
    def total_cities(self) -> int:
        """全国（大陆）地级市统计单元总数，用于计算覆盖率。"""
        return len(self.cities)

    @property
    def total_provinces(self) -> int:
        """大陆省级行政区数量（31）。"""
        return len(self.province_in_stats)

    def get(self, city_name: str) -> Optional[Dict[str, Any]]:
        return self._by_name.get(city_name)

    def province_of(self, city_name: str) -> Optional[str]:
        c = self._by_name.get(city_name)
        return c.get("province") if c else None

    # ---------------- 文本匹配 ----------------

    def _match_in_text(
        self, text: str, require_city_suffix: bool = False, anchor_start: bool = False
    ) -> Optional[str]:
        """在文本中匹配地级市名。

        参数：
          require_city_suffix —— 命中后必须紧跟"市"字。
            用于**地址**匹配：实测 query-order 的 storeAddress 多为"路名+门牌号"
            （如"广州路14号""中山路166号""延安路98号"），若不加限制会把
            "广州路"误判为广州市、"中山路"误判为中山市。加上"市"字约束后，
            只有"南京市玄武区珠江路2-5号"这类显式带市名的地址才会命中。

          anchor_start —— 要求命中位置必须是文本开头。
            用于**门店名**匹配：麦当劳门店命名惯例为"麦当劳<城市><商圈/路名>餐厅"，
            剥去品牌前缀后，城市名几乎总是位于开头，锚定开头可显著抑制误判。
        """
        if not text:
            return None
        best: Optional[Tuple[int, int, str]] = None  # (start, -len, city)
        for alias, city in self._alias_sorted:
            if len(alias) < 2:
                continue
            idx = text.find(alias)
            if idx < 0:
                continue
            if anchor_start and idx != 0:
                continue
            if require_city_suffix and text[idx + len(alias) : idx + len(alias) + 1] != "市":
                continue
            cand = (idx, -len(alias), city)
            if best is None or cand < best:
                best = cand
        return best[2] if best else None

    @staticmethod
    def _strip_prefix(name: str) -> str:
        for p in BRAND_PREFIXES:
            if name.startswith(p):
                return name[len(p) :]
        return name

    @staticmethod
    def _is_excluded(text: str) -> bool:
        return any(tok in text for tok in EXCLUDED_TOKENS)

    # ---------------- 主入口 ----------------

    def resolve(
        self,
        store_name: str = "",
        address: str = "",
        store_code: str = "",
        probe_cities: Optional[Iterable[str]] = None,
        client: Any = None,
    ) -> Dict[str, Any]:
        """返回 {city, province, lon, lat, source, confidence}。"""
        name = (store_name or "").strip()
        addr = (address or "").strip()

        # L1 人工纠偏（人工指定 > 一切自动推断）
        if store_code and str(store_code) in self.overrides:
            return self._pack(self.overrides[str(store_code)], "override", 1.0)
        if name and name in self.name_overrides:
            return self._pack(self.name_overrides[name], "override", 1.0)
        # L1b 门店名包含式纠偏：用于"麦当劳XX店（已停业）"这类带后缀、无法精确命中的情况。
        #     取最长键，避免短键误命中。
        if name and self.name_overrides:
            hit_key = None
            for k in self.name_overrides:
                if k and k in name and (hit_key is None or len(k) > len(hit_key)):
                    hit_key = k
            if hit_key:
                return self._pack(self.name_overrides[hit_key], "override", 0.95)

        # 边界：港澳台及海外不计入
        if self._is_excluded(name) or self._is_excluded(addr):
            return self._pack(None, "excluded", 0.0)

        # L2 门店名匹配（命名惯例最可靠：麦当劳<城市><商圈/路名>餐厅）
        #    先要求"剥掉品牌前缀后城市名位于开头"；不行再退化为全文最靠前匹配。
        if name:
            body = self._strip_prefix(name)
            hit = self._match_in_text(body, anchor_start=True)
            if hit:
                return self._pack(hit, "store_name", 0.9)
            hit = self._match_in_text(body) or self._match_in_text(name)
            if hit:
                return self._pack(hit, "store_name", 0.75)

        # L3 地址匹配：必须显式出现"XX市"，否则路名会造成严重误判
        if addr:
            hit = self._match_in_text(addr, require_city_suffix=True)
            if hit:
                return self._pack(hit, "address", 0.85)

        # L4 MCP 反查（可选，默认关闭）
        if client is not None and probe_cities:
            for city in probe_cities:
                try:
                    stores = client.nearby_stores(city=city, keyword=self._strip_prefix(name) or city)
                except Exception:  # noqa: BLE001
                    continue
                codes = {str(s.get("storeCode")): s for s in stores or []}
                if store_code and str(store_code) in codes:
                    return self._pack(city, "mcp_probe", 0.7)

        return self._pack(None, "unknown", 0.0)

    def _pack(self, city: Optional[str], source: str, confidence: float) -> Dict[str, Any]:
        c = self._by_name.get(city) if city else None
        return {
            "city": c["name"] if c else None,
            "province": c.get("province") if c else None,
            "lon": c.get("lon") if c else None,
            "lat": c.get("lat") if c else None,
            "adcode": c.get("adcode") if c else None,
            "source": source,
            "confidence": confidence,
        }
