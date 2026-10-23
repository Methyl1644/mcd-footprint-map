#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
render.py —— 把聚合结果渲染为单文件、可离线双击打开的 HTML。

输出 HTML 已内联：
  - 行政区域边界底图（data/china-outline.json）
  - 足迹聚合数据（城市/时间轴/当日回忆/统计）
不依赖任何 CDN、不加载任何在线地图瓦片，因此断网也能正常查看。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

TEMPLATE_DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets",
    "viewer.html",
)


def _js_safe(obj: Any) -> str:
    """序列化为 JSON 并做 JS 内联安全转义。"""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # 防止 </script> 提前闭合、以及 U+2028/2029 破坏 JS 字符串
    return (
        text.replace("\\u2028", "\\u2028")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_html_string(
    footprint: Dict[str, Any],
    outline_path: str,
    template_path: Optional[str] = None,
) -> str:
    """渲染为 HTML 字符串（不落盘），供本地服务直接响应。"""
    template_path = template_path or TEMPLATE_DEFAULT
    with open(template_path, "r", encoding="utf-8") as fp:
        html = fp.read()
    with open(outline_path, "r", encoding="utf-8") as fp:
        outline = json.load(fp)

    html = html.replace("__FOOTPRINT_DATA__", _js_safe(footprint))
    html = html.replace("__OUTLINE_DATA__", _js_safe(outline))
    return html


def render_html(
    footprint: Dict[str, Any],
    outline_path: str,
    out_path: str,
    template_path: Optional[str] = None,
) -> str:
    """渲染并写出 HTML，返回输出路径。"""
    html = render_html_string(footprint, outline_path, template_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(html)
    return out_path
