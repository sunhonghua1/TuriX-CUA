#!/usr/bin/env python3
"""
应用启动原子执行器 — open -b + NSWorkspace 轮询最前端，行为对齐 calc_helper。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import Cocoa  # type: ignore[import-untyped]


def _wait_for_frontmost(bundle_id: str, timeout: float = 5.0) -> bool:
    """与 calc_helper 一致：轮询 NSWorkspace 直至指定 bundle 最前端。"""
    workspace = Cocoa.NSWorkspace.sharedWorkspace()
    deadline = time.time() + timeout
    while time.time() < deadline:
        front = workspace.frontmostApplication()
        if front and front.bundleIdentifier() == bundle_id:
            return True
        time.sleep(0.1)
    return False

# 常用别名 -> bundle id（可扩展）
APP_ALIASES: dict[str, str] = {
    "safari": "com.apple.Safari",
    "chrome": "com.google.Chrome",
    "firefox": "org.mozilla.firefox",
    "wechat": "com.tencent.xinWeChat",
    "weixin": "com.tencent.xinWeChat",
    "calculator": "com.apple.calculator",
    "terminal": "com.apple.Terminal",
    "iterm": "com.googlecode.iterm2",
    "notes": "com.apple.Notes",
    "mail": "com.apple.mail",
    "music": "com.apple.Music",
    "finder": "com.apple.finder",
    "vscode": "com.microsoft.VSCode",
}


try:
    from .app_registry import resolve_app_bundle_id
except ImportError:
    from app_registry import resolve_app_bundle_id

def resolve_bundle_id(name: str) -> str | None:
    key = name.strip().lower()
    if key.startswith("com."):
        return key
    
    # 1. Try hardcoded aliases first
    if key in APP_ALIASES:
        return APP_ALIASES[key]
        
    # 2. Dynamically resolve localized names via mdfind
    return resolve_app_bundle_id(name)


def launch(app_token: str, *, wait_timeout: float = 8.0) -> bool:
    """
    启动或激活应用并等待其成为最前端。
    app_token: 别名（safari）、本地化名称（备忘录）或完整 bundle id。
    """
    bid = resolve_bundle_id(app_token)
    if not bid:
        print(f"[app_launcher] 未找到应用: {app_token}", file=sys.stderr)
        return False

    subprocess.run(["open", "-b", bid], check=True)
    print(f"[app_launcher] open -b {bid}")
    ok = _wait_for_frontmost(bid, timeout=wait_timeout)
    if ok:
        print("[app_launcher] 应用已处于最前端")
    else:
        print("[app_launcher] 超时：应用未在最前端", file=sys.stderr)
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m src.fox_executors.app_launcher safari", file=sys.stderr)
        sys.exit(1)
    ok = launch(sys.argv[1])
    sys.exit(0 if ok else 1)
