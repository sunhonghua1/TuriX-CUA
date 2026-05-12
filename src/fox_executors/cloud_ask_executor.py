#!/usr/bin/env python3
"""
云端问答执行器 — 调用 DeepSeek API 生成结果，复制到剪贴板，并弹出系统通知。

接口与 ask_executor.py 完全一致:
  入口: 1 个位置参数 (prompt 字符串)
  调用: python cloud_ask_executor.py "<prompt>"
  退出: exit 0 = 成功 / exit 1 = 失败
  副作用: LLM 答案写入系统剪贴板 (pbcopy) + osascript 通知
  失败: 原因输出到 stderr

区别:
  - 走 DeepSeek 云端 API (3-8s vs 本地 27B 110s)
  - 省略本地记忆检索 (云端无意义且增加延迟)
  - 通知标题含 ☁️ 区分本地/云端
"""
from __future__ import annotations

import os
import subprocess
import sys

try:
    from openai import OpenAI
except ImportError:
    print("[cloud_ask] 缺少 openai 库，请运行: pip install openai", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# 环境配置 (可通过 env 覆盖)
# ---------------------------------------------------------------------------
_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
_TIMEOUT = float(os.environ.get("DEEPSEEK_TIMEOUT", "30"))

_SYSTEM_PROMPT = (
    "你是小狐狸 (LittleFox)，一个贴心的桌面 AI 助手。"
    "请用简洁、友好的中文回答用户的问题。"
    "回答要直接、准确，避免冗余解释。"
)


def run_cloud_ask(prompt: str) -> bool:
    """调用 DeepSeek API 回答问题，结果写入剪贴板。返回 True = 成功。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print(
            "[cloud_ask] 缺少 DEEPSEEK_API_KEY 环境变量，请先 export DEEPSEEK_API_KEY=...",
            file=sys.stderr,
        )
        return False

    # v1.1: 防呆 — 检测占位符样本被字面粘贴的情况
    if not api_key.isascii():
        print(
            f"[cloud_ask] DEEPSEEK_API_KEY 含非 ASCII 字符 "
            f"(前 10 字: {api_key[:10]!r}), "
            f"很可能 ~/.zshrc 里粘贴了占位符样本。"
            f"请改成真实 sk-... 开头的 key。",
            file=sys.stderr,
        )
        return False


    try:
        client = OpenAI(
            base_url=_BASE_URL,
            api_key=api_key,
            timeout=_TIMEOUT,
        )

        print(f"[cloud_ask] 调用 DeepSeek ({_MODEL})...")
        completion = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt.strip()},
            ],
            temperature=0.7,
        )

        answer = (completion.choices[0].message.content or "").strip()
        if not answer:
            print("[cloud_ask] DeepSeek 返回空内容", file=sys.stderr)
            return False

        preview = answer[:30] + ("..." if len(answer) > 30 else "")
        print(f"[cloud_ask] 生成成功, 复制到剪贴板: {preview}")

        # 写入剪贴板
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(answer.encode("utf-8"))

        # 系统通知 (☁️ 区分云端)
        safe_prompt = prompt.replace('"', '\\"').replace("'", "\\'")
        short_prompt = safe_prompt[:17] + "..." if len(safe_prompt) > 20 else safe_prompt
        script = (
            f'display notification "已将回答复制到剪贴板！" '
            f'with title "🦊 小狐狸 ☁️" subtitle "针对: {short_prompt}"'
        )
        subprocess.run(["osascript", "-e", script], capture_output=True)

        return True

    except Exception as e:
        print(f"[cloud_ask] 发生错误: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python cloud_ask_executor.py <prompt>", file=sys.stderr)
        sys.exit(1)

    ok = run_cloud_ask(sys.argv[1])
    sys.exit(0 if ok else 1)
