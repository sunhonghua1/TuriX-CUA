#!/usr/bin/env python3
"""
微信极速发送原子执行器 (Fox-path Executor)
利用 AppleScript (System Events) 实现：激活微信 -> Cmd+F 搜索 -> 选中联系人 -> 发送消息。
追求极致速度，无二次确认，闭眼盲发（Fast & Blind）。
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
    
    # 构建 AppleScript
    # 注意：为了防止单双引号冲突，使用 AppleScript 的 quoted form 来传递变量
    applescript_code = f"""
    tell application "System Events"
        -- 首先尝试激活微信进程
        try
            set wechatProc to first application process whose name is "WeChat"
            set frontmost of wechatProc to true
        on error
            -- 如果没启动，用 shell open 启动
            do shell script "open -b com.tencent.xinWeChat"
            delay 1.0
            set wechatProc to first application process whose name is "WeChat"
            set frontmost of wechatProc to true
        end try
        
        delay 0.3
        
        tell wechatProc
            -- 1. 触发搜索 (Cmd + F)
            keystroke "f" using {{command down}}
            delay 0.2
            
            -- 2. 输入联系人
            -- 对于中文输入法可能干扰的情况，可以依靠系统剪贴板，但 keystroke 通常足够快且绕过输入法
            set the clipboard to "{contact}"
            keystroke "v" using {{command down}}
            delay 0.6 -- 等待搜索结果出现
            
            -- 3. 选中该联系人
            key code 36 -- Return
            delay 0.3
            
            -- 4. 输入消息内容
            set the clipboard to "{message}"
            keystroke "v" using {{command down}}
            delay 0.2
            
            -- 5. 回车发送！
            key code 36 -- Return
        end tell
    end tell
    """
    
    t0 = time.time()
    try:
        # 执行 AppleScript
        result = subprocess.run(
            ["osascript", "-e", applescript_code],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"[wechat_sender] ❌ AppleScript 失败: {result.stderr}", file=sys.stderr)
            return result.returncode
            
        elapsed = time.time() - t0
        print(f"[wechat_sender] ✅ 已通过系统剪贴板注入并成功发送！(耗时 {elapsed:.2f}s)")
        return 0
    except Exception as e:
        print(f"[wechat_sender] ❌ 发生异常: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python -m src.fox_executors.wechat_sender_executor <联系人> <消息内容>", file=sys.stderr)
        sys.exit(1)
        
    contact_arg = sys.argv[1]
    message_arg = sys.argv[2]
    sys.exit(run(contact_arg, message_arg))
