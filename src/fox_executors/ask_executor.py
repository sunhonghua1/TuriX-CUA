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

_DEFAULT_BASE = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
_DEFAULT_KEY = os.environ.get("FOX_LOCAL_LLM_API_KEY", "lm-studio")

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

        print(f"[ask_executor] 正在调用本地模型 ({use_model}) 回答...")
        completion = client.chat.completions.create(
            model=use_model,
            messages=[
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
