import os
import time
from datasets import load_dataset

# --- 配置 ---
YOUR_TARGET_DIR = "/root/autodl-tmp/Agent_audit_system/safety_data"
# --- 创建目录 ---
os.makedirs(YOUR_TARGET_DIR, exist_ok=True)

print(f"数据集将被下载和缓存到: {YOUR_TARGET_DIR}")
print("开始下载 gretelai/gretel-safety-alignment-en-v1 ...")
print("提示：根据网络情况，首次下载可能需要 5~20 分钟，请耐心等待。")

# 记录开始时间
start_time = time.time()

# load_dataset 会自动使用 tqdm 显示进度条（如果已安装 tqdm）
dataset = load_dataset(
    "gretelai/gretel-safety-alignment-en-v1",
    cache_dir=YOUR_TARGET_DIR,
    # 可选：如果想看到更详细的下载日志，可以设置
    # download_config=download_config,
)

end_time = time.time()
print(f"下载和缓存完成，共用时 {end_time - start_time:.2f} 秒")

print("数据加载完成，现在保存到持久化目录...")
save_path = os.path.join(YOUR_TARGET_DIR, "gretel_safety_dataset_hf")
dataset.save_to_disk(save_path)
print(f"数据集已成功保存到: {save_path}")