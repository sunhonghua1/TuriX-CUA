import fitz
import pathlib
import json
import re
import pandas as pd
from openai import OpenAI
import time

def extract_invoice_data(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    
    import os
    _base_url = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
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
    try:
        # Dynamically fetch the available models to support LM Studio multi-model mode
        models = client.models.list()
        use_model = models.data[0].id if models.data else 'local-model'
        
        response = client.chat.completions.create(
            model=use_model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        content = re.sub(r'^```json\n|\n```$', '', content, flags=re.MULTILINE).strip()
        if content.startswith('```'):
             content = content[3:].strip()
        
        data = json.loads(content)
        data['文件名'] = pdf_path.name
        return data
    except Exception as e:
        print(f"Error processing {pdf_path.name}: {e}")
        return {"文件名": pdf_path.name, "错误": str(e)}

def main():
    folder_path = pathlib.Path('/Users/sunhonghua1970outlook.com/Desktop/05月投递箱/05月报销')
    # If the folder does not exist, let's try the desktop directly or 05月投递箱
    if not folder_path.exists():
        folder_path = pathlib.Path('/Users/sunhonghua1970outlook.com/Desktop/05月投递箱')
    
    pdf_files = list(folder_path.glob('*.pdf'))
    if not pdf_files:
        print("未找到 PDF 文件")
        return

    print(f"找到 {len(pdf_files)} 个 PDF 文件，正在使用本地大模型逐个提取信息（可能需要几分钟）...")
    results = []
    for pdf_file in pdf_files:
        print(f"正在处理: {pdf_file.name}")
        data = extract_invoice_data(pdf_file)
        results.append(data)
    
    df = pd.DataFrame(results)
    
    # Reorder columns to put filename first
    cols = ['文件名'] + [c for c in df.columns if c != '文件名']
    df = df[cols]
    
    out_path = pathlib.Path('/Users/sunhonghua1970outlook.com/Desktop/05月发票汇总.xlsx')
    df.to_excel(out_path, index=False)
    print(f"\n✅ 汇总完成！已保存至: {out_path}")

if __name__ == "__main__":
    main()
