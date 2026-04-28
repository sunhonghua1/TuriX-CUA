"""
P3.6 · 高频任务 fast-path skill 库

设计原则
--------
- **绕过 brain/actor**：直接用预设动作清单走 controller.multi_act()，省下 brain 看图 + 推理 ~19s/step。
- **只用键盘 / spotlight 类动作**：避免依赖 mac UI tree（解析慢、易碎），保证 fast-path 真的"快"。
- **不命中即透明降级**：matcher 返回 False 时，主循环走原有 brain → actor 流程，对未覆盖任务零副作用。
- **可扩展**：新增 skill 只需追加一个 QuickSkill 实例，无需改主循环逻辑。

工作流
------
    用户任务 → _try_quick_skill()
        ├─ matcher 命中且 builder 返回非空 actions
        │     → controller.multi_act() → 写 plan_history → return True
        └─ 都不命中
              → return False，主循环继续走 brain/actor
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

# QuickSkill 用 dict 列表表达 actions，与 ActionItem schema 保持完全一致：
#   [{"open_app": {"app_name": "Calculator"}}, {"input_text": {"text": "17*23"}}, ...]
ActionDict = dict
ActionList = list[ActionDict]


@dataclass(frozen=True)
class QuickSkill:
    """
    一条 fast-path 快捷技能。

    Attributes:
        name: 技能标识，用于日志和 plan_history。
        matcher: 任务文本判断器，True 表示该 skill 想接管。
        builder: 任务文本 → actions list；返回 [] 表示放弃（让 brain 接管）。
    """
    name: str
    matcher: Callable[[str], bool]
    builder: Callable[[str], ActionList]


# ─── 工具函数：从中文/英文任务文本里抽数学表达式 ─────────────────────
_MATH_EXPR_RE = re.compile(
    r"(\-?\d+(?:\.\d+)?(?:\s*[+\-\*\×x*\/÷=]\s*\-?\d+(?:\.\d+)?)+)"
)


def _normalize_math_expr(raw: str) -> str:
    """把'17 × 23' / '17 x 23' / '17*23' 都规范成计算器认识的 '17*23'。"""
    expr = raw.strip().replace(" ", "")
    expr = expr.replace("×", "*").replace("x", "*").replace("X", "*")
    expr = expr.replace("÷", "/")
    # 去掉尾部 = 号（很多任务写成 "17*23="）
    expr = expr.rstrip("=")
    return expr


def _extract_math_expr(task: str) -> Optional[str]:
    match = _MATH_EXPR_RE.search(task)
    if not match:
        return None
    return _normalize_math_expr(match.group(1))


# ─── Skill 1：计算器（演示场景神器）─────────────────────────────────
def _matcher_calculator(task: str) -> bool:
    t = task.lower()
    keyword_hit = any(k in t for k in ("计算器", "calculator", "calc"))
    expr_hit = _extract_math_expr(task) is not None
    # 必须同时命中关键词 + 有数学表达式，避免误触发
    return keyword_hit and expr_hit


def _build_calculator_actions(task: str) -> ActionList:
    expr = _extract_math_expr(task)
    if not expr:
        return []
    # Calculator.app 不接受 input_text (Quartz unicode events) 也不接受 pyautogui.press。
    # AppleScript System Events 需要 Automation 权限（子进程拿不到）。
    # 最终方案：type_keys 用真实的 macOS key code (CGEvent) 发送按键，
    # 并且传入 app_name="Calculator" 让底层强制抢回 Calculator 的焦点！
    return [
        {"open_app": {"app_name": "Calculator"}},
        {"wait": {}},
        {"type_keys": {"text": expr, "app_name": "Calculator"}},
        {"Hotkey": {"key": "enter"}},
        {"record_info": {
            "text": f"Calculator opened and computed: {expr}",
            "file_name": "calculator_result.txt",
        }},
        {"done": {}},
    ]


# ─── Skill 2：仅打开某个 App（如"打开 Notion"）─────────────────────
# 关键词 → spotlight 应用名 映射
_SIMPLE_OPEN_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("微信", "wechat"), "WeChat"),
    (("钉钉", "dingtalk"), "DingTalk"),
    (("notion",), "Notion"),
    (("safari",), "Safari"),
    (("chrome", "谷歌浏览器"), "Google Chrome"),
    (("终端", "terminal"), "Terminal"),
    (("访达", "finder"), "Finder"),
    (("便签", "notes", "备忘录"), "Notes"),
)


def _is_pure_open_request(task: str) -> Optional[str]:
    """
    检查任务是否纯粹是"打开 X"，不带后续动作。
    返回应用名，或 None。

    判定规则：
      - 包含"打开"或"open"
      - 命中应用名关键词
      - 任务长度 ≤ 20 字符（防止"打开 Excel 然后输入...."这种被误判）
      - 不含"发"/"输入"/"写"/"send"/"type"/"write" 等动词
    """
    t = task.lower().strip()
    if len(t) > 20:
        return None
    if "打开" not in t and "open " not in t and "启动" not in t:
        return None
    # 排除复杂动作
    if any(verb in t for verb in ("发", "输入", "写", "send", "type", "write", "搜")):
        return None
    for keywords, app_name in _SIMPLE_OPEN_MAP:
        if any(k in t for k in keywords):
            return app_name
    return None


def _matcher_simple_open(task: str) -> bool:
    return _is_pure_open_request(task) is not None


def _build_simple_open_actions(task: str) -> ActionList:
    app_name = _is_pure_open_request(task)
    if not app_name:
        return []
    # 纯启动场景不需要键盘交互，1 个 wait 让用户看到 app 出现就够了
    return [
        {"open_app": {"app_name": app_name}},
        {"wait": {}},
        {"wait": {}},
        {"record_info": {
            "text": f"Successfully opened {app_name}",
            "file_name": f"open_{app_name.lower().replace(' ', '_')}.txt",
        }},
        {"done": {}},
    ]


# ─── Skill 注册表 ─────────────────────────────────────────────────
QUICK_SKILLS: tuple[QuickSkill, ...] = (
    QuickSkill(
        name="open_calculator",
        matcher=_matcher_calculator,
        builder=_build_calculator_actions,
    ),
    QuickSkill(
        name="simple_open_app",
        matcher=_matcher_simple_open,
        builder=_build_simple_open_actions,
    ),
)


def find_quick_skill(task: str) -> Optional[tuple[QuickSkill, ActionList]]:
    """
    查找任务对应的 fast-path skill 并构造好动作清单。

    Returns:
        (skill, actions) — 命中且 actions 非空时
        None             — 都不命中 / 命中但 builder 放弃
    """
    if not task or not task.strip():
        return None
    for skill in QUICK_SKILLS:
        try:
            if not skill.matcher(task):
                continue
            actions = skill.builder(task)
            if actions:
                return skill, actions
        except Exception:
            # 一条 skill 出错不该挡住其它 skill 或主循环
            continue
    return None
