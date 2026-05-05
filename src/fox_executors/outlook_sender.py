#!/usr/bin/env python3
"""
Outlook 邮件静默发送器 — 通过 macOS AppleScript 控制 Microsoft Outlook 发送邮件。

用法:
    python outlook_sender.py <to> <subject> <body> [attachment_path]

示例:
    python outlook_sender.py "zhang@example.com" "月度报告" "附件为本月财务报告，请查收。" ~/Desktop/报告.pdf

特点:
    - 利用 macOS AppleScript 直接控制 Outlook，无需 SMTP 配置
    - 支持附件（可选）
    - 非阻塞执行，不卡住小狐狸主进程
    - 发送完成后自动通知 + 语音播报
"""
from __future__ import annotations

import subprocess
import sys
import os
import logging

logger = logging.getLogger(__name__)

# 尝试导入语音模块
try:
    import voice
    HAS_VOICE = True
except ImportError:
    HAS_VOICE = False


def _notify(title: str, message: str) -> None:
    """macOS 原生通知。"""
    script = f'display notification "{message}" with title "{title}"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def send_outlook_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: str = "",
) -> dict:
    """
    通过 AppleScript 控制 Microsoft Outlook 发送邮件。

    Args:
        to: 收件人邮箱地址
        subject: 邮件主题
        body: 邮件正文
        attachment_path: 附件路径（可选）

    Returns:
        dict: {"status": "success"/"error", "message": ...}
    """

    # 转义 AppleScript 字符串中的特殊字符
    subject_escaped = subject.replace('"', '\\"').replace("\\", "\\\\")
    body_escaped = body.replace('"', '\\"').replace("\\", "\\\\").replace("\n", "\\n")
    to_escaped = to.replace('"', '\\"')

    # 构建 AppleScript
    attachment_block = ""
    if attachment_path:
        abs_path = os.path.expanduser(attachment_path)
        if os.path.exists(abs_path):
            # Outlook AppleScript 需要 POSIX path
            attachment_block = f'''
                make new attachment with properties {{file: POSIX file "{abs_path}"}}
            '''
        else:
            return {
                "status": "error",
                "message": f"附件不存在: {abs_path}",
            }

    applescript = f'''
    tell application "Microsoft Outlook"
        set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:"{body_escaped}"}}
        tell newMessage
            make new to recipient with properties {{email address:{{address:"{to_escaped}"}}}}
            {attachment_block}
        end tell
        send newMessage
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.info(f"✅ 邮件已发送至 {to}")
            _notify("小狐狸 · 邮件", f"邮件已发送至 {to}")
            if HAS_VOICE:
                voice.speak(f"邮件已成功发送给{to.split('@')[0]}。")
            return {
                "status": "success",
                "message": f"邮件已发送至 {to}",
                "subject": subject,
            }
        else:
            error_msg = result.stderr.strip() or "未知错误"
            logger.error(f"❌ 邮件发送失败: {error_msg}")

            # 常见错误提示
            if "not running" in error_msg.lower() or "-600" in error_msg:
                return {
                    "status": "error",
                    "message": "Microsoft Outlook 未运行，请先打开 Outlook。",
                }
            return {
                "status": "error",
                "message": f"发送失败: {error_msg}",
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "邮件发送超时（30秒），请检查 Outlook 状态。",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"执行异常: {str(e)}",
        }


def run(to: str, subject: str, body: str, attachment: str = "") -> int:
    """CLI 入口。"""
    result = send_outlook_email(to, subject, body, attachment)
    if result["status"] == "success":
        print(f"[outlook_sender] ✅ {result['message']}")
        return 0
    else:
        print(f"[outlook_sender] ❌ {result['message']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "用法: python outlook_sender.py <收件人> <主题> <正文> [附件路径]",
            file=sys.stderr,
        )
        sys.exit(1)

    to_addr = sys.argv[1]
    subj = sys.argv[2]
    content = sys.argv[3]
    attach = sys.argv[4] if len(sys.argv) > 4 else ""
    sys.exit(run(to_addr, subj, content, attach))
