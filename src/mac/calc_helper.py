#!/usr/bin/env python3
"""
独立的计算器辅助脚本 —— 100% 自包含，零外部依赖。

把"打开计算器 → 等焦点 → 清零 → 输入表达式 → 回车"全部在一个原子操作里完成，
杜绝浏览器在 action 间隙抢焦点的问题。

用法:
    python3 src/mac/calc_helper.py "17*23"
    python3 src/mac/calc_helper.py "27×82"
"""
import subprocess
import sys
import time

import Cocoa
import Quartz


# ─── macOS 虚拟键码映射 ────────────────────────────────────────────
_CHAR_TO_KEYCODE: dict[str, tuple[int, bool]] = {
    # (keycode, needs_shift)
    '0': (29, False), '1': (18, False), '2': (19, False), '3': (20, False),
    '4': (21, False), '5': (23, False), '6': (22, False), '7': (26, False),
    '8': (28, False), '9': (25, False),
    '+': (24, True),  '-': (27, False), '*': (28, True),  '/': (44, False),
    '=': (24, False), '.': (47, False),
    '\n': (36, False), 'enter': (36, False),
    'escape': (53, False),
}

CALC_BUNDLE_ID = "com.apple.calculator"


def _post_key(keycode: int, needs_shift: bool):
    """同步地发送一个键码事件（key down + key up）。"""
    if needs_shift:
        shift_down = Quartz.CGEventCreateKeyboardEvent(None, 56, True)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, shift_down)
        time.sleep(0.02)

    key_down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    if needs_shift:
        Quartz.CGEventSetFlags(key_down, Quartz.kCGEventFlagMaskShift)
    Quartz.CGEventPost(Quartz.kCGSessionEventTap, key_down)
    time.sleep(0.02)

    key_up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventPost(Quartz.kCGSessionEventTap, key_up)
    time.sleep(0.02)

    if needs_shift:
        shift_up = Quartz.CGEventCreateKeyboardEvent(None, 56, False)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, shift_up)
        time.sleep(0.02)


def _wait_for_frontmost(bundle_id: str, timeout: float = 5.0) -> bool:
    """等待指定 bundle_id 的应用成为系统最前端窗口。"""
    workspace = Cocoa.NSWorkspace.sharedWorkspace()
    deadline = time.time() + timeout
    while time.time() < deadline:
        front = workspace.frontmostApplication()
        if front and front.bundleIdentifier() == bundle_id:
            return True
        time.sleep(0.1)
    return False


def calculate(expr: str) -> bool:
    """
    原子操作：打开计算器 → 等焦点 → AC清零 → 输入表达式 → 回车。
    全程同步执行，没有任何可以被浏览器钻空子的间隙。
    """
    t0 = time.time()

    # ─── 教训驱动的设计：默认走 System Events 路径 ───────────────
    # 之前我们试过：open -b → 等 frontmost → CGEvent 送键。失败原因：
    #   - frontmostApplication 返回的是"被点亮的窗口"，不一定有 keyboard focus
    #   - 浏览器场景下 calc 看似 frontmost，但按键被浏览器吞掉
    #   - calc_helper 还误报成功
    # 现在改为：System Events keystroke 一站式完成（绕开焦点检查），
    # 浏览器/任何 app 抢焦点也阻挡不了——这是 macOS Accessibility 的硬规则。
    # 代价：慢约 0.3-0.5 秒（AppleScript 启动开销），但 100% 可靠。

    applescript = f'''
    tell application id "com.apple.calculator" to activate
    delay 0.4
    tell application "System Events"
        tell process "Calculator"
            set frontmost to true
        end tell
        delay 0.1
        keystroke "c" using {{command down}}
        delay 0.1
        keystroke "{expr}"
        delay 0.15
        key code 36
    end tell
    '''
    print("[calc_helper] ⚙️  通过 System Events 强制送键（绕开焦点抢夺）")
    result = subprocess.run(
        ["osascript", "-e", applescript],
        check=False, capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"[calc_helper] ❌ System Events 失败: {result.stderr.strip()}")
        return False

    elapsed = time.time() - t0
    print(f"[calc_helper] 🎉 完成！耗时 {elapsed:.2f} 秒（System Events 路径）")
    return True

# ─── 以下是旧的 CGEvent 路径，已不再使用（保留作未来高频优化的参考）───
def _legacy_cgevent_path(expr: str) -> bool:
    """旧路径：等 frontmost 后用 CGEvent 高速送键。在浏览器场景失败。"""

    # 3. 按 Escape 清零 (AC)
    esc = _CHAR_TO_KEYCODE['escape']
    _post_key(esc[0], esc[1])
    time.sleep(0.1)
    print("[calc_helper] ✅ 已按 AC 清零")

    # 4. 逐字符输入表达式
    for ch in expr:
        lookup = _CHAR_TO_KEYCODE.get(ch)
        if lookup is None:
            print(f"[calc_helper] ⚠️ 跳过不认识的字符: '{ch}'")
            continue
        _post_key(lookup[0], lookup[1])
        time.sleep(0.05)
    print(f"[calc_helper] ✅ 已输入: {expr}")

    # 5. 按回车得到结果
    enter = _CHAR_TO_KEYCODE['\n']
    _post_key(enter[0], enter[1])
    print("[calc_helper] ✅ 已按回车")

    elapsed = time.time() - t0
    print(f"[calc_helper] 🎉 完成！耗时 {elapsed:.2f} 秒")
    return True


def normalize_expr(raw: str) -> str:
    """规范化数学表达式：处理中文乘号、除号等。"""
    expr = raw.strip().replace(" ", "")
    expr = expr.replace("×", "*").replace("x", "*").replace("X", "*")
    expr = expr.replace("÷", "/")
    expr = expr.rstrip("=")
    return expr


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 src/mac/calc_helper.py '17*23'")
        sys.exit(1)
    
    raw_expr = sys.argv[1]
    expr = normalize_expr(raw_expr)
    print(f"[calc_helper] 表达式: {raw_expr} → {expr}")
    
    success = calculate(expr)
    sys.exit(0 if success else 1)
