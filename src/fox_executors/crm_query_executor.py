#!/usr/bin/env python3
"""
CRM 数据查询原子执行器 — 从 CordysCRM 查询客户/线索/商机/合同数据。

用法:
    python crm_query_executor.py <query_type> [extra_args_json]

query_type:
    dashboard    → 首页统计概览（本月线索/客户/商机/合同数）
    customers    → 客户列表（最近 N 条）
    leads        → 线索列表（最近 N 条）
    opportunities → 商机列表
    summary      → 自然语言摘要（给语音播报用）

环境变量:
    CRM_BASE_URL    默认 http://localhost:8081
    CRM_API_TOKEN   认证 Token（空则使用 Mock 数据）
    CRM_MOCK_MODE   设为 "1" 强制使用 Mock 数据（开发/演示用）
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
import voice  # 🦊 导入语音引擎
from pathlib import Path
from datetime import datetime

# ─── 配置 ──────────────────────────────────────────────────────────
CRM_BASE_URL = os.environ.get("CRM_BASE_URL", "http://localhost:8081")
CRM_API_TOKEN = os.environ.get("CRM_API_TOKEN", "")
CRM_MOCK_MODE = os.environ.get("CRM_MOCK_MODE", "1") == "1"  # 默认 Mock

# ─── Mock 数据（演示/开发用）──────────────────────────────────────
_MOCK_DASHBOARD = {
    "本月新增线索": 47,
    "本月新增客户": 12,
    "活跃商机": 8,
    "本月签约合同": 3,
    "合同总金额": "¥ 285,000",
    "待跟进客户": 5,
    "数据更新时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
}

_MOCK_CUSTOMERS = [
    {"客户名称": "深圳智联科技有限公司", "联系人": "王总",   "手机": "138****8001", "状态": "活跃",   "最近跟进": "2026-04-28"},
    {"客户名称": "杭州云帆网络科技",     "联系人": "李经理", "手机": "139****5502", "状态": "活跃",   "最近跟进": "2026-04-25"},
    {"客户名称": "北京卓越数据分析",     "联系人": "张总监", "手机": "186****3303", "状态": "待跟进", "最近跟进": "2026-04-20"},
    {"客户名称": "上海锦程贸易有限公司", "联系人": "陈总",   "手机": "135****7704", "状态": "活跃",   "最近跟进": "2026-04-30"},
    {"客户名称": "广州汇达投资咨询",     "联系人": "刘总",   "手机": "158****9905", "状态": "沉默",   "最近跟进": "2026-03-15"},
]

_MOCK_LEADS = [
    {"线索来源": "官网表单",   "公司": "成都新锐科技",   "联系人": "赵小姐", "创建日期": "2026-04-29", "状态": "待分配"},
    {"线索来源": "展会获客",   "公司": "武汉光谷数据",   "联系人": "孙先生", "创建日期": "2026-04-28", "状态": "已分配"},
    {"线索来源": "微信推荐",   "公司": "南京创智软件",   "联系人": "周总",   "创建日期": "2026-04-27", "状态": "跟进中"},
    {"线索来源": "百度推广",   "公司": "厦门海峡云科技", "联系人": "吴经理", "创建日期": "2026-04-26", "状态": "待分配"},
]

_MOCK_OPPORTUNITIES = [
    {"商机名称": "智联科技 ERP 升级项目", "金额": "¥ 120,000", "阶段": "方案报价", "预计成交": "2026-05-15", "负责人": "孙弘华"},
    {"商机名称": "云帆网络年度运维合同",   "金额": "¥ 85,000",  "阶段": "商务谈判", "预计成交": "2026-05-20", "负责人": "孙弘华"},
    {"商机名称": "卓越数据 BI 系统采购",   "金额": "¥ 200,000", "阶段": "需求确认", "预计成交": "2026-06-01", "负责人": "孙弘华"},
]


# ─── HTTP 请求（真实 API 模式）──────────────────────────────────
def _crm_api_get(endpoint: str) -> dict:
    """调用 CordysCRM REST API（需要 curl，避免引入 requests 依赖）。"""
    url = f"{CRM_BASE_URL}{endpoint}"
    headers = []
    if CRM_API_TOKEN:
        headers = ["-H", f"Authorization: Bearer {CRM_API_TOKEN}"]

    result = subprocess.run(
        ["curl", "-sf", *headers, url],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise ConnectionError(f"CRM API 请求失败: {url} (rc={result.returncode})")
    return json.loads(result.stdout)


# ─── 查询调度器 ─────────────────────────────────────────────────
def query_dashboard() -> dict:
    """首页统计概览。"""
    if CRM_MOCK_MODE:
        return _MOCK_DASHBOARD
    return _crm_api_get("/home/statistic")


def query_customers(limit: int = 5) -> list[dict]:
    """客户列表。"""
    if CRM_MOCK_MODE:
        return _MOCK_CUSTOMERS[:limit]
    data = _crm_api_get(f"/customer/page?pageSize={limit}&pageNum=1")
    return data.get("records", data.get("rows", []))


def query_leads(limit: int = 5) -> list[dict]:
    """线索列表。"""
    if CRM_MOCK_MODE:
        return _MOCK_LEADS[:limit]
    data = _crm_api_get(f"/clue/page?pageSize={limit}&pageNum=1")
    return data.get("records", data.get("rows", []))


def query_opportunities() -> list[dict]:
    """商机列表。"""
    if CRM_MOCK_MODE:
        return _MOCK_OPPORTUNITIES
    data = _crm_api_get("/opportunity/page?pageSize=10&pageNum=1")
    return data.get("records", data.get("rows", []))


def generate_summary() -> str:
    """生成自然语言摘要（供语音播报 + 剪贴板）。"""
    d = query_dashboard()
    lines = [
        f"📊 CRM 数据快报（{d.get('数据更新时间', '今日')}）",
        f"• 本月新增线索 {d.get('本月新增线索', 0)} 条",
        f"• 本月新增客户 {d.get('本月新增客户', 0)} 家",
        f"• 活跃商机 {d.get('活跃商机', 0)} 个",
        f"• 本月签约合同 {d.get('本月签约合同', 0)} 份，总金额 {d.get('合同总金额', '未知')}",
        f"• 待跟进客户 {d.get('待跟进客户', 0)} 家",
    ]
    return "\n".join(lines)


# ─── 剪贴板 + 通知 ───────────────────────────────────────────────
def _copy_to_clipboard(text: str) -> None:
    """复制到 macOS 剪贴板。"""
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    except Exception:
        pass


def _notify(title: str, message: str) -> None:
    """macOS 原生通知。"""
    script = f'display notification "{message}" with title "{title}"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


# ─── 主入口 ─────────────────────────────────────────────────────
def run(query_type: str, extra: str = "{}") -> int:
    try:
        extra_args = json.loads(extra) if extra else {}
    except json.JSONDecodeError:
        extra_args = {}

    try:
        if query_type == "dashboard":
            result = query_dashboard()
            output = json.dumps(result, ensure_ascii=False, indent=2)
            _copy_to_clipboard(output)
            _notify("小狐狸 · CRM", "仪表盘数据已复制到剪贴板")
            print(f"[crm_query] ✅ 仪表盘数据已获取")
            print(output)
            # 🔊 语音播报
            voice.speak(f"报告孙先生，本月新增线索{result.get('本月新增线索', 0)}条，已签约合同{result.get('本月签约合同', 0)}份。数据已同步。")
            return 0

        elif query_type == "customers":
            limit = extra_args.get("limit", 5)
            result = query_customers(limit)
            output = json.dumps(result, ensure_ascii=False, indent=2)
            _copy_to_clipboard(output)
            _notify("小狐狸 · CRM", f"已查询 {len(result)} 条客户记录")
            print(f"[crm_query] ✅ 查询到 {len(result)} 条客户记录")
            print(output)
            # 🔊 语音播报
            voice.speak(f"为您查到{len(result)}家客户，详细名单已复制到剪贴板。")
            return 0

        elif query_type == "leads":
            limit = extra_args.get("limit", 5)
            result = query_leads(limit)
            output = json.dumps(result, ensure_ascii=False, indent=2)
            _copy_to_clipboard(output)
            _notify("小狐狸 · CRM", f"已查询 {len(result)} 条线索")
            print(f"[crm_query] ✅ 查询到 {len(result)} 条线索")
            print(output)
            # 🔊 语音播报
            voice.speak(f"系统新增了{len(result)}条线索，请及时跟进。")
            return 0

        elif query_type == "opportunities":
            result = query_opportunities()
            output = json.dumps(result, ensure_ascii=False, indent=2)
            _copy_to_clipboard(output)
            _notify("小狐狸 · CRM", f"已查询 {len(result)} 个商机")
            print(f"[crm_query] ✅ 查询到 {len(result)} 个商机")
            print(output)
            return 0

        elif query_type == "summary":
            summary = generate_summary()
            _copy_to_clipboard(summary)
            _notify("小狐狸 · CRM", "数据快报已生成")
            print(f"[crm_query] ✅ CRM 数据快报已生成")
            print(summary)
            # 🔊 语音播报 (精简版摘要)
            voice.speak(f"孙先生，为您生成今日CRM快报。本月活跃商机{query_dashboard().get('活跃商机', 0)}个，业绩稳步增长中。")
            return 0

        else:
            print(f"[crm_query] ❌ 未知查询类型: {query_type}", file=sys.stderr)
            return 1

    except ConnectionError as e:
        print(f"[crm_query] ❌ CRM 连接失败: {e}", file=sys.stderr)
        print("[crm_query] 💡 请确认 CordysCRM Docker 容器已启动 (端口 8081)", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[crm_query] ❌ 查询失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python crm_query_executor.py <dashboard|customers|leads|opportunities|summary> [extra_json]", file=sys.stderr)
        sys.exit(1)

    q_type = sys.argv[1]
    q_extra = sys.argv[2] if len(sys.argv) > 2 else "{}"
    sys.exit(run(q_type, q_extra))
