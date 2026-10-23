#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_geo_data.py —— 构建「麦麦足迹地图」所需的离线地理底图数据。

产出两个文件（写入 data/ 目录）：
  1. china-outline.json     省级行政区边界（简化多边形），用于绘制底图轮廓
  2. city-centroids.json    地级市（含地区/自治州/盟/直辖市）中心坐标查表

数据源：阿里云 DataV.GeoAtlas 行政区划边界数据（源自民政部行政区划数据）。
  - 省级：https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json
  - 地市级：https://geo.datav.aliyun.com/areas_v3/bound/<province_adcode>_full.json

合规说明（重要）：
  - 本脚本只取「行政区域边界几何」用于绘制统计示意地图，不接入任何地图瓦片服务，
    不使用任何需要 Key 的地图服务。
  - 底图轮廓按国家标准完整绘制：包含台湾省，并保留九段线要素。
  - 「足迹点亮」统计口径仅覆盖中国大陆（不含港澳台及海外），
    因为麦当劳 MCP 服务本身限定中国大陆地区使用；港澳台仅作为底图轮廓的一部分绘制，
    不参与统计、不产生任何点亮逻辑。

用法：
    python tools/build_geo_data.py [--out data] [--province-precision 3]

依赖：仅标准库 + requests（如无 requests 则回退到 urllib）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

BASE = "https://geo.datav.aliyun.com/areas_v3/bound"

# 统计口径排除：港澳台（MCP 服务不覆盖）
EXCLUDED_FROM_STATS = {710000: "台湾省", 810000: "香港特别行政区", 820000: "澳门特别行政区"}

# 直辖市：作为单一"城市"单元参与统计（其下为市辖区，不再细分）
MUNICIPALITIES = {110000: "北京市", 120000: "天津市", 310000: "上海市", 500000: "重庆市"}


def http_get_json(url: str, retries: int = 3) -> Any:
    """GET JSON，带简单重试。优先 requests，回退 urllib。"""
    last_err: Optional[Exception] = None
    for i in range(retries):
        try:
            try:
                import requests  # type: ignore

                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except ImportError:
                import urllib.request

                with urllib.request.urlopen(url, timeout=30) as fp:
                    return json.loads(fp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"下载失败: {url} -> {last_err}")


def round_coords(geom: Dict[str, Any], precision: int) -> Dict[str, Any]:
    """按精度压缩坐标，显著减小文件体积。"""

    def rr(pt: List[float]) -> List[float]:
        return [round(pt[0], precision), round(pt[1], precision)]

    def dedup(ring: List[List[float]]) -> List[List[float]]:
        out: List[List[float]] = []
        for pt in ring:
            p = rr(pt)
            if not out or out[-1] != p:
                out.append(p)
        # 环至少需要 4 个点（闭合）
        if len(out) >= 3 and out[0] != out[-1]:
            out.append(out[0])
        return out

    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon":
        rings = [dedup(r) for r in coords]
        rings = [r for r in rings if len(r) >= 4]
        return {"type": "Polygon", "coordinates": rings}
    if gtype == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = [dedup(r) for r in poly]
            rings = [r for r in rings if len(r) >= 4]
            if rings:
                polys.append(rings)
        return {"type": "MultiPolygon", "coordinates": polys}
    return geom


def build_outline(precision: int) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """下载省级边界，返回 (简化后的 features, 省级元信息)。"""
    raw = http_get_json(f"{BASE}/100000_full.json")
    feats: List[Dict[str, Any]] = []
    meta: Dict[int, Dict[str, Any]] = {}

    for f in raw.get("features", []):
        props = f.get("properties", {})
        adcode = props.get("adcode")
        name = props.get("name")

        # 九段线要素（adcode 为字符串 "100000_JD"），单独保留，仅用于绘制
        if isinstance(adcode, str):
            geom = round_coords(f.get("geometry", {}), precision)
            feats.append(
                {
                    "type": "Feature",
                    "properties": {"adcode": adcode, "name": name or "九段线", "kind": "boundary-line"},
                    "geometry": geom,
                }
            )
            continue

        geom = round_coords(f.get("geometry", {}), precision)
        in_stats = adcode not in EXCLUDED_FROM_STATS
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "adcode": adcode,
                    "name": name,
                    "kind": "province",
                    "in_stats": in_stats,
                    "center": props.get("center"),
                },
                "geometry": geom,
            }
        )
        if isinstance(adcode, int) and name:
            meta[adcode] = {"name": name, "center": props.get("center"), "in_stats": in_stats}

    return feats, meta


def build_city_centroids(province_meta: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """逐省下载地市级边界，提取中心坐标，构建 城市名 -> 坐标 的查表。

    返回结构：
      {
        "cities": [ {name, short, adcode, province, lon, lat, level} , ... ],
        "alias":  { "南京": "南京市", ... }   # 简称/去后缀 -> 标准名，用于门店名解析
      }
    """
    cities: List[Dict[str, Any]] = []
    alias: Dict[str, str] = {}

    for adcode, pmeta in province_meta.items():
        if adcode in EXCLUDED_FROM_STATS:
            continue
        pname = pmeta["name"]
        try:
            raw = http_get_json(f"{BASE}/{adcode}_full.json")
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 省份 {pname}({adcode}) 下载失败: {exc}", file=sys.stderr)
            continue

        if adcode in MUNICIPALITIES:
            # 直辖市整体作为一个统计单元
            center = pmeta.get("center") or [0, 0]
            cities.append(
                {
                    "name": pname,
                    "short": pname.replace("市", ""),
                    "adcode": adcode,
                    "province": pname,
                    "lon": round(center[0], 4),
                    "lat": round(center[1], 4),
                    "level": "municipality",
                }
            )
            continue

        for f in raw.get("features", []):
            props = f.get("properties", {})
            cname = props.get("name")
            cadcode = props.get("adcode")
            if not cname or not isinstance(cadcode, int):
                continue
            center = props.get("center") or props.get("centroid")
            if not center:
                continue
            cities.append(
                {
                    "name": cname,
                    "short": cname,
                    "adcode": cadcode,
                    "province": pname,
                    "lon": round(center[0], 4),
                    "lat": round(center[1], 4),
                    "level": "city",
                }
            )
        print(f"[ok] {pname} 地市级要素已抓取")

    # 构建别名（去掉"市/地区/自治州/盟/特别行政区"等后缀），便于从门店名中解析
    for c in cities:
        name: str = c["name"]
        short = c["short"]
        if short and short not in alias:
            alias[short] = name
        for suffix in ("市", "地区", "自治州", "盟", "特别行政区"):
            if name.endswith(suffix) and len(name) > len(suffix):
                stem = name[: -len(suffix)]
                if stem and stem not in alias:
                    alias[stem] = name

    return {"cities": cities, "alias": alias}


def main() -> int:
    ap = argparse.ArgumentParser(description="构建麦麦足迹地图离线地理数据")
    ap.add_argument("--out", default="data", help="输出目录")
    ap.add_argument("--province-precision", type=int, default=3, help="省级边界坐标小数位")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    print("[1/3] 下载省级边界 ...")
    feats, province_meta = build_outline(args.province_precision)
    outline = {
        "type": "FeatureCollection",
        "source": "DataV.GeoAtlas 100000_full",
        "note": "仅用于绘制统计示意底图；台湾省按国家标准绘制，不参与足迹统计。",
        "features": feats,
    }
    outline_path = os.path.join(args.out, "china-outline.json")
    with open(outline_path, "w", encoding="utf-8") as fp:
        json.dump(outline, fp, ensure_ascii=False, separators=(",", ":"))
    print(f"[ok] 写出 {outline_path} ({os.path.getsize(outline_path)/1024:.0f} KB, {len(feats)} 要素)")

    print("[2/3] 下载地市级中心坐标 ...")
    centroids = build_city_centroids(province_meta)
    centroids["note"] = "地级市（含地区/自治州/盟/省直辖县级行政区）中心坐标；直辖市按单一统计单元处理。"
    centroids_path = os.path.join(args.out, "city-centroids.json")
    with open(centroids_path, "w", encoding="utf-8") as fp:
        json.dump(centroids, fp, ensure_ascii=False, separators=(",", ":"))
    print(
        f"[ok] 写出 {centroids_path} ({os.path.getsize(centroids_path)/1024:.0f} KB, "
        f"{len(centroids['cities'])} 个城市单元, {len(centroids['alias'])} 条别名)"
    )

    print("[3/3] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
