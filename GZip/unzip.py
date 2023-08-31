import os
import gzip
import shutil

source_folder = "E:\PKM2PNG-main\png2pkm\\res"
output_folder = "E:\PKM2PNG-main\png2pkm\png2pkm-master\\pkm"

def rename_png_to_zip(source_path):
    for file_name in os.listdir(source_path):
        if file_name.endswith(".png"):
            png_file_path = os.path.join(source_path, file_name)
            new_name = os.path.splitext(png_file_path)[0] + ".zip"
            os.rename(png_file_path, new_name)
            print(f"Renamed {file_name} to {new_name}")

def unzip_all_zips(source_path, output_path):
    if not os.path.exists(output_path):
        os.makedirs(output_path)  # 如果输出文件夹不存在，创建它

    for file_name in os.listdir(source_path):
        if file_name.endswith(".png"):
            zip_file_path = os.path.join(source_path, file_name)
            output_file_name = os.path.splitext(file_name)[0] + ".pkm"  # 用 .png 后缀命名解压后的文件
            output_file_path = os.path.join(output_path, output_file_name)

            with gzip.open(zip_file_path, 'rb') as f_in:
                with open(output_file_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            print(f"Extracted {file_name} to {output_file_name} successfully.")

# rename_png_to_zip(source_folder)
unzip_all_zips(source_folder, output_folder)
