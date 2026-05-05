#!/usr/bin/env python3
"""
本地问答执行器 — 调用本地大模型生成结果，复制到剪贴板，并弹出系统通知。
"""
from __future__ import annotations

import os
import subprocess
import sys
import logging

try:
    from openai import OpenAI
except ImportError:
    print("[ask_executor] 缺少 openai 库", file=sys.stderr)
    sys.exit(1)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
_DEFAULT_KEY = os.environ.get("FOX_LOCAL_LLM_API_KEY", "not-needed")

def _get_relevant_memories(query: str, limit: int = 10) -> str:
    """从本地 SQLite 数据库中检索最近的对话记录。"""
    import sqlite3
    from pathlib import Path
    db_path = Path.home() / ".ninetail-fox" / "conversations.sqlite"
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # 改进：直接获取最近的 N 条记录，作为上下文
        cursor = conn.execute(
            "SELECT role, content FROM conversation_log ORDER BY timestamp DESC LIMIT ?", 
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return ""
        
        # 倒序排列，让时间早的在上面
        rows.reverse()
        mem_text = "\n".join([f"【{row['role']}】: {row['content']}" for row in rows])
        
        return f"\n--- 历史对话记录 (记忆) ---\n{mem_text}\n--------------------------\n"
    except Exception as e:
        logger.debug("检索记忆失败: %s", e)
        return ""

def _default_model(client: OpenAI) -> str | None:
    explicit = os.environ.get("FOX_LOCAL_LLM_MODEL", "").strip()
    if explicit:
        return explicit
    try:
        models = client.models.list()
        if getattr(models, "data", None):
            return models.data[0].id
    except Exception as e:
        logger.debug("list models failed: %s", e)
    return None

def run_ask(prompt: str) -> bool:
    try:
        client = OpenAI(
            base_url=_DEFAULT_BASE,
            api_key=_DEFAULT_KEY,
            timeout=60.0,
        )
        use_model = _default_model(client)
        if not use_model:
            print("[ask_executor] 无法获取本地模型", file=sys.stderr)
            return False

        print(f"[ask_executor] 正在检索相关记忆...")
        memory_context = _get_relevant_memories(prompt)

        print(f"[ask_executor] 正在调用本地模型 ({use_model}) 回答...")
        completion = client.chat.completions.create(
            model=use_model,
            messages=[
                {"role": "system", "content": f"你是小狐狸 (LittleFox)，一个贴心的桌面 AI 助手。{memory_context}"},
                {"role": "user", "content": prompt.strip()},
            ],
            temperature=0.7,
        )
        
        answer = (completion.choices[0].message.content or "").strip()
        if not answer:
            print("[ask_executor] 本地模型返回为空", file=sys.stderr)
            return False
            
        print(f"[ask_executor] 生成成功，正在复制到剪贴板: {answer[:30]}...")

        # 写入剪贴板
        process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        process.communicate(answer.encode('utf-8'))

        # 发送通知
        # 为了避免 AppleScript 对引号的转义问题，采用安全的方式
        safe_prompt = prompt.replace('"', '\\"').replace("'", "\\'")
        short_prompt = safe_prompt if len(safe_prompt) < 20 else safe_prompt[:17] + "..."
        script = f'display notification "已将回答复制到剪贴板！" with title "🦊 小狐狸" subtitle "针对: {short_prompt}"'
        subprocess.run(["osascript", "-e", script])

        return True
    except Exception as e:
        print(f"[ask_executor] 发生错误: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m src.fox_executors.ask_executor <prompt>", file=sys.stderr)
        sys.exit(1)
    
    ok = run_ask(sys.argv[1])
    sys.exit(0 if ok else 1)
