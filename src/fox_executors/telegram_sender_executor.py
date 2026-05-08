#!/usr/bin/env python3
"""
Telegram 极速发送原子执行器 (Fox-path Executor)
使用 AppleScript + System Events 控制 Telegram Mac 客户端完成消息发送。
"""
from __future__ import annotations

import subprocess
import sys
import time


def _escape_applescript_text(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return escaped.replace("\n", "\\n")


def run(contact: str, message: str) -> int:
    """运行 Telegram 发送逻辑；返回退出码。"""
    if not contact or not message:
        print("[telegram_sender] ❌ 缺少联系人或消息内容", file=sys.stderr)
        return 1

    print(f"[telegram_sender] 🚀 准备发送 Telegram 给 '{contact}'，内容: '{message}'")
    t0 = time.time()

    contact_safe = _escape_applescript_text(contact)
    message_safe = _escape_applescript_text(message)

    script = f"""
    set targetName to "{contact_safe}"
    set targetMessage to "{message_safe}"

    tell application "System Events"
        if not (exists process "Telegram") then
            error "Telegram 应用未启动或未登录" number 1002
        end if
    end tell

    tell application "Telegram" to activate

    tell application "System Events"
        tell application process "Telegram"
            set frontmost to true
        end tell
        delay 0.4

        keystroke "k" using {{command down}}
        delay 0.6
        keystroke "a" using {{command down}}
        delay 0.1
        key code 51
        delay 0.2
        keystroke targetName
        delay 1.0
        key code 36
        delay 0.8

        -- 尝试聚焦输入区，避免焦点仍停留在搜索框
        key code 53
        delay 0.2

        keystroke targetMessage
        delay 0.2
        key code 36
    end tell
    """

    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    elapsed = time.time() - t0

    if res.returncode != 0:
        stderr = (res.stderr or "").strip()
        if "1002" in stderr or "Telegram 应用未启动或未登录" in stderr:
            print(f"[telegram_sender] ❌ {stderr or 'Telegram 应用未启动/不可用'}", file=sys.stderr)
            return 2
        if "(-1728)" in stderr:
            print(f"[telegram_sender] ❌ 联系人可能未找到: {stderr}", file=sys.stderr)
            return 3
        print(f"[telegram_sender] ❌ AppleScript 执行失败: {stderr}", file=sys.stderr)
        return 2

    if res.stderr.strip():
        print(f"[telegram_sender] ⚠️ AppleScript 警告: {res.stderr.strip()}")

    print(f"[telegram_sender] ✅ 消息发送完成 (耗时 {elapsed:.2f}s)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python telegram_sender_executor.py <联系人> <消息内容>", file=sys.stderr)
        sys.exit(1)

    contact_arg = str(sys.argv[1]).strip()
    message_arg = str(sys.argv[2]).strip()
    sys.exit(run(contact_arg, message_arg))
