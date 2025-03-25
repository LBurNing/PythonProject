import gzip
import os
import sys

# 检查是否处于调试模式
debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    # 获取当前工作路径
    current_dir = os.getcwd()
    versions_file = os.path.join(r'E:\yuyan\code\client\game\version', 'versions.txt')
    new_version_file = os.path.join(r'E:\yuyan\code\client\game\version', 'newVersion.txt')
    output_version_file = os.path.join(r'E:\yuyan\code\client\game\version', 'android', 'versions.txt')
else:
    try:
        # 获取当前工作路径
        current_dir = os.getcwd()
        # 结合当前工作路径和命令行参数
        versions_file = os.path.join(current_dir, 'versions.txt')
        new_version_file = os.path.join(current_dir, 'newVersion.txt')
        output_version_file = os.path.join(current_dir, 'android', 'versions.txt')
        print("Release模式\ninput_file: ", versions_file, " output_file: ", output_version_file)
    except IndexError:
        print("错误：在Release模式下，需要提供输入文件和输出文件的路径作为命令行参数。")
        sys.exit(1)

def replace_data_in_versions(new_version_file, versions_file, output_file):
    try:
        # 读取 newVersion 文件中的数据
        with open(new_version_file, 'r') as new_file:
            new_data_lines = new_file.readlines()

        # 存储要替换的数据映射
        replacement_map = {}
        for line in new_data_lines:
            parts = line.strip().split('\t')
            if len(parts) >= 2:
                key = parts[0]
                replacement = '\t'.join(parts)
                replacement_map[key] = replacement

        # 读取并处理 versions 文件
        with gzip.open(versions_file, 'rt', compresslevel=9) as versions_f, gzip.open(output_file, 'wt', compresslevel=9) as out_f:
            for line in versions_f:
                parts = line.strip().split('\t')
                if parts and parts[0] in replacement_map:
                    # 如果找到匹配项，进行替换
                    new_line = replacement_map[parts[0]] + '\n'
                    out_f.write(new_line)
                else:
                    # 没有匹配项，保持原内容
                    out_f.write(line)
        print(f"替换完成，结果已保存到 {output_file}")
    except FileNotFoundError:
        print("错误：未找到指定的文件。")
    except Exception as e:
        print(f"发生未知错误: {e}")

replace_data_in_versions(new_version_file, versions_file, output_version_file)
    