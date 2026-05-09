#!/usr/bin/env python3
"""
Notes 笔记搜索原子执行器 (Fox-path Executor)
使用 AppleScript 搜索 macOS Notes.app，返回匹配笔记的标题和内容摘要。
"""
from __future__ import annotations

import subprocess
import sys
import json


def run(query: str) -> int:
    """搜索 Notes.app 笔记；返回退出码 0=成功。"""
    if not query:
        print("[notes_search] ❌ 缺少搜索关键词", file=sys.stderr)
        return 1

    print(f"[notes_search] 🔍 搜索笔记: '{query}'")

    # 转义双引号
    query_safe = query.replace('"', '\\"')

    script = f"""
    tell application "Notes"
        set results to {{}}
        set matchedNotes to (every note whose name contains "{query_safe}" or body contains "{query_safe}")
        set maxCount to 10
        set i to 0
        repeat with n in matchedNotes
            if i ≥ maxCount then exit repeat
            set end of results to name of n & "|||" & (text 1 thru 300 of body of n)
            set i to i + 1
        end repeat
        set AppleScript's text item delimiters to "\\n===\\n"
        return results as text
    end tell
    """

    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        stderr = (res.stderr or "").strip()
        if "Not authorized" in stderr or "not allowed" in stderr:
            print(f"[notes_search] ❌ 缺少 Notes.app 自动化权限: {stderr}", file=sys.stderr)
            return 2
        print(f"[notes_search] ❌ AppleScript 执行失败: {stderr}", file=sys.stderr)
        return 2

    output = (res.stdout or "").strip()
    if not output:
        print(f"[notes_search] 📭 没有找到包含 '{query}' 的笔记")
        return 0

    # 解析结果并格式化输出
    notes = output.split("\n===\n")
    print(f"[notes_search] 📝 找到 {len(notes)} 条笔记:")
    for i, note_text in enumerate(notes, 1):
        parts = note_text.split("|||", 1)
        title = parts[0].strip() if parts else "无标题"
        body_preview = parts[1].strip() if len(parts) > 1 else ""
        # 去掉 HTML 标签的粗糙方式（Notes 返回 HTML body）
        import re
        body_clean = re.sub(r'<[^>]+>', '', body_preview).strip()
        if len(body_clean) > 200:
            body_clean = body_clean[:200] + "..."
        print(f"  {i}. 【{title}】 {body_clean}")

    # 复制结果到剪贴板
    clipboard_text = "\n\n".join(notes) if notes else f"未找到包含 '{query}' 的笔记。"
    try:
        pbcopy = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        pbcopy.communicate(clipboard_text.encode("utf-8"))
        print(f"[notes_search] 📋 搜索结果已复制到剪贴板")
    except Exception:
        pass

    print(f"[notes_search] 💡 {clipboard_text}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python notes_search_executor.py <搜索关键词>", file=sys.stderr)
        sys.exit(1)

    query_arg = str(sys.argv[1]).strip()
    sys.exit(run(query_arg))
