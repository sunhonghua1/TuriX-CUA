#!/usr/bin/env python3
"""
计算器原子执行器 — 调用已验证的 calc_helper（同步焦点 + 键入）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# TuriX-CUA 根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CALC_SCRIPT = _PROJECT_ROOT / "src" / "mac" / "calc_helper.py"


def run(expression: str) -> int:
    """运行计算；返回进程退出码 0=成功。"""
    if not _CALC_SCRIPT.is_file():
        print(f"[calc_executor] 找不到脚本: {_CALC_SCRIPT}", file=sys.stderr)
        return 1
    proc = subprocess.run(
        [sys.executable, str(_CALC_SCRIPT), expression],
        cwd=str(_PROJECT_ROOT),
    )
    return int(proc.returncode)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m src.fox_executors.calc_executor '44*55'", file=sys.stderr)
        sys.exit(1)
    sys.exit(run(" ".join(sys.argv[1:])))
