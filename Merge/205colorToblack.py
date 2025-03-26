import os
import sys
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import numpy as np
Image.MAX_IMAGE_PIXELS = None

debug = sys.gettrace()
if debug:
    # 指定输入图像和输出路径
    input_image_path = r"C:\Users\lihehui\Desktop\1\幽冥\Maps\map\tiles\56098\56098.jpg"
    output_image_path = r"C:\Users\lihehui\Desktop\1\幽冥\Maps\map\tiles\56098\56098_out.jpg"
else:
    input_image_path = sys.argv[1]
    output_image_path = sys.argv[2]

def replace_color(image_path, output_path, target_color=(205, 205, 205), replacement_color=(0, 0, 0)):
    # 打开图像
    image = Image.open(image_path)

    # 将图像转换为RGB模式
    image = image.convert('RGB')

    # 将图像转换为NumPy数组
    img_array = np.array(image)

    # 定义目标颜色的条件
    target_color_condition = (img_array[:, :, 0] == target_color[0]) & \
                             (img_array[:, :, 1] == target_color[1]) & \
                             (img_array[:, :, 2] == target_color[2])

    # 将满足条件的像素替换为指定的颜色
    img_array[target_color_condition] = replacement_color

    # 将NumPy数组转换回图像
    modified_image = Image.fromarray(img_array)

    # 保存修改后的图像
    modified_image.save(output_path)

replace_color(input_image_path, output_image_path, target_color=(205, 205, 205), replacement_color=(0, 0, 0))
