#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
config.py —— MCP_TOKEN 的本地持久化与读取优先级。

为什么要单独存一份：
  Skill 需要「用户填一次 Token，之后每次足迹都基于他自己的账号生效」。
  Token 不能写进产物 HTML（会被分享出去），也不该每次手敲，因此落盘到
  用户本机的一个小 JSON 文件，并尽量收紧权限。

读取优先级（由高到低）：
  1. 命令行 --token
  2. 环境变量 MCD_MCP_TOKEN
  3. 本机配置文件 <配置目录>/token.json   ← 设置面板写入的就是这里

配置目录：环境变量 MCD_FOOTPRINT_HOME，默认 ~/.mcd-footprint-map
"""

from __future__ import annotations

import json
import os
import stat
from typing import Any, Dict, Optional

ENV_TOKEN = "MCD_MCP_TOKEN"
ENV_ENDPOINT = "MCD_MCP_ENDPOINT"
ENV_HOME = "MCD_FOOTPRINT_HOME"

DEFAULT_ENDPOINT = "https://mcp.mcd.cn"


def config_dir() -> str:
    base = os.environ.get(ENV_HOME, "").strip()
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".mcd-footprint-map")
    return os.path.abspath(base)


def token_path() -> str:
    return os.path.join(config_dir(), "token.json")


class TokenStore:
    """读写本机 Token 配置。文件内容：{token, endpoint, updated_at}。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or token_path()

    # ---------------- 读 ----------------

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def token(self) -> str:
        return str(self.load().get("token") or "").strip()

    @property
    def endpoint(self) -> str:
        return str(self.load().get("endpoint") or "").strip() or DEFAULT_ENDPOINT

    @property
    def updated_at(self) -> str:
        return str(self.load().get("updated_at") or "")

    def exists(self) -> bool:
        return bool(self.token)

    # ---------------- 写 ----------------

    def save(self, token: str, endpoint: Optional[str] = None) -> Dict[str, Any]:
        import datetime as _dt

        token = (token or "").strip()
        if not token:
            raise ValueError("Token 不能为空")
        old = self.load()
        data = {
            "token": token,
            "endpoint": (endpoint or old.get("endpoint") or DEFAULT_ENDPOINT),
            "updated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        # 尽力收紧权限（Windows 上 chmod 效果有限，但仍尝试）
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:  # noqa: BLE001
            pass
        return data

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001
            pass

    # ---------------- 展示 ----------------

    @staticmethod
    def mask(token: str) -> str:
        """脱敏展示：只保留前 4 与后 4 位。"""
        t = (token or "").strip()
        if not t:
            return ""
        if len(t) <= 10:
            return t[:2] + "****" + t[-2:]
        return t[:4] + "****" + t[-4:]

    def public_state(self) -> Dict[str, Any]:
        """给前端的只读状态（绝不含明文 Token）。"""
        tok = self.token
        return {
            "token_set": bool(tok),
            "token_masked": self.mask(tok),
            "endpoint": self.endpoint,
            "updated_at": self.updated_at,
            "path": self.path,
        }


def resolve_token(cli_token: Optional[str] = None) -> str:
    """按优先级解析出最终使用的 Token。"""
    if cli_token and str(cli_token).strip():
        return str(cli_token).strip()
    env = os.environ.get(ENV_TOKEN, "").strip()
    if env:
        return env
    return TokenStore().token


def resolve_endpoint(cli_endpoint: Optional[str] = None) -> str:
    if cli_endpoint and str(cli_endpoint).strip():
        return str(cli_endpoint).strip()
    env = os.environ.get(ENV_ENDPOINT, "").strip()
    if env:
        return env
    return TokenStore().endpoint
