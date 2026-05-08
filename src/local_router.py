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
from pathlib import Path
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError as e:  # pragma: no cover
    raise ImportError("local_router requires the 'openai' package") from e

# 优先使用专门的路由器端点（8001），否则回退到通用端点（8000）
_DEFAULT_BASE = os.environ.get("FOX_ROUTER_LLM_BASE_URL", os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1"))
_DEFAULT_KEY = os.environ.get("FOX_LOCAL_LLM_API_KEY", "not-needed")

_REAL_DESKTOP = str(Path.home() / "Desktop")
_REAL_HOME = str(Path.home())

def _build_system_prompt() -> str:
    return f"""你是 LittleFox 的本地意图路由器。根据用户输入，只输出一个 JSON 对象，不要 markdown，不要解释。

重要：本机真实路径为 {_REAL_DESKTOP}（桌面）。所有路径必须使用 ~ 或真实路径，绝对不要用 /Users/yourname 或其他占位符。

技能九选一：
1) calculator — 仅适合「纯算术 / 公式计算」。
2) open_app — 仅适合「纯粹打开或启动某个 Mac 应用」。
3) send_wechat — 只要意图包含发消息、发微信。
4) local_ask — 只要提到翻译、写东西、问答、聊天、或者让助手「记住」、「保存」、「记录」某事（纯文本性质的记忆）。参数: prompt (用户原始输入).
5) file_organizer — 文件搬运。参数: source_dir (必须用 ~ 开头，如 ~/Desktop/05月投递箱), target_folder_name, glob_pattern (支持逗号分隔或关键词如'发票').
6) excel_writer — 生成 Excel 报表。参数: target_path, data (结构化对象).
7) invoice_summarizer — 只要提到提取发票信息、发票汇总表、生成发票Excel等。参数: source_dir (发票所在文件夹), output_path (保存的xlsx路径).
8) financial_reporter — 只要提到生成财务报告、分析财务数据、写分析摘要等。参数: excel_path (通常是 ~/Desktop/05月发票汇总.xlsx), output_path (保存的docx路径).
9) fallback — 复杂 GUI 任务、多步操作、视觉识别。

输出格式（严格）：
{{"skill":"file_organizer","args":{{"source_dir":"~/Desktop/05月投递箱","target_folder_name":"05月报销","glob_pattern":"*"}}}}
{{"skill":"excel_writer","args":{{"target_path":"~/Desktop/report.xlsx","data":{{"header":["日期","项目","金额"],"rows":[...]}}}}}}
{{"skill":"invoice_summarizer","args":{{"source_dir":"~/Desktop/05月投递箱","output_path":"~/Desktop/05月发票汇总.xlsx"}}}}
{{"skill":"financial_reporter","args":{{"excel_path":"~/Desktop/05月发票汇总.xlsx","output_path":"~/Desktop/财务分析报告.docx"}}}}
{{"skill":"fallback"}}

open_app 的 app 字段必须提取用户提到的准确名称（中英文皆可），不要自己乱翻译。
calculator 的 expression 里把运算写成一行表达式。
send_wechat 必须从用户的话中准确提取联系人(contact)和内容(message)。
local_ask 的 prompt 必须包含用户需要回答/翻译/生成的完整原始需求。"""


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
    elif skill in ("ask", "local_ask", "chat", "qa", "text", "translate"):
        skill = "local_ask"
    elif skill in ("file", "organize", "move", "file_organizer"):
        skill = "file_organizer"
    elif skill in ("excel", "excel_writer", "spreadsheet"):
        skill = "excel_writer"
    elif skill in ("word", "word_writer", "doc", "docx"):
        skill = "word_writer"
    elif skill in ("invoice", "invoice_summarizer", "summarizer"):
        skill = "invoice_summarizer"
    elif skill in ("financial", "report", "financial_reporter", "finance"):
        skill = "financial_reporter"
    elif skill not in ("calculator", "open_app", "send_wechat", "local_ask", "file_organizer", "excel_writer", "word_writer", "invoice_summarizer", "financial_reporter"):
        skill = "fallback"

    args = raw.get("args")
    if not isinstance(args, dict):
        args = {}

    # 修正路径中的占位符用户名 (e.g. /Users/yourname -> /Users/real_user)
    real_home = _REAL_HOME
    for key in ("source_dir", "target_path", "excel_path", "output_path"):
        if key in args and isinstance(args[key], str):
            path_val = args[key]
            # Replace any /Users/ANYTHING/ prefix with real home
            import re as _re
            path_val = _re.sub(r'^/Users/[^/]+/', real_home.rstrip('/') + '/', path_val)
            # Also expand ~ to real home (in case it wasn't already)
            path_val = path_val.replace('~', real_home)
            args[key] = path_val

    # 返回归一化后的数据
    if skill == "fallback":
        return {"skill": "fallback"}
    
    return {"skill": skill, "args": args}


def _get_relevant_memories(query: str, limit: int = 3) -> str:
    """从本地 SQLite 数据库中检索相关记忆。"""
    import sqlite3
    db_path = Path.home() / ".ninetail-fox" / "conversations.sqlite"
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        # 简单的关键词模糊匹配（生产环境建议使用向量搜索）
        keywords = [k for k in re.split(r'\s+', query) if len(k) > 1]
        if not keywords:
            cursor = conn.execute("SELECT content FROM conversation_log WHERE role='user' ORDER BY timestamp DESC LIMIT ?", (limit,))
        else:
            where_clause = " OR ".join(["content LIKE ?"] * len(keywords))
            params = [f"%{k}%" for k in keywords] + [limit]
            cursor = conn.execute(f"SELECT content FROM conversation_log WHERE role='user' AND ({where_clause}) ORDER BY timestamp DESC LIMIT ?", params)
        
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return ""
        mem_text = "\n".join([f"- {row['content']}" for row in rows])
        return f"\n相关历史记忆：\n{mem_text}\n"
    except Exception as e:
        logger.warning(f"检索记忆失败: {e}")
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
    
    # 注入记忆
    memory_context = _get_relevant_memories(user_task)
    full_prompt = _build_system_prompt() + memory_context

    completion = client.chat.completions.create(
        model=use_model,
        messages=[
            {"role": "system", "content": full_prompt},
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
