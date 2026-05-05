#!/usr/bin/env python3
"""
Clawdcursor 桥接执行器 — 连接 clawdcursor REST API，赋予小狐狸"视觉 + 操作"能力。

用法:
    python clawdcursor_executor.py task  "打开计算器并输入 123+456"
    python clawdcursor_executor.py tool  accessibility '{"action":"read_tree"}'
    python clawdcursor_executor.py tool  computer      '{"action":"screenshot"}'
    python clawdcursor_executor.py health

环境变量:
    CLAWDCURSOR_API     默认 http://127.0.0.1:3847
    CLAWDCURSOR_TOKEN   覆盖 ~/.clawdcursor/token

clawdcursor 提供 6 个复合工具 (compact mode):
    computer       鼠标 / 键盘 / 截图 / 等待
    accessibility  读 UI 树 / 按名称点击 / 设值
    window         打开 / 聚焦 / 最大化 / 关闭应用
    system         剪贴板 / OCR / 时间 / 快捷键
    browser        CDP — DOM 级别控制浏览器
    task           整条自然语言指令交给 clawdcursor 自主执行
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ─── 配置 ──────────────────────────────────────────────────────
CLAWDCURSOR_API = os.environ.get("CLAWDCURSOR_API", "http://127.0.0.1:3847")
TOKEN_FILE = Path.home() / ".clawdcursor" / "token"


def _get_token() -> str:
    """读取 clawdcursor 认证 token。"""
    env_token = os.environ.get("CLAWDCURSOR_TOKEN", "").strip()
    if env_token:
        return env_token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return ""


def _get_turix_config() -> dict:
    """读取 TuriX config.json 获取大模型配置。"""
    config_path = Path("/Users/github/TuriX-CUA/examples/config.json")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _ensure_server_running() -> bool:
    """检测 clawdcursor 是否在运行。如果尝试使用 /execute/task 会报错 400，说明启动的是 serve 模式，需要用 start 模式自动拉起。"""
    try:
        # Check if the server is healthy
        r_health = subprocess.run(
            ["curl", "-sf", f"{CLAWDCURSOR_API}/health"],
            capture_output=True, text=True, timeout=2,
        )
        if r_health.returncode == 0:
            # check if /execute/task works (empty task to avoid acting, just check if 400)
            token = _get_token()
            cmd = ["curl", "-s", "-X", "POST", f"{CLAWDCURSOR_API}/execute/task", "-d", '{"instruction":""}']
            if token:
                cmd += ["-H", f"Authorization: Bearer {token}"]
            cmd += ["-H", "Content-Type: application/json"]
            r_task = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if "not found" not in r_task.stdout and "Cannot POST" not in r_task.stdout:
                return True
            print("[clawdcursor] ⚠️ 当前运行的是 serve 模式，没有 task 能力，准备重启...", file=sys.stderr)
            subprocess.run(["clawdcursor", "stop"], capture_output=True)
            time.sleep(1)
    except Exception:
        pass

    # 尝试自动启动
    print("[clawdcursor] ⚠️ 服务未运行或模式不匹配，正在以 start 模式自动启动...", file=sys.stderr)
    
    # 获取 LLM 配置
    turix_cfg = _get_turix_config()
    brain_cfg = turix_cfg.get("brain_llm", {})
    provider = brain_cfg.get("provider", "openai")
    model = brain_cfg.get("model_name", "anthropic/claude-sonnet-4.6")
    base_url = brain_cfg.get("base_url", "https://api.openai.com/v1")
    api_key = brain_cfg.get("api_key", "")
    
    # 映射 provider
    # 如果模型名包含 anthropic，则优先使用 anthropic 协议以获得更好的工具调用支持
    if "anthropic" in model.lower():
        provider = "anthropic"
        openai_compat = False
    elif provider == "turix" or provider == "deepseek":
        provider = "openai"
        openai_compat = True
    else:
        openai_compat = (provider == "openai")
        
    # 确保 base_url 没有末尾斜杠，避免出现 //chat/completions 导致 500 错误
    base_url = base_url.rstrip("/")
        
    # 主动写入 .clawdcursor-config.json 到当前工作目录
    config_file = os.path.join(os.getcwd(), ".clawdcursor-config.json")
    pipeline_cfg = {
        "provider": provider,
        "apiKey": api_key,
        "pipeline": {
            "layer1": True,
            "layer2": {
                "enabled": True,
                "model": model,
                "baseUrl": base_url
            },
            "layer3": {
                "enabled": True,
                "model": model,
                "baseUrl": base_url,
                "computerUse": False
            }
        }
    }
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(pipeline_cfg, f, indent=2)
    except Exception as e:
        print(f"[clawdcursor] ⚠️ 无法写入配置文件: {e}", file=sys.stderr)

    # 准备环境变量
    env = os.environ.copy()
    if provider == "anthropic":
        env["ANTHROPIC_API_KEY"] = api_key
        env["ANTHROPIC_BASE_URL"] = base_url
    else:
        env["OPENAI_API_KEY"] = api_key
        env["OPENAI_BASE_URL"] = base_url
    
    # 也可以设置通用的 AI_API_KEY
    env["AI_API_KEY"] = api_key

    start_cmd = ["clawdcursor", "start", "--accept"]
    if provider:
        start_cmd.extend(["--provider", provider])
    
    print(f"[clawdcursor] 🛠️ 启动命令: {' '.join(start_cmd)}")

    try:
        with open(os.path.expanduser("~/.clawdcursor/executor_start.log"), "w") as f_log:
            subprocess.Popen(
                start_cmd,
                stdout=f_log,
                stderr=subprocess.STDOUT,
                env=env,
            )
        # 等待启动
        for _ in range(10):
            time.sleep(1)
            try:
                r = subprocess.run(
                    ["curl", "-sf", f"{CLAWDCURSOR_API}/health"],
                    capture_output=True, text=True, timeout=2,
                )
                if r.returncode == 0:
                    print("[clawdcursor] ✅ 服务已自动启动 (start 模式)", file=sys.stderr)
                    return True
            except Exception:
                pass
        print("[clawdcursor] ❌ 自动启动超时", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("[clawdcursor] ❌ clawdcursor 命令不存在，请先安装", file=sys.stderr)
        return False


def _api_call(method: str, endpoint: str, body: dict | None = None) -> dict:
    """调用 clawdcursor REST API。"""
    url = f"{CLAWDCURSOR_API}{endpoint}"
    token = _get_token()

    cmd = ["curl", "-sf", "-X", method]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise ConnectionError(f"API 请求失败: {url} (rc={result.returncode})\n{result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


# ─── 核心功能 ─────────────────────────────────────────────────
def health_check() -> dict:
    """检查 clawdcursor 服务健康状态。"""
    return _api_call("GET", "/health")


def run_task(instruction: str) -> dict:
    """将整条自然语言指令交给 clawdcursor 的 task pipeline 自主执行。"""
    return _api_call("POST", "/execute/task", {"instruction": instruction})


def run_tool(tool_name: str, params: dict) -> dict:
    """精确调用某个复合工具（computer / accessibility / window / system / browser）。"""
    return _api_call("POST", f"/execute/{tool_name}", params)


def read_screen() -> dict:
    """读取当前屏幕的可访问性树（结构化 UI 元素）。"""
    return run_tool("accessibility", {"action": "read_tree"})


def take_screenshot() -> dict:
    """截取当前屏幕截图。"""
    return run_tool("computer", {"action": "screenshot"})


# ─── CLI 入口 ─────────────────────────────────────────────────
def run(mode: str, *args) -> int:
    if not _ensure_server_running():
        print("[clawdcursor] ❌ 无法连接 clawdcursor 服务", file=sys.stderr)
        return 1

    try:
        if mode == "health":
            result = health_check()
            print(f"[clawdcursor] ✅ 服务状态: {json.dumps(result, ensure_ascii=False)}")

            # macOS 通知
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "Clawdcursor v{result.get("version", "?")} 运行中，{result.get("tools", 0)} 个工具就绪" with title "🦊 小狐狸 · 视觉引擎"'],
                capture_output=True, timeout=5,
            )
            return 0

        elif mode == "task":
            instruction = args[0] if args else ""
            if not instruction:
                print("[clawdcursor] ❌ 缺少 instruction 参数", file=sys.stderr)
                return 1

            print(f"[clawdcursor] 🚀 执行桌面任务: {instruction[:60]}...")
            start = time.time()
            result = run_task(instruction)
            elapsed = time.time() - start

            output = json.dumps(result, ensure_ascii=False, indent=2)
            print(f"[clawdcursor] ✅ 任务完成 ({elapsed:.1f}s)")
            print(output)

            # 复制结果到剪贴板
            try:
                subprocess.run(["pbcopy"], input=output.encode("utf-8"), check=True)
                print("[clawdcursor] 📋 结果已复制到剪贴板")
            except Exception:
                pass

            # macOS 通知
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "桌面任务执行完成 ({elapsed:.1f}s)" with title "🦊 小狐狸 · 视觉引擎"'],
                capture_output=True, timeout=5,
            )
            return 0

        elif mode == "tool":
            tool_name = args[0] if args else ""
            params_json = args[1] if len(args) > 1 else "{}"
            if not tool_name:
                print("[clawdcursor] ❌ 缺少 tool_name 参数", file=sys.stderr)
                return 1

            params = json.loads(params_json)
            print(f"[clawdcursor] 🔧 调用工具: {tool_name}({params.get('action', '')})")
            result = run_tool(tool_name, params)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        else:
            print(f"[clawdcursor] ❌ 未知模式: {mode}", file=sys.stderr)
            print("用法: python clawdcursor_executor.py <task|tool|health> [args...]", file=sys.stderr)
            return 1

    except ConnectionError as e:
        print(f"[clawdcursor] ❌ 连接失败: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[clawdcursor] ❌ 执行错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python clawdcursor_executor.py <task|tool|health> [args...]", file=sys.stderr)
        sys.exit(1)

    sys.exit(run(sys.argv[1], *sys.argv[2:]))
