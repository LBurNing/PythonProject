import os
import subprocess

# 配置路径
astcenc_exe = "Actc2Png/astcenc-avx2.exe"  # 确保在同目录或加完整路径
input_folder = r"C:\Users\lihehui\Desktop\205548-529-24815716(1)\assets\builtin\anims"
output_folder = os.path.join(input_folder, "decoded_pngs")

# 自动创建输出目录
os.makedirs(output_folder, exist_ok=True)

# 0,0 -21,0 -48,-3 -32,-3 
# 遍历所有 .astc 文件
for filename in os.listdir(input_folder):
    if filename.lower().endswith(".astc"):
        input_path = os.path.join(input_folder, filename)
        output_name = os.path.splitext(filename)[0] + ".png"
        output_path = os.path.join(output_folder, output_name)

        # 构建命令
        cmd = [astcenc_exe, "-dl", input_path, output_path]

        print("解压中:", input_path)
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print("成功:", output_name)
        except subprocess.CalledProcessError as e:
            print("失败:", filename)
            print(e.stderr)