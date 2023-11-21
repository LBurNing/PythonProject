from PIL import Image
import os

# 设置图片文件夹路径和输出路径
image_folder = 'C:\\Users\\lihehui\\Desktop\\png'
output_path = os.path.join("C:\\Users\\lihehui\\Desktop\\out", '4.jpg')

# 获取图片列表并按文件名排序
image_files = sorted([f for f in os.listdir(image_folder) if f.endswith('.PNG')], key=lambda x: int(x.split('.')[0]))

# 设置每行和每列的图片数量
num_columns = 55
num_rows = 60

# 设置单个图片的大小
image_width = 96  # 你可以根据实际情况调整图片大小
image_height = 64

# 创建一个新的大图
result_image = Image.new('RGB', (num_columns * image_width, num_rows * image_height))

# 遍历图片列表并将它们粘贴到大图中
for i, image_file in enumerate(image_files):
    row = i // num_columns
    col = i % num_columns
    img_path = os.path.join(image_folder, image_file)
    img = Image.open(img_path)
    img = img.resize((image_width, image_height), Image.LANCZOS)
    result_image.paste(img, (col * image_width, row * image_height))

# 保存拼接后的大图
result_image.save(output_path)

print(f"拼接完成，保存为 {output_path}")
