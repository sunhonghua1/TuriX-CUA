import pandas as pd
import pathlib
import sys
import os
import json
import re
import subprocess
from openai import OpenAI

def _expand_path(p):
    return str(pathlib.Path(p).expanduser().resolve())

def clean_amount(val):
    if pd.isna(val): return 0.0
    s = str(val).replace(',', '')
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
    return float(nums[0]) if nums else 0.0

def run_ppt_analysis(excel_path, output_path):
    try:
        # 1. 自动找文件
        excel_p = pathlib.Path(excel_path).expanduser()
        if not excel_p.exists():
            desktop = pathlib.Path.home() / "Desktop"
            possible = list(desktop.glob("*发票汇总*.xlsx"))
            if possible:
                excel_p = possible[0]
            else:
                raise FileNotFoundError("桌面上没找到发票汇总文件")
        
        # 2. 读取并提取关键数据
        df = pd.read_excel(excel_p)
        amounts = df['价税合计'].apply(clean_amount) if '价税合计' in df.columns else pd.Series([0.0]*len(df))
        total = amounts.sum()
        count = len(df)
        max_spend = amounts.max()
        top_vendor = df['销售方'].value_counts().idxmax() if '销售方' in df.columns else "未知"

        # 3. 让 26B 策划 PPT 内容
        _base_url = os.environ.get("FOX_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        _model = os.environ.get("FOX_LOCAL_LLM_MODEL", "gemma-4-26b")
        client = OpenAI(base_url=_base_url, api_key="not-needed")

        prompt = f"""
你是一名资深商业演示专家。请为一份财务报销分析 PPT 策划内容。
数据：
- 总金额：{total:.2f} 元
- 发票数：{count} 张
- 单笔最高：{max_spend:.2f} 元
- 最大供应商：{top_vendor}

请输出一个严格的 JSON 对象，包含 title, subtitle 和 3 个 sections (每个 section 含 heading 和 body)。
body 必须是精简的 bullet points 形式，适合在 PPT 上展示。
JSON 格式示例：
{{
  "title": "...",
  "subtitle": "...",
  "sections": [
    {{"heading": "...", "body": "1. ...\n2. ..."}},
    ...
  ]
}}
不要输出任何其他文字，只输出 JSON。
"""
        response = client.chat.completions.create(
            model=_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        # 提取 JSON
        content = response.choices[0].message.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            raise ValueError(f"模型返回内容无法解析为 JSON: {content}")
        
        ppt_data = json.loads(json_match.group(0))

        # 4. 调用现有的 ppt_writer.py 生成文件
        # 寻找 ppt_writer.py 的绝对路径
        current_dir = pathlib.Path(__file__).parent
        writer_path = current_dir / "ppt_writer.py"
        
        # 运行子进程生成 PPT
        cmd = [sys.executable, str(writer_path), output_path, json.dumps(ppt_data)]
        subprocess.run(cmd, check=True)
        
        print(f"✅ PPT 实战报告已生成：{output_path}")
        return True
    except Exception as e:
        print(f"❌ PPT 生成失败: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    # 接收来自 server.py 的参数
    # 第 1 个参数: excel_path
    # 第 2 个参数: output_path
    in_excel = _expand_path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].strip() else _expand_path("~/Desktop/05月发票汇总.xlsx")
    out_ppt = _expand_path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].strip() else _expand_path("~/Desktop/财务演示文稿.pptx")
    
    print(f"[ppt_analyzer] 🚀 开始处理任务...")
    print(f"  输入 Excel: {in_excel}")
    print(f"  输出 PPT: {out_ppt}")
    
    run_ppt_analysis(in_excel, out_ppt)
