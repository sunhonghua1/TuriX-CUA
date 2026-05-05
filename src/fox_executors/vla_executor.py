import subprocess
import os
import logging
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VLAExecutor")

def execute_vla_task(task_type, prompt):
    """
    使用 Mano-P (VLA) 引擎执行视觉任务
    task_type: 'ask' (询问屏幕内容) 或 'do' (执行点击/操作)
    """
    logger.info(f"🚀 启动 VLA 视觉引擎 | 任务类型: {task_type} | 提示词: {prompt}")
    
    # 确保使用 Homebrew 安装的路径
    mano_path = "mano-cua"
    
    try:
        # 构建指令 (使用 run 命令和 --local 标志确保本地推理)
        cmd = [mano_path, "run", prompt, "--local"]
        
        # 记录开始时间
        start_time = time.time()
        
        # 运行指令
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60 # 视觉模型推理较慢，给 60 秒超时
        )
        
        elapsed = time.time() - start_time
        
        if process.returncode == 0:
            logger.info(f"✅ VLA 任务完成 (耗时: {elapsed:.2f}s)")
            return {
                "status": "success",
                "content": process.stdout.strip(),
                "latency": f"{elapsed:.2f}s",
                "engine": "Mano-P (Local VLA)"
            }
        else:
            logger.error(f"❌ VLA 引擎报错: {process.stderr}")
            return {
                "status": "error",
                "message": process.stderr.strip() or "未知错误",
                "engine": "Mano-P"
            }
            
    except subprocess.TimeoutExpired:
        logger.error("⏰ VLA 任务超时")
        return {"status": "error", "message": "视觉推理超时，请检查模型是否卡住", "engine": "Mano-P"}
    except Exception as e:
        logger.error(f"💥 VLA 执行器异常: {str(e)}")
        return {"status": "error", "message": str(e), "engine": "Mano-P"}

if __name__ == "__main__":
    # 简单的本地测试
    print(execute_vla_task("ask", "屏幕上显示的是什么软件？"))
