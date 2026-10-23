#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
submit_contest.py —— 一键完成参赛提交。

三步：
  1. 在 GitHub 上创建 **公开** 仓库（已存在则复用）
  2. 把本地 main 分支推送上去
  3. 按官方格式在活动仓库提报名 Issue

报名格式（严格遵守官方 README 的要求）：
  - 标题与正文分开提交（Issue 的 title / body 两个字段），标题内不含换行
  - 「标签 : 内容」写在同一行，如「项目简介：xxx」，中间不换行
  - 项目地址写**裸 URL**，不用 Markdown 链接格式

用法：
    export GITHUB_TOKEN=ghp_xxx        # 推荐走环境变量，不落盘
    python tools/submit_contest.py

    # 或显式传入（会留在 shell 历史里，慎用）
    python tools/submit_contest.py --token ghp_xxx

    # 只想看看会做什么，不触碰 GitHub
    python tools/submit_contest.py --dry-run

    # 分步执行
    python tools/submit_contest.py --only repo
    python tools/submit_contest.py --only push
    python tools/submit_contest.py --only issue

Token 权限：classic token 勾选 public_repo 即可（创建公开仓库 + 在他人公开仓库提 Issue）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

API = "https://api.github.com"
CONTEST_REPO = "M-China/mcd-developer-innovation-challenge"
DEFAULT_REPO_NAME = "mcd-footprint-map"
PROJECT_NAME = "麦麦足迹地图"
DESCRIPTION = "用吃麦当劳的记录点亮走过的城市，丈量走遍全国的脚步。"

# 官方要求的正文模板：标签与内容同行、项目地址用裸 URL
ISSUE_TITLE = "【报名】麦麦足迹地图 —— 用吃麦当劳的记录点亮走过的城市"
ISSUE_INTRO = (
    "基于麦当劳中国 MCP 的原创 Skill：把每一笔麦当劳订单还原到地级市粒度，"
    "在中国大陆地图上点亮走过的城市，并按日期回溯「那天在哪家店、几点、吃了什么」。"
    "支持城市→门店→日期三级下钻、新点亮城市高亮、21:00 后深夜场次的克制追问，"
    "订单可按城市与门店筛选，定位来源可追溯。"
)


def api(method: str, path: str, token: str, body: Optional[Dict[str, Any]] = None) -> Any:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "mcd-footprint-map-submit",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"GitHub API {method} {path} 失败：HTTP {exc.code} {detail}") from exc


def run(cmd: list, cwd: Optional[str] = None, capture: bool = True) -> str:
    if not capture:
        subprocess.run(cmd, cwd=cwd, check=True)
        return ""
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError("命令失败：" + " ".join(cmd) + "\n" + (out.stderr or out.stdout))
    return (out.stdout or "").strip()


def build_issue_body(repo_url: str) -> str:
    return (
        "【参赛申请】\n"
        f"项目名称：{PROJECT_NAME}\n"
        f"项目地址：{repo_url}\n"
        f"项目简介：{ISSUE_INTRO}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="一键创建公开仓库、推送代码并提交报名 Issue")
    p.add_argument("--token", default=None, help="GitHub Token（默认读环境变量 GITHUB_TOKEN）")
    p.add_argument("--repo", default=DEFAULT_REPO_NAME, help="仓库名")
    p.add_argument("--only", choices=["repo", "push", "issue"], help="只执行其中一步")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不触碰 GitHub")
    args = p.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    token = args.token or os.environ.get("GITHUB_TOKEN", "").strip()

    print("=" * 66)
    print("参赛提交 · 麦麦足迹地图")
    print("=" * 66)

    if args.dry_run:
        owner = "<你的 GitHub 用户名>"
        url = f"https://github.com/{owner}/{args.repo}"
        print("[计划 1/3] 创建公开仓库：", url)
        print("[计划 2/3] 推送本地 main 分支到该仓库")
        print("[计划 3/3] 在", CONTEST_REPO, "提报名 Issue：")
        print("-" * 66)
        print("标题：" + ISSUE_TITLE)
        print(build_issue_body(url))
        print("-" * 66)
        print("（--dry-run 未做任何网络操作）")
        return 0

    if not token:
        print("[error] 缺少 GitHub Token。", file=sys.stderr)
        print("  方式一：export GITHUB_TOKEN=ghp_xxx（推荐，不落盘）", file=sys.stderr)
        print("  方式二：python tools/submit_contest.py --token ghp_xxx", file=sys.stderr)
        print("  权限：classic token 勾选 public_repo", file=sys.stderr)
        return 2

    # ---------- 1. 身份 ----------
    me = api("GET", "/user", token)
    owner = me.get("login") or ""
    if not owner:
        print("[error] 无法读取 GitHub 身份，请确认 Token 有效。", file=sys.stderr)
        return 2
    repo_url = f"https://github.com/{owner}/{args.repo}"
    print(f"[0/3] 身份：{owner}")

    # ---------- 2. 仓库 ----------
    if args.only in (None, "repo"):
        try:
            api("POST", "/user/repos", token, {
                "name": args.repo,
                "description": DESCRIPTION,
                "private": False,
                "auto_init": False,
                "has_issues": True,
            })
            print(f"[1/3] 已创建公开仓库：{repo_url}")
        except RuntimeError as exc:
            if "HTTP 422" in str(exc) or "already exists" in str(exc):
                print(f"[1/3] 仓库已存在，直接复用：{repo_url}")
            else:
                raise
    if args.only == "repo":
        return 0

    # ---------- 3. 推送 ----------
    if args.only in (None, "push"):
        remote = f"https://{owner}:{token}@github.com/{owner}/{args.repo}.git"
        exists = run(["git", "remote"], cwd=root)
        if "origin" in exists.split():
            run(["git", "remote", "set-url", "origin", remote], cwd=root)
        else:
            run(["git", "remote", "add", "origin", remote], cwd=root)
        run(["git", "push", "-u", "origin", "main"], cwd=root, capture=False)
        print(f"[2/3] 已推送 main 分支：{repo_url}")
        # 推送后把带 Token 的 remote 换成干净地址，避免 Token 留在 .git/config 里
        run(["git", "remote", "set-url", "origin", f"https://github.com/{owner}/{args.repo}.git"], cwd=root)
        print("      （已清除 remote 中内嵌的 Token）")
    if args.only == "push":
        return 0

    # ---------- 4. 报名 Issue ----------
    if args.only in (None, "issue"):
        issue = api("POST", f"/repos/{CONTEST_REPO}/issues", token, {
            "title": ISSUE_TITLE,
            "body": build_issue_body(repo_url),
        })
        print(f"[3/3] 已提交报名 Issue：{issue.get('html_url')}")
        print()
        print("接下来：等官方机器人在 Issue 下回复「报名成功」通知。")
        print("注意：报名截止 2026-10-25 23:59（北京时间）。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
