#!/usr/bin/env python3
"""
微信极速发送原子执行器 (Fox-path Executor)
v5: 终极稳定版。
使用 macOS 菜单栏点击 (UI Elements) 代替 `Cmd+F` 和 `Cmd+V` 快捷键。
彻底解决中文输入法、系统权限导致的快捷键被拦截、失效以及发出错误提示音的问题。
"""
from __future__ import annotations

import subprocess
import sys
import time

def run(contact: str, message: str) -> int:
    """运行微信极速发送逻辑；返回进程退出码 0=成功。"""
    if not contact or not message:
        print("[wechat_sender] ❌ 缺少联系人或消息内容", file=sys.stderr)
        return 1

    print(f"[wechat_sender] 🚀 准备发送微信给 '{contact}'，内容: '{message}'")
    
    t0 = time.time()
    
    # 转义双引号，防止 AppleScript 注入
    contact_safe = contact.replace('"', '\\"')
    message_safe = message.replace('"', '\\"')

    script = f"""
    -- 1. 激活微信
    tell application "WeChat" to activate
    
    tell application "System Events"
        -- 循环等待直到微信拿到真正的最前台焦点
        set timeoutCounter to 0
        repeat until frontmost of application process "WeChat"
            tell application process "WeChat" to set frontmost to true
            delay 0.5
            set timeoutCounter to timeoutCounter + 1
            if timeoutCounter > 10 then exit repeat
        end repeat
        
        delay 0.5
        
        tell application process "WeChat"
            -- 2. 触发搜索：不按快捷键，直接点击顶部菜单栏的“编辑” -> “查找…”
            try
                click menu item "查找…" of menu 1 of menu bar item "编辑" of menu bar 1
            on error
                -- 兼容英文系统或旧版本
                keystroke "f" using {{command down}}
            end try
        end tell
        delay 1.0
        
        -- 3. 清空搜索框 (如果里面有旧内容)
        -- 这里 Delete 键一般不会被拦截
        keystroke "a" using {{command down}}
        delay 0.1
        key code 51
        delay 0.3
        
        -- 4. 粘贴联系人名字
        set the clipboard to "{contact_safe}"
        delay 0.3
        tell application process "WeChat"
            -- 直接点击顶部菜单栏的“编辑” -> “粘贴”
            try
                click menu item "粘贴" of menu 1 of menu bar item "编辑" of menu bar 1
            on error
                keystroke "v" using {{command down}}
            end try
        end tell
        delay 2.5
        
        -- 5. 按回车选中第一个搜索结果
        key code 36
        delay 2.5
        
        -- 6. 按两次 Escape 彻底关闭搜索面板，让焦点回到消息输入框
        key code 53
        delay 1.5
        key code 53
        delay 1.0
        
        -- 7. 粘贴消息内容
        set the clipboard to "{message_safe}"
        delay 0.3
        tell application process "WeChat"
            try
                click menu item "粘贴" of menu 1 of menu bar item "编辑" of menu bar 1
            on error
                keystroke "v" using {{command down}}
            end try
        end tell
        delay 1.0
        
        -- 8. 按回车发送
        key code 36
        delay 0.5
    end tell
    """
    
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    elapsed = time.time() - t0
    
    if res.returncode != 0:
        print(f"[wechat_sender] ❌ AppleScript 执行失败: {res.stderr}", file=sys.stderr)
        return res.returncode
    
    if res.stderr.strip():
        print(f"[wechat_sender] ⚠️ AppleScript 警告: {res.stderr.strip()}")
        
    print(f"[wechat_sender] ✅ 已成功通过一镜到底脚本完成发送！(耗时 {elapsed:.2f}s)")
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python wechat_sender_executor.py <联系人> <消息内容>", file=sys.stderr)
        sys.exit(1)
        
    contact_arg = sys.argv[1]
    message_arg = sys.argv[2]
    sys.exit(run(contact_arg, message_arg))
