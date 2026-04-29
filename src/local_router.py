"""
本地意图路由器 — 连接本机 OpenAI 兼容端点（LM Studio / Ollama），Zero-shot JSON 路由。

环境变量:
  FOX_LOCAL_LLM_BASE_URL  默认 http://127.0.0.1:1234/v1  (LM Studio)
  FOX_LOCAL_LLM_MODEL     默认环境内的第一个可用模型可留空由服务端决定，若为空则用模型列表自动探测
  FOX_LOCAL_LLM_API_KEY   默认 lm-studio（LM Studio 常忽略；Ollama 可用任意非空字符串）

输出约定（严格 JSON 对象，单行）:
  {"skill": "calculator", "args": {"expression": "18*24"}}
  {"skill": "open_app", "args": {"app": "safari"}}
  {"skill": "fallback"}
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError as e:  # pragma: no cover
    raise ImportError("local_router requires the 'openai' package") from e

# 默认 LM Studio；Ollama OpenAI 兼容层一般为 http://127.0.0.1:11434/v1
_DEFAULT_BASE = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
_DEFAULT_KEY = os.environ.get("FOX_LOCAL_LLM_API_KEY", "lm-studio")

SYSTEM_PROMPT = """你是 LittleFox 的本地意图路由器。根据用户输入，只输出一个 JSON 对象，不要 markdown，不要解释。

技能四选一：
1) calculator — 仅适合「纯算术 / 公式计算」，需要用户在计算器里完成或自动化输入表达式。
2) open_app — 仅适合「纯粹打开或启动某个 Mac 应用」，不包含任何后续动作。
   > [!IMPORTANT]
   > 如果用户要的是「打开应用并在里面做某件事」（如：打开Chrome查新闻、打开备忘录写日记、打开计算器算个大数），**绝对不允许**选 open_app，**必须选 fallback**！open_app 只能用于单纯的“打开XXX”，不做任何后续操作。
3) send_wechat — 只要用户的意图包含发消息、发微信、告诉某人某事（哪怕指令是以“打开微信”开头），都必须选此项。
4) fallback — 复杂任务、需要搜索/看图/写代码/系统设置/多步操作/在某个应用内做具体事情（除了发微信）/不确定时一律选它。

输出格式（严格）：
{"skill":"calculator","args":{"expression":"..."}}
{"skill":"open_app","args":{"app":"备忘录"}}
{"skill":"send_wechat","args":{"contact":"张三","message":"今晚吃饭吗"}}
{"skill":"fallback"}

open_app 的 app 字段必须提取用户提到的准确名称（中英文皆可），不要自己乱翻译。
calculator 的 expression 里把运算写成一行表达式。
send_wechat 必须从用户的话中准确提取联系人(contact)和内容(message)。"""


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法解析 JSON: {text[:200]}")


def _normalize_route(raw: dict[str, Any]) -> dict[str, Any]:
    skill = str(raw.get("skill", "fallback")).lower().strip()
    if skill in ("calc", "math", "calculator"):
        skill = "calculator"
    elif skill in ("open", "open_app", "launch", "app"):
        skill = "open_app"
    elif skill in ("wechat", "send_wechat", "message"):
        skill = "send_wechat"
    elif skill not in ("calculator", "open_app", "send_wechat"):
        skill = "fallback"

    args = raw.get("args")
    if not isinstance(args, dict):
        args = {}

    if skill == "calculator":
        expr = args.get("expression") or args.get("expr") or raw.get("expression")
        if not expr:
            return {"skill": "fallback"}
        return {"skill": "calculator", "args": {"expression": str(expr).strip()}}

    if skill == "open_app":
        app = args.get("app") or args.get("name") or raw.get("app")
        if not app:
            return {"skill": "fallback"}
        return {"skill": "open_app", "args": {"app": str(app).strip()}}

    if skill == "send_wechat":
        contact = args.get("contact") or args.get("name") or raw.get("contact")
        message = args.get("message") or args.get("text") or raw.get("message")
        if not contact or not message:
            return {"skill": "fallback"}
        return {"skill": "send_wechat", "args": {"contact": str(contact).strip(), "message": str(message).strip()}}

    return {"skill": "fallback"}


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


def route_task(
    user_task: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    调用本地聊天模型，返回归一化路由 dict:
      {"skill":"calculator"|"open_app"|"fallback", "args"?}
    """
    client = OpenAI(
        base_url=base_url or _DEFAULT_BASE,
        api_key=api_key or _DEFAULT_KEY,
        timeout=timeout,
    )
    use_model = model or _default_model(client)
    if not use_model:
        raise ValueError(
            "请设置环境变量 FOX_LOCAL_LLM_MODEL，或确保本机 API 支持 GET /v1/models 且至少有一个模型。"
        )
    completion = client.chat.completions.create(
        model=use_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_task.strip()},
        ],
        temperature=0.0,
    )

    content = (completion.choices[0].message.content or "").strip()
    raw = _extract_json_object(content)
    return _normalize_route(raw)


def route_task_safe(user_task: str, **kwargs: Any) -> dict[str, Any]:
    """路由失败时退回 fallback，不抛异常。"""
    try:
        return route_task(user_task, **kwargs)
    except Exception as e:
        logger.warning("local_router fallback due to: %s", e)
        return {"skill": "fallback"}
