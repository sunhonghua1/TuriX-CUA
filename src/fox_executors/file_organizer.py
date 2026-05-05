#!/usr/bin/env python3
"""
文件搬运原子执行器（独立脚本，零外部依赖）。

用法:
    python file_organizer.py <source_dir> <target_folder_name> <glob_pattern>
示例:
    python file_organizer.py ~/Desktop "04-30 财务报销" "Screenshot*.png"
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def organize_files(source_dir: str, target_folder_name: str, glob_pattern: str) -> bool:
    try:
        src_path = Path(source_dir).expanduser().resolve()
        if not src_path.is_dir():
            raise ValueError(f"源目录不存在或不是目录: {source_dir}")

        target_path = src_path / target_folder_name
        target_path.mkdir(parents=True, exist_ok=True)

        # 支持多个模式，用逗号分隔
        patterns = [p.strip() for p in glob_pattern.split(",") if p.strip()]
        if not patterns:
            patterns = ["*"]

        # 智能增强：如果是关于发票的，增加常见匹配模式
        invoice_keywords = ["发票", "invoice", "receipt", "bill", "报销"]
        enhanced_patterns = []
        for p in patterns:
            enhanced_patterns.append(p)
            # 如果模式包含发票关键词，或者模式比较宽泛且目录里有发票
            low_p = p.lower()
            if any(k in low_p for k in invoice_keywords):
                # 增加通用的 PDF 匹配，因为发票通常是 PDF
                if "*.pdf" not in enhanced_patterns:
                    enhanced_patterns.append("*.pdf")
                if "*发票*" not in enhanced_patterns:
                    enhanced_patterns.append("*发票*")
                if "*Invoice*" not in enhanced_patterns:
                    enhanced_patterns.append("*Invoice*")

        files_to_move = []
        seen_paths = set()
        for p in enhanced_patterns:
            for found in src_path.glob(p):
                # 排除目录，排除目标文件夹本身，确保是当前层级的文件
                if (
                    found.is_file() 
                    and found.parent.resolve() == src_path 
                    and found.resolve() != target_path.resolve()
                    and found.suffix.lower() != ".ds_store"
                ):
                    if found.resolve() not in seen_paths:
                        files_to_move.append(found)
                        seen_paths.add(found.resolve())

        count = len(files_to_move)
        if count > 0:
            subprocess.run(
                ["mv", *(str(p) for p in files_to_move), str(target_path)],
                check=True,
            )

        print(f"[file_organizer] ✅ 移动 {count} 个文件 → {target_folder_name}/")
        return True
    except Exception as exc:
        print(f"[file_organizer] ❌ {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "用法: python file_organizer.py <source_dir> <target_folder_name> <glob_pattern>",
            file=sys.stderr,
        )
        sys.exit(1)

    ok = organize_files(sys.argv[1], sys.argv[2], sys.argv[3])
    sys.exit(0 if ok else 1)
