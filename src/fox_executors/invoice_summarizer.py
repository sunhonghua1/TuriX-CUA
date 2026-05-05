#!/usr/bin/env python3
"""
发票汇总执行器（调用本地 LLM 提取发票数据，并生成 Excel 表格）。

用法:
    python invoice_summarizer.py <source_dir> <output_path>
示例:
    python invoice_summarizer.py ~/Desktop/05月投递箱 ~/Desktop/05月报销汇总.xlsx
"""

import sys
import fitz
import pathlib
import json
import re
import pandas as pd
from openai import OpenAI

def _expand_path(p: str) -> str:
    """展开 ~ 和环境变量。"""
    return str(pathlib.Path(p).expanduser().resolve())

def extract_invoice_data(pdf_path: pathlib.Path) -> dict:
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
            
        # 优先使用环境变量，默认回退到 Rapid-MLX 端口 8000
        import os
        _base_url = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        _api_key  = os.environ.get("FOX_LOCAL_LLM_API_KEY",  "not-needed")
        client = OpenAI(base_url=_base_url, api_key=_api_key)
        
        prompt = f'''
请从以下中国增值税发票文本中提取信息，并严格输出 JSON 格式（不要包含任何其他文字或 markdown）。
注意：
1. 发票号码通常是8位纯数字。
2. 购买方是发票抬头（买东西的公司）。
3. 销售方是卖东西的公司。
4. 价税合计是发票总金额（通常是带有¥符号的数字，或者在价税合计一栏）。

输出格式：
{{
  "发票号码": "...",
  "开票日期": "...",
  "购买方": "...",
  "销售方": "...",
  "价税合计": "..."
}}

发票文本：
{text[:2000]}
'''
        # 动态获取模型列表以支持 LM Studio 的多模型模式
        import os
        models = client.models.list()
        
        # 自动识别模型：优先用环境变量，如果没有就抓取服务器当前加载的第一个模型
        env_model = os.environ.get("FOX_LOCAL_LLM_MODEL")
        available_model_ids = [m.id for m in models.data]
        
        if env_model in available_model_ids:
            use_model = env_model
        elif available_model_ids:
            use_model = available_model_ids[0]
            print(f"[invoice_summarizer] ⚠️ 找不到指定模型 {env_model}，自动切换到: {use_model}", file=sys.stderr)
        else:
            use_model = 'default'
            
        response = client.chat.completions.create(
            model=use_model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r'^```json\n|\n```$', '', content, flags=re.MULTILINE).strip()
        if content.startswith('```'):
             content = content[3:].strip()
        
        data = json.loads(content)
        data['文件名'] = pdf_path.name
        return data
    except Exception as e:
        print(f"[invoice_summarizer] ⚠️ 解析 {pdf_path.name} 失败: {e}", file=sys.stderr)
        return {"文件名": pdf_path.name, "错误": str(e)}

def main():
    if len(sys.argv) < 3:
        print("Usage: python invoice_summarizer.py <source_dir> <output_path>", file=sys.stderr)
        sys.exit(1)

    source_dir = pathlib.Path(_expand_path(sys.argv[1]))
    output_path = pathlib.Path(_expand_path(sys.argv[2]))

    if not source_dir.is_dir():
        print(f"[invoice_summarizer] ❌ 源目录不存在或不是目录: {source_dir}", file=sys.stderr)
        sys.exit(1)

    pdf_files = list(source_dir.glob('*.pdf'))
    if not pdf_files:
        print(f"[invoice_summarizer] ⚠️ 在 {source_dir} 未找到 PDF 文件", file=sys.stderr)
        # Even if empty, create an empty excel to show it worked but found nothing
        df = pd.DataFrame(columns=['文件名', '发票号码', '开票日期', '购买方', '销售方', '价税合计'])
        df.to_excel(output_path, index=False)
        print(f"[invoice_summarizer] ✅ 已生成空汇总表: {output_path}")
        sys.exit(0)

    print(f"[invoice_summarizer] 🔍 找到 {len(pdf_files)} 个 PDF 发票，正在调用本地大模型提取数据...")
    results = []
    for pdf_file in pdf_files:
        print(f"   处理中: {pdf_file.name}")
        data = extract_invoice_data(pdf_file)
        results.append(data)
    
    df = pd.DataFrame(results)
    
    cols = ['文件名'] + [c for c in df.columns if c != '文件名']
    df = df[cols]
    
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(output_path, index=False)
        print(f"[invoice_summarizer] ✅ 汇总完成！已保存至: {output_path}")
    except Exception as e:
        print(f"[invoice_summarizer] ❌ 保存 Excel 失败: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
