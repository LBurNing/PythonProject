import subprocess
import glob
import os
import sys
import shutil
from pathlib import Path

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    input_dir = 'D:\\FGCQ\\code\\client\\lua'
    output_dir = 'D:\\FGCQ\\tools\\luajit2.1\\lua'
    luajit_directory = r'D:\\FGCQ\\tools\\luajit2.1'
else:
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    luajit_directory = sys.argv[3]

# 切换工作目录
os.chdir(luajit_directory)
command = ["luajit", "-b"]

# 判断输出目录是否存在，不存在则创建
Path(output_dir).mkdir(parents=True, exist_ok=True)

file_list = []

for file in glob.glob(str(input_dir + '\\**\\*.lua'), recursive=True):
    file_list.append(file)

for file in file_list:
    file_path = Path(file)
    relative_path = file_path.relative_to(input_dir)
    output_file = Path(output_dir) / relative_path.with_suffix('.lua')

    output_folder = output_file.parent
    output_folder.mkdir(parents=True, exist_ok=True)

    # 执行命令行
    subprocess.run(command + [str(file_path), str(output_file)])

list_file_list = []
for file in glob.glob(str(input_dir + '\\**\\*.list'), recursive=True):
    list_file_list.append(file)

for file in list_file_list:
    target_path = file.replace(input_dir, output_dir)
    destination_folder = os.path.dirname(target_path)
    os.makedirs(destination_folder, exist_ok=True)

    # 复制文件
    shutil.copy(file, target_path)
