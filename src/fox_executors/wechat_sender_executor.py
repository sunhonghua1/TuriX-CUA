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
import base64

def run(contact: str, message: str) -> int:
    """运行微信极速发送逻辑；返回进程退出码 0=成功。"""
    if not contact or not message:
        print("[wechat_sender] ❌ 缺少联系人或消息内容", file=sys.stderr)
        return 1

    print(f"[wechat_sender] 🚀 准备发送微信给 '{contact}'，内容: '{message}'")
    
    t0 = time.time()
    
    contact_b64 = base64.b64encode(contact.encode('utf-8')).decode('utf-8')
    message_b64 = base64.b64encode(message.encode('utf-8')).decode('utf-8')

    script = f"""
    -- 强制使用 Bundle ID 拉起微信，避免中文系统下 tell application "WeChat" 找不到应用
    do shell script "open -b com.tencent.xinWeChat"
    delay 1.0
    
    tell application "System Events"
        -- 进程名永远是 "WeChat"
        set wechatProc to first application process whose name is "WeChat"
        set frontmost of wechatProc to true
        delay 0.3
        
        tell wechatProc
            -- 1. 触发搜索
            keystroke "f" using {{command down}}
            delay 0.5
            
            -- 2. 注入联系人并粘贴
            do shell script "echo '{contact_b64}' | base64 -d | pbcopy"
            delay 0.2
            keystroke "v" using {{command down}}
            delay 1.0
            
            -- 3. 选中联系人
            key code 36
            delay 1.0
            
            -- 4. 注入消息内容并粘贴
            do shell script "echo '{message_b64}' | base64 -d | pbcopy"
            delay 0.2
            keystroke "v" using {{command down}}
            delay 0.5
            
            -- 5. 发送
            key code 36
        end tell
    end tell
    """
    
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[wechat_sender] ❌ AppleScript 执行失败: {res.stderr}", file=sys.stderr)
        return res.returncode
        
    elapsed = time.time() - t0
    print(f"[wechat_sender] ✅ 已成功通过一镜到底脚本完成发送！(耗时 {elapsed:.2f}s)")
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python -m src.fox_executors.wechat_sender_executor <联系人> <消息内容>", file=sys.stderr)
        sys.exit(1)
        
    contact_arg = sys.argv[1]
    message_arg = sys.argv[2]
    sys.exit(run(contact_arg, message_arg))
