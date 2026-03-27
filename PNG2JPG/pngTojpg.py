import os
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

# 设置输入文件夹和输出文件夹
input_folder = r"C:\Users\lihehui\Desktop\mapout\传战毒蛇山谷"
output_folder = r"C:\Users\lihehui\Desktop\mapout\传战毒蛇山谷\jpg"

# 确保输出文件夹存在
os.makedirs(output_folder, exist_ok=True)

# 遍历输入文件夹所有文件
for root, dirs, files in os.walk(input_folder):
    for file in files:
        if file.lower().endswith('.png'):
            png_path = os.path.join(root, file)
            # 保留原文件名，改扩展名为 .jpg
            jpg_filename = os.path.splitext(file)[0] + '.jpg'
            jpg_path = os.path.join(output_folder, jpg_filename)
            
            # 打开 PNG
            img = Image.open(png_path)
            
            # 如果有透明通道，填充为白色背景
            if img.mode in ('RGBA', 'LA'):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])  # alpha 通道
                img = background
            else:
                img = img.convert("RGB")
            
            # 保存为 JPG，高质量
            img.save(jpg_path, "JPEG", quality=100)
            print(f"已转换: {png_path} → {jpg_path}")

print("批量转换完成！")