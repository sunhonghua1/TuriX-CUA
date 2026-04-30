#!/usr/bin/env python3
"""
macOS 原生语音播报工具。
调用系统 say 命令，无需任何第三方依赖。
"""
import subprocess
import shutil
import logging

logger = logging.getLogger(__name__)

# 优先使用的中文语音引擎（按优先级排列）
_PREFERRED_VOICES = ["Tingting", "Meijia", "Sinji"]


def _detect_voice() -> str:
    """检测系统中可用的中文语音引擎，返回第一个可用的。"""
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True, text=True, timeout=5
        )
        available = result.stdout
        for voice in _PREFERRED_VOICES:
            if voice in available:
                return voice
    except Exception as e:
        logger.debug(f"检测语音引擎失败: {e}")
    return ""  # 空字符串 = 使用系统默认


def speak(text: str, voice: str = "") -> None:
    """
    使用 macOS say 命令播报文本。
    
    Args:
        text: 要播报的文本内容
        voice: 指定语音引擎名称，空字符串则自动检测
    """
    if not shutil.which("say"):
        logger.warning("say 命令不可用（非 macOS？），跳过语音播报")
        return

    if not voice:
        voice = _detect_voice()

    cmd = ["say"]
    if voice:
        cmd.extend(["-v", voice])
    # 语速稍微加快一点（默认 200，设为 220 更自然）
    cmd.extend(["-r", "220"])
    cmd.append(text)

    try:
        # 非阻塞执行，不等待语音播完
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"🔊 语音播报: {text[:30]}...")
    except Exception as e:
        logger.warning(f"语音播报失败: {e}")
