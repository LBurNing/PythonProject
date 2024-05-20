import os
import sys

# 检查命令行参数是否足够
if len(sys.argv) < 2:
    print("Usage: python script.py link.txt")
    sys.exit(1)

# 读取 link.txt 文件路径
link_file = sys.argv[1]

# 检查 link.txt 文件是否存在
if not os.path.exists(link_file):
    print(f"Link file '{link_file}' does not exist")
    sys.exit(1)

# 获取当前运行环境的路径
current_directory = os.path.dirname(os.path.realpath(sys.argv[0]))
current_directory = os.path.dirname(current_directory)

# 读取 link.txt 文件
with open(link_file, "r") as file:
    for line in file:
        # 按行分割数据
        src, dst = line.strip().split("<To>")
        src = os.path.join(current_directory, src.strip())  # 拼接源文件夹路径
        dst = os.path.join(current_directory, dst.strip())  # 拼接目标路径

        # 检查源文件夹是否存在
        if not os.path.exists(src):
            print(f"Source folder '{src}' does not exist")
            continue

        # 删除已存在的软链接（如果存在）
        if os.path.islink(dst):
            os.unlink(dst)

        # 创建软链接
        try:
            os.symlink(src, dst)
            print(f"Symbolic link created at '{dst}' pointing to '{src}'")
        except OSError as e:
            print(f"Error creating symbolic link: {e}")

# 等待用户关闭窗口
input("Press Enter to exit...")
