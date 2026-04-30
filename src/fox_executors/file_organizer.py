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

        files_to_move = [
            p
            for p in src_path.glob(glob_pattern)
            if p.is_file() and p.parent.resolve() == src_path and p.resolve() != target_path.resolve()
        ]
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
