#!/usr/bin/env python3
"""
截图 OCR + 翻译原子执行器 (Fox-path Executor)
使用 macOS Vision.framework (VNRecognizeTextRequest) 做 OCR，
再调用本地 LLM 翻译，结果复制到剪贴板。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _screenshot_to_file() -> str:
    """截取当前屏幕到临时文件，返回路径。"""
    tmp = tempfile.mktemp(suffix=".png")
    subprocess.run(["screencapture", "-x", tmp], check=True)
    return tmp


def _ocr_image(image_path: str, lang: str = "zh-Hans") -> str:
    """
    用 macOS Vision.framework 做 OCR。
    同时开启中英文识别。
    """
    swift_code = r"""
import Vision
import AppKit
import Foundation

let imagePath = CommandLine.arguments[1]
let lang = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : "zh-Hans"

guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
// 同时开启中英文识别，提高代码和混合文本的成功率
request.recognitionLanguages = [lang, "en-US"]
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try? handler.perform([request])

guard let observations = request.results else {
    exit(0)
}

let lines = observations.compactMap { $0.topCandidates(1).first?.string }
print(lines.joined(separator: "\n"))
"""
    # 使用唯一的临时文件
    fd, swift_tmp = tempfile.mkstemp(suffix=".swift")
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(swift_code)

        res = subprocess.run(
            ["swift", swift_tmp, image_path, lang],
            capture_output=True, text=True, timeout=30,
        )
        return (res.stdout or "").strip()
    except Exception as e:
        print(f"[ocr_translate] ❌ Swift OCR 失败: {e}", file=sys.stderr)
        return ""
    finally:
        try:
            os.unlink(swift_tmp)
        except Exception:
            pass


def _translate_with_llm(text: str, target_lang: str = "英文") -> str:
    """调用本地 LLM 翻译文本。"""
    try:
        from openai import OpenAI
    except ImportError:
        print("[ocr_translate] ❌ 缺少 openai 库", file=sys.stderr)
        return ""

    base_url = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    api_key = os.environ.get("FOX_LOCAL_LLM_API_KEY", "not-needed")

    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=60.0)
        models = client.models.list()
        model_id = models.data[0].id if models.data else None
        if not model_id:
            print("[ocr_translate] ❌ 无法获取本地模型", file=sys.stderr)
            return ""

        completion = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": f"你是一个翻译助手。将用户提供的文本翻译成{target_lang}，只输出翻译结果，不要解释。"},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[ocr_translate] ❌ LLM 翻译失败: {e}", file=sys.stderr)
        return ""


def run(image_path: str, action: str = "ocr") -> int:
    """
    action: 'ocr' = 仅识别文字
            'translate' = OCR + 翻译成英文
            'translate_zh' = OCR + 翻译成中文
    """
    # 如果没提供图片路径，截取当前屏幕
    if not image_path or image_path == "screen":
        print("[ocr_translate] 📸 截取当前屏幕...")
        image_path = _screenshot_to_file()
        _cleanup_img = True
    else:
        image_path = str(Path(image_path).expanduser().resolve())
        _cleanup_img = False

    if not Path(image_path).exists():
        print(f"[ocr_translate] ❌ 图片不存在: {image_path}", file=sys.stderr)
        return 1

    # Step 1: OCR
    print(f"[ocr_translate] 🔍 识别文字中: {image_path}")
    ocr_text = _ocr_image(image_path)
    if not ocr_text:
        # 重试一次：有时 Vision 引擎启动慢
        import time
        time.sleep(0.5)
        ocr_text = _ocr_image(image_path)
    
    if not ocr_text:
        print("[ocr_translate] ⚠️ 未识别到文字")
        ocr_text = ""

    # Step 2: 翻译（如果需要）
    result_parts = []
    if ocr_text:
        result_parts.append(f"--- OCR 识别结果 ---\n{ocr_text}")

    if action in ("translate", "translate_zh") and ocr_text:
        target_lang = "中文" if action == "translate_zh" else "英文"
        print(f"[ocr_translate] 🌐 翻译成{target_lang}中...")
        translated = _translate_with_llm(ocr_text, target_lang)
        if translated:
            result_parts.append(f"\n--- {target_lang}翻译 ---\n{translated}")

    result = "\n\n".join(result_parts) if result_parts else "未识别到文字内容"

    # 复制到剪贴板
    try:
        pbcopy = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        pbcopy.communicate(result.encode("utf-8"))
        print(f"[ocr_translate] 📋 结果已复制到剪贴板")
    except Exception:
        pass

    print(f"[ocr_translate] 💡 {result}")
    print(f"[ocr_translate] ✅ 完成")

    # 清理临时截图
    if _cleanup_img:
        try:
            Path(image_path).unlink(missing_ok=True)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python ocr_translate_executor.py <图片路径|screen> [ocr|translate|translate_zh]", file=sys.stderr)
        sys.exit(1)

    img = sys.argv[1]
    act = sys.argv[2] if len(sys.argv) > 2 else "ocr"
    sys.exit(run(img, act))
