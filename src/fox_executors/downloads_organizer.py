#!/usr/bin/env python3
"""
下载文件夹智能归类原子执行器 (Fox-path Executor)
扫描 ~/Downloads，按文件类型 + LLM 智能分类到子文件夹。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# 文件扩展名 → 默认分类
_EXT_CATEGORIES: dict[str, str] = {
    # 文档
    ".pdf": "文档", ".doc": "文档", ".docx": "文档", ".txt": "文档",
    ".rtf": "文档", ".odt": "文档", ".pages": "文档",
    # 表格/演示
    ".xls": "表格", ".xlsx": "表格", ".csv": "表格",
    ".ppt": "演示", ".pptx": "演示", ".key": "演示",
    # 图片
    ".jpg": "图片", ".jpeg": "图片", ".png": "图片", ".gif": "图片",
    ".bmp": "图片", ".svg": "图片", ".webp": "图片", ".heic": "图片",
    ".tiff": "图片", ".ico": "图片",
    # 压缩包
    ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包",
    ".tar": "压缩包", ".gz": "压缩包", ".bz2": "压缩包",
    ".dmg": "安装包", ".pkg": "安装包", ".app": "安装包",
    # 音视频
    ".mp3": "音频", ".wav": "音频", ".aac": "音频", ".flac": "音频",
    ".mp4": "视频", ".mov": "视频", ".avi": "视频", ".mkv": "视频",
    ".webm": "视频",
    # 代码
    ".py": "代码", ".js": "代码", ".ts": "代码", ".html": "代码",
    ".css": "代码", ".json": "代码", ".xml": "代码", ".yaml": "代码",
    ".yml": "代码", ".sh": "代码", ".sql": "代码",
    # 字体
    ".ttf": "字体", ".otf": "字体", ".woff": "字体", ".woff2": "字体",
}


def _categorize_by_ext(filename: str) -> str:
    """根据扩展名确定分类。"""
    ext = Path(filename).suffix.lower()
    return _EXT_CATEGORIES.get(ext, "其他")


def _ask_llm_category(filenames: list[str]) -> dict[str, str]:
    """批量让 LLM 为无法自动归类的文件推荐分类。"""
    try:
        from openai import OpenAI
    except ImportError:
        return {}

    base_url = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    api_key = os.environ.get("FOX_LOCAL_LLM_API_KEY", "not-needed")

    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)
        models = client.models.list()
        model_id = models.data[0].id if models.data else None
        if not model_id:
            return {}

        file_list = "\n".join(f"- {f}" for f in filenames)
        completion = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "你是文件分类助手。为每个文件推荐一个简短中文分类名（2-4字），如：发票、合同、简历、报告、截图、安装包等。只输出JSON，格式：{\"文件名\": \"分类\"}"},
                {"role": "user", "content": f"请为以下文件分类：\n{file_list}"},
            ],
            temperature=0.1,
        )
        text = (completion.choices[0].message.content or "").strip()
        # 提取 JSON（支持嵌套花括号）
        try:
            start = text.index("{")
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return json.loads(text[start : i + 1])
        except (ValueError, json.JSONDecodeError):
            pass
    except Exception as e:
        print(f"[downloads_organizer] ⚠️ LLM 分类失败: {e}")
    return {}


def run(source_dir: str = "~/Downloads", dry_run: bool = False) -> int:
    """扫描并归类下载文件夹。"""
    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        print(f"[downloads_organizer] ❌ 目录不存在: {src}", file=sys.stderr)
        return 1

    print(f"[downloads_organizer] 📂 扫描: {src}")

    # 收集文件
    files = [f for f in src.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not files:
        print("[downloads_organizer] 📭 没有需要归类的文件")
        return 0

    # 第一轮：按扩展名分类
    category_map: dict[str, str] = {}  # filename -> category
    unclassified: list[str] = []

    for f in files:
        cat = _categorize_by_ext(f.name)
        category_map[f.name] = cat
        if cat == "其他":
            unclassified.append(f.name)

    # 第二轮：LLM 智能分类"其他"文件
    if unclassified and len(unclassified) <= 30:
        print(f"[downloads_organizer] 🤖 LLM 分类 {len(unclassified)} 个未识别文件...")
        llm_cats = _ask_llm_category(unclassified)
        category_map.update(llm_cats)

    # 统计
    cat_counts: dict[str, int] = {}
    for cat in category_map.values():
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    print(f"[downloads_organizer] 📊 分类结果: {dict(cat_counts)}")

    # 移动文件
    moved = 0
    for f in files:
        cat = category_map.get(f.name, "其他")
        target_dir = src / cat
        target = target_dir / f.name

        if target.exists() and target != f:
            # 重名加序号
            stem = f.stem
            suffix = f.suffix
            i = 1
            while target.exists():
                target = target_dir / f"{stem} ({i}){suffix}"
                i += 1

        if dry_run:
            print(f"  [DRY] {f.name} → {cat}/")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(f), str(target))
                moved += 1
            except Exception as e:
                print(f"  ⚠️ 移动失败 {f.name}: {e}")

    action = "将归类" if dry_run else "已归类"
    print(f"[downloads_organizer] ✅ {action} {moved}/{len(files)} 个文件")

    # 复制报告到剪贴板
    report_lines = [f"下载文件夹归类报告 ({len(files)} 个文件)"]
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        report_lines.append(f"  {cat}: {count} 个")
    try:
        pbcopy = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        pbcopy.communicate("\n".join(report_lines).encode("utf-8"))
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "~/Downloads"
    dry = "--dry-run" in sys.argv
    sys.exit(run(src_dir, dry_run=dry))
