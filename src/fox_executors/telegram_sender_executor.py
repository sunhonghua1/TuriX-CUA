#!/usr/bin/env python3
"""
Telegram 极速发送原子执行器 (Fox-path Executor)
v5: 终极稳定版。
使用 macOS 菜单栏点击 (UI Elements) 代替 keystroke 中文输入。
彻底解决中文输入法、系统权限导致的快捷键被拦截、失效以及发出错误提示音的问题。
"""
from __future__ import annotations

import subprocess
import sys
import time


def run(contact: str, message: str) -> int:
    """运行 Telegram 发送逻辑；返回退出码。"""
    if not contact or not message:
        print("[telegram_sender] ❌ 缺少联系人或消息内容", file=sys.stderr)
        return 1

    print(f"[telegram_sender] 🚀 准备发送 Telegram 给 '{contact}'，内容: '{message}'")
    t0 = time.time()

    # 转义双引号，防止 AppleScript 注入
    contact_safe = contact.replace('"', '\\"')
    message_safe = message.replace('"', '\\"')

    script = f"""
    -- 1. 检查 Telegram 是否在运行
    tell application "System Events"
        if not (exists process "Telegram") then
            error "Telegram 应用未启动或未登录" number 1002
        end if
    end tell

    -- 2. 激活 Telegram
    tell application "Telegram" to activate

    tell application "System Events"
        -- 循环等待直到 Telegram 拿到真正的最前台焦点
        set timeoutCounter to 0
        repeat until frontmost of application process "Telegram"
            tell application process "Telegram" to set frontmost to true
            delay 0.5
            set timeoutCounter to timeoutCounter + 1
            if timeoutCounter > 10 then exit repeat
        end repeat

        delay 0.5

        tell application process "Telegram"
            -- 3. 触发搜索：点击菜单栏 "编辑" -> "搜索…" (或 "Search…")
            try
                click menu item "搜索…" of menu 1 of menu bar item "编辑" of menu bar 1
            on error
                try
                    click menu item "Search…" of menu 1 of menu bar item "Edit" of menu bar 1
                on error
                    -- 兜底：快捷键 Cmd+K
                    keystroke "k" using {{command down}}
                end try
            end try
        end tell
        delay 1.0

        -- 4. 清空搜索框 (如果里面有旧内容)
        keystroke "a" using {{command down}}
        delay 0.1
        key code 51
        delay 0.3

        -- 5. 粘贴联系人名字 (剪贴板 + 菜单栏点击，不走 keystroke)
        set the clipboard to "{contact_safe}"
        delay 0.3
        tell application process "Telegram"
            try
                click menu item "粘贴" of menu 1 of menu bar item "编辑" of menu bar 1
            on error
                try
                    click menu item "Paste" of menu 1 of menu bar item "Edit" of menu bar 1
                on error
                    keystroke "v" using {{command down}}
                end try
            end try
        end tell
        delay 2.0

        -- 6. 按回车选中第一个搜索结果
        key code 36
        delay 2.0

        -- 7. 按 Escape 关闭搜索面板，让焦点回到消息输入框
        key code 53
        delay 1.0

        -- 8. 粘贴消息内容 (剪贴板 + 菜单栏点击)
        set the clipboard to "{message_safe}"
        delay 0.3
        tell application process "Telegram"
            try
                click menu item "粘贴" of menu 1 of menu bar item "编辑" of menu bar 1
            on error
                try
                    click menu item "Paste" of menu 1 of menu bar item "Edit" of menu bar 1
                on error
                    keystroke "v" using {{command down}}
                end try
            end try
        end tell
        delay 1.0

        -- 9. 按回车发送
        key code 36
        delay 0.5
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

    print(f"[telegram_sender] ✅ 已成功通过一镜到底脚本完成发送！(耗时 {elapsed:.2f}s)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python telegram_sender_executor.py <联系人> <消息内容>", file=sys.stderr)
        sys.exit(1)

    contact_arg = str(sys.argv[1]).strip()
    message_arg = str(sys.argv[2]).strip()
    sys.exit(run(contact_arg, message_arg))
