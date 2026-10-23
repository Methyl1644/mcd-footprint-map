#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mcd-footprint-map —— 麦麦足迹地图

用吃麦当劳的记录点亮走过的城市，丈量走遍全国的脚步。
基于麦当劳 MCP（order-list / query-order / query-nearby-stores / now-time-info）真实能力实现。

统计口径：中国大陆地区，地级市粒度；港澳台及海外不计入。
"""

__version__ = "1.0.0"
__all__ = ["mcp_client", "cities", "normalize", "aggregate", "narrative", "render", "cli"]
