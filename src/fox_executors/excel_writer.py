#!/usr/bin/env python3
"""
Excel 写入原子执行器 — AppleScript 操控 Microsoft Excel + openpyxl 兜底。

用法:
    python excel_writer.py <output_xlsx_path> <data_json>
    python excel_writer.py ~/Desktop/report.xlsx '[{"日期":"2026-04-30","金额":"1234.56","项目":"差旅费"}]'

方案 A: AppleScript 操控 Microsoft Excel（无需 openpyxl，支持中文表头）
方案 B: openpyxl 直接写 .xlsx 文件（用户没装 Excel 时 fallback）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# ─── openpyxl 可用性检测 ──────────────────────────────────────────
try:
    import openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False


def _expand_path(p: str) -> str:
    """展开 ~ 和环境变量。"""
    return str(Path(p).expanduser().resolve())


def _write_via_applescript(output_path: str, headers: list[str], rows: list[list[str]]) -> bool:
    """
    方案 A: AppleScript 操控 Microsoft Excel 写入数据。
    用 NSAppleScript 继承辅助功能权限，不抢焦点。
    """
    # 构建单元格值设置语句
    set_cells_lines = []
    # 表头 (row 1)
    for col_idx, header in enumerate(headers, 1):
        col_letter = chr(ord('A') + col_idx - 1) if col_idx <= 26 else f"A{col_idx}"
        escaped = header.replace('"', '\\"').replace('\\', '\\\\')
        set_cells_lines.append(
            f'set value of range "{col_letter}1" to "{escaped}"'
        )
    # 数据行 (row 2+)
    for row_idx, row in enumerate(rows, 2):
        for col_idx, val in enumerate(row, 1):
            col_letter = chr(ord('A') + col_idx - 1) if col_idx <= 26 else f"A{col_idx}"
            escaped = str(val).replace('"', '\\"').replace('\\', '\\\\')
            set_cells_lines.append(
                f'set value of range "{col_letter}{row_idx}" to "{escaped}"'
            )

    set_cells_block = '\n        '.join(set_cells_lines)

    # 保存路径的 POSIX 形式
    posix_path = Path(output_path).as_posix()

    applescript = f'''
    tell application "Microsoft Excel"
        activate
        set newBook to make new workbook
        tell active sheet of newBook
        {set_cells_block}
        end tell
        save active workbook in POSIX file "{posix_path}"
        close active workbook saving no
    end tell
    '''

    print("[excel_writer] ⚙️  AppleScript 操控 Excel 写入...")
    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            print(f"[excel_writer] ❌ AppleScript 失败: {err}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print("[excel_writer] ❌ AppleScript 超时 (60s)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[excel_writer] ❌ AppleScript 异常: {e}", file=sys.stderr)
        return False


def _write_via_openpyxl(output_path: str, headers: list[str], rows: list[list[str]]) -> bool:
    """
    方案 B: openpyxl 直接写 .xlsx 文件（无需 Excel 应用）。
    """
    if not _HAS_OPENPYXL:
        print("[excel_writer] ❌ openpyxl 未安装，无法 fallback", file=sys.stderr)
        return False

    print("[excel_writer] ⚙️  openpyxl 写入 .xlsx...")
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(headers)
        for row in rows:
            ws.append(row)
        wb.save(output_path)
        return True
    except Exception as e:
        print(f"[excel_writer] ❌ openpyxl 写入失败: {e}", file=sys.stderr)
        return False


def run(output_path: str, data_json: str) -> int:
    """
    主入口：解析 JSON → 尝试方案 A → fallback 方案 B。
    返回 0=成功，1=失败。
    """
    # 解析 JSON 数据
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError as e:
        print(f"[excel_writer] ❌ JSON 解析失败: {e}", file=sys.stderr)
        return 1

    if not data or not isinstance(data, list):
        print("[excel_writer] ❌ 数据为空或格式不对（需要 list of dict）", file=sys.stderr)
        return 1

    # 提取表头和数据行
    headers = list(data[0].keys())
    rows = [[str(item.get(h, "")) for h in headers] for item in data]
    row_count = len(rows)

    # 展开输出路径
    output_path = _expand_path(output_path)

    # 确保输出目录存在
    output_dir = Path(output_path).parent
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    # 方案 A: AppleScript 操控 Excel
    success = _write_via_applescript(output_path, headers, rows)

    # 方案 B: openpyxl 兜底
    if not success:
        print("[excel_writer] ⚠️  AppleScript 失败，尝试 openpyxl fallback...")
        success = _write_via_openpyxl(output_path, headers, rows)

    if success:
        print(f"[excel_writer] ✅ wrote {row_count} rows → {output_path}")
        return 0
    else:
        print("[excel_writer] ❌ 所有方案均失败", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python excel_writer.py <output_xlsx_path> <data_json>", file=sys.stderr)
        print('示例: python excel_writer.py ~/out.xlsx \'[{"日期":"2026-04-30","金额":"1234.56","项目":"差旅费"}]\'', file=sys.stderr)
        sys.exit(1)

    sys.exit(run(sys.argv[1], sys.argv[2]))
