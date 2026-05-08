#!/usr/bin/env python3
"""
fireworks_diagram_executor.py - 技术架构图生成器

工作流(三级 fallback,永远出图):
  1. ZenMux 云端 LLM(opus 4.7 → sonnet 4.6 → gemini 3.1 flash)
     - 快(2-30 秒)、准、按用户描述生成
     - quota 满或网络失败时自动跳下一个
  2. 模板 fallback(根据关键词选 fixture)
     - 0 秒,永远成功
     - 节点结构是模板的,title 用用户描述

依赖:
  - rsvg-convert (brew install librsvg)
  - fireworks-tech-graph skill 装在 /Users/github/.agents/skills/
  - ZenMux API key 在 /Users/github/TuriX-CUA/.clawdcursor-config.json

CLI:
  python3 fireworks_diagram_executor.py "<用户原话描述>"
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
SKILL_DIR: Path = Path("/Users/github/.agents/skills/fireworks-tech-graph")
OUTPUT_BASE: Path = Path.home() / "Desktop" / "diagrams"
ZENMUX_CONFIG: Path = Path("/Users/github/TuriX-CUA/.clawdcursor-config.json")

ZENMUX_BASE_URL: str = "https://zenmux.ai/api/v1"
ZENMUX_TIMEOUT_SECONDS: int = 60

# 优先级:opus 最强 → sonnet 次强 → gemini 最快
ZENMUX_MODELS: list[str] = [
    "anthropic/claude-opus-4.7",
    "anthropic/claude-sonnet-4.6",
    "google/gemini-3.1-flash-lite-preview",
]

# 关键词 → 模板 fixture 映射(LLM 失败时根据描述选模板)
TEMPLATE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("rag", "记忆", "memory", "向量"), "agent-memory-types-style4.json"),
    (("微服务", "microservice", "服务"), "microservices-style3.json"),
    (("agent", "智能体", "代理"), "multi-agent-style5.json"),
    (("tool", "工具调用", "function call"), "tool-call-style2.json"),
    (("api", "接口", "调用"), "api-flow-style7.json"),
]
DEFAULT_TEMPLATE: str = "system-architecture-style6.json"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[fireworks_diagram] %(message)s")


# ---------------------------------------------------------------------------
# System prompt(教 ZenMux 模型生成 fireworks JSON)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = """你是 fireworks-tech-graph 的 JSON 生成器。严格按下面 example 格式输出,只输出一个 JSON 对象,不要 markdown 不要解释。

字段(只用这些,不要发明额外字段):
- template_type: architecture / data-flow / flowchart / sequence / agent / memory
- style: 1~7 整数(3=Blueprint 蓝图最适合系统架构)
- containers[]: 用 header_prefix("01" "02"),不要用 "type" 嵌套
- nodes[].kind: rect / double_rect / cylinder
- nodes[].fill / stroke: 颜色(不要用 "style" 嵌套)
- arrows[].flow: read / control / data / async / feedback
- arrows[].source_port / target_port: top / bottom / left / right

完整 example(照抄结构,改内容):
{
  "template_type": "architecture", "style": 3, "width": 1180, "height": 700,
  "title": "示例", "subtitle": "副标题",
  "containers": [
    {"x":40,"y":96,"width":1100,"height":94,"label":"01 入口层","header_prefix":"01","stroke":"#0ea5e9","fill":"none"},
    {"x":40,"y":224,"width":1100,"height":150,"label":"02 处理层","header_prefix":"02","stroke":"#0ea5e9","fill":"none"},
    {"x":40,"y":410,"width":1100,"height":150,"label":"03 输出层","header_prefix":"03","stroke":"#0ea5e9","fill":"none"}
  ],
  "nodes": [
    {"id":"a","kind":"rect","x":80,"y":120,"width":180,"height":54,"label":"用户","type_label":"INPUT","fill":"#0b3b5e","stroke":"#67e8f9","flat":true},
    {"id":"b","kind":"double_rect","x":300,"y":116,"width":200,"height":62,"label":"网关","type_label":"GATEWAY","fill":"#0b3b5e","stroke":"#67e8f9"},
    {"id":"c","kind":"rect","x":150,"y":270,"width":260,"height":80,"label":"核心服务","type_label":"CORE","fill":"#0b3b5e","stroke":"#fde047","flat":true},
    {"id":"d","kind":"cylinder","x":480,"y":260,"width":180,"height":100,"label":"数据库","fill":"#0b3b5e","stroke":"#67e8f9"},
    {"id":"e","kind":"rect","x":150,"y":456,"width":260,"height":60,"label":"输出","type_label":"OUTPUT","fill":"#064e3b","stroke":"#34d399","flat":true}
  ],
  "arrows": [
    {"source":"a","target":"b","source_port":"right","target_port":"left","flow":"control"},
    {"source":"b","target":"c","source_port":"bottom","target_port":"top","flow":"read"},
    {"source":"c","target":"d","source_port":"right","target_port":"left","flow":"data"},
    {"source":"c","target":"e","source_port":"bottom","target_port":"top","flow":"read"}
  ],
  "legend":[{"flow":"read","label":"主流程"},{"flow":"control","label":"控制"},{"flow":"data","label":"数据"}],
  "legend_position":"bottom-right","legend_box":true,"legend_box_fill":"#0b3552","legend_x":760,"legend_y":580
}

布局约束:
- containers y 分层:96 / 224 / 410 / 594
- nodes 必须在 container 内部
- 每层 3~5 节点横向均布
- Style 3 用 fill="#0b3b5e" stroke="#67e8f9"(主) 或 stroke="#fde047"(C 位高亮)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _strip_markdown_fence(text: str) -> str:
    """去掉 ```json ... ``` markdown 包装。"""
    text = text.strip()
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            return m.group(1).strip()
    return text


def _load_zenmux_key() -> Optional[str]:
    """从 .clawdcursor-config.json 读 ZenMux API key。"""
    try:
        with open(ZENMUX_CONFIG) as f:
            return json.load(f).get("apiKey")
    except Exception as exc:
        logger.warning("读取 ZenMux key 失败: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 路径 1:ZenMux 多模型(优先级 fallback)
# ---------------------------------------------------------------------------
def generate_json_via_zenmux(description: str) -> Optional[dict]:
    """依次尝试 ZenMux 模型,首个成功的返回。全失败返回 None。"""
    api_key = _load_zenmux_key()
    if not api_key:
        logger.warning("跳过 ZenMux:没有 API key")
        return None

    for model in ZENMUX_MODELS:
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": description},
                ],
                "temperature": 0.0,
                "max_tokens": 2048,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{ZENMUX_BASE_URL}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=ZENMUX_TIMEOUT_SECONDS) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            elapsed_ms = int((time.time() - t0) * 1000)
            content = payload["choices"][0]["message"]["content"]
            cleaned = _strip_markdown_fence(content)
            parsed = json.loads(cleaned, strict=False)
            logger.info("✅ ZenMux %s 成功(%dms)", model, elapsed_ms)
            return parsed
        except urllib.error.HTTPError as exc:
            err = exc.read().decode(errors="replace")
            if "quote_exceeded" in err or '"402"' in err:
                logger.info("🚫 ZenMux %s quota 满,试下一个", model)
            else:
                logger.warning("❌ ZenMux %s HTTP %d: %s", model, exc.code, err[:100])
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("⚠️ ZenMux %s 输出解析失败: %s", model, exc)
        except Exception as exc:
            logger.warning("⚠️ ZenMux %s %s: %s", model, type(exc).__name__, exc)

    return None


# ---------------------------------------------------------------------------
# 路径 2:模板 fallback(永远成功)
# ---------------------------------------------------------------------------
def generate_json_via_template(description: str) -> Optional[dict]:
    """根据描述关键词选 fixture 模板,改 title 后返回。"""
    desc_lower = description.lower()
    template_file = DEFAULT_TEMPLATE
    for keywords, fname in TEMPLATE_KEYWORDS:
        if any(k in desc_lower for k in keywords):
            template_file = fname
            break

    template_path = SKILL_DIR / "fixtures" / template_file
    if not template_path.exists():
        logger.error("模板文件不存在: %s", template_path)
        return None

    try:
        with open(template_path) as f:
            template = json.load(f)
    except Exception as exc:
        logger.error("加载模板失败: %s", exc)
        return None

    # 把用户描述塞到 title 里
    title = description.strip()[:60]
    template["title"] = title
    template["subtitle"] = "(模板渲染 · ZenMux quota 满或离线时使用)"
    logger.info("📋 使用模板 %s,title=%s", template_file, title[:40])
    return template


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
def render_diagram(diagram_json: dict, output_dir: Path) -> Optional[tuple[Path, Optional[Path]]]:
    """渲染 JSON → SVG (+ PNG)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / "diagram.svg"
    png_path = output_dir / "diagram.png"

    template_type = str(diagram_json.get("template_type", "architecture"))
    json_str = json.dumps(diagram_json, ensure_ascii=False)

    try:
        subprocess.run(
            [
                "python3",
                str(SKILL_DIR / "scripts" / "generate-from-template.py"),
                template_type,
                str(svg_path),
                json_str,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("SVG 生成失败: %s", exc.stderr[:300])
        return None

    if not svg_path.exists():
        logger.error("SVG 没生成出来")
        return None

    try:
        subprocess.run(
            ["rsvg-convert", "-w", "1920", str(svg_path), "-o", str(png_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("PNG 转换失败(SVG 仍可用): %s", exc)
        return svg_path, None

    return svg_path, png_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("[fireworks_diagram] ❌ 缺少描述参数", file=sys.stderr)
        return 1

    description = sys.argv[1].strip()
    logger.info("📝 用户描述: %s", description[:100])

    # 1. 先试 ZenMux(快,准)
    logger.info("🌐 1/2 尝试 ZenMux 云端 LLM...")
    diagram_json = generate_json_via_zenmux(description)

    # 2. ZenMux 全失败 → 模板 fallback(永远成功)
    if diagram_json is None:
        logger.info("📋 2/2 ZenMux 不可用,降级到模板 fallback")
        diagram_json = generate_json_via_template(description)

    if diagram_json is None:
        print("[fireworks_diagram] ❌ 所有路径都失败(包括模板)", file=sys.stderr)
        return 2

    # 渲染
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_BASE / timestamp
    logger.info("🎨 渲染到 %s", output_dir)

    rendered = render_diagram(diagram_json, output_dir)
    if rendered is None:
        print("[fireworks_diagram] ❌ 渲染失败", file=sys.stderr)
        return 3

    svg_path, png_path = rendered

    # 打开 Finder
    try:
        subprocess.run(["open", str(output_dir)], check=False)
    except Exception:
        pass

    print("[fireworks_diagram] ✅ 完成")
    print(f"   SVG: {svg_path}")
    if png_path is not None:
        print(f"   PNG: {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
