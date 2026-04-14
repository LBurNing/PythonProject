import os
from PIL import Image

# 防止超大图报错
Image.MAX_IMAGE_PIXELS = None

# 输入输出路径
input_folder = r"C:\Users\lihehui\Desktop\Map\桃源之门\Maps\map\tiles\桃园副本"
output_folder = r"C:\Users\lihehui\Desktop\Map\桃源之门\Maps\map\tiles\桃园副本\桃园副本.jpg"

# 确保输出目录存在
os.makedirs(output_folder, exist_ok=True)

for root, dirs, files in os.walk(input_folder):
    for file in files:
        if file.lower().endswith(".png"):
            png_path = os.path.join(root, file)

            # 直接输出到同一个目录
            jpg_name = os.path.splitext(file)[0] + ".jpg"
            jpg_path = os.path.join(output_folder, jpg_name)

            try:
                with Image.open(png_path) as img:
                    img = img.convert("RGB")
                    img.save(jpg_path, "JPEG", quality=95, subsampling=0)

                print(f"✔ {png_path}")

            except Exception as e:
                print(f"✘ 失败: {png_path} -> {e}")

print("批量转换完成！")