import os
import sys
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import numpy as np
Image.MAX_IMAGE_PIXELS = None

debug = sys.gettrace()
if len(sys.argv) >= 3:
    print("Release模式\n")
    input_image_path = sys.argv[1]
    output_image_path = sys.argv[2]
    print("Release模式\ninput_image_path: ", input_image_path, " output_image_path: ", output_image_path)
else:
    # 指定输入图像和输出路径
    input_image_path = r"C:\Users\lihehui\Desktop\9张地图\dt070323W\dt070323W\Maps\map\tiles\New_rxcq2012\New_rxcq2012.png"
    output_image_path = r"C:\Users\lihehui\Desktop\9张地图\dt070323W\dt070323W\Maps\map\tiles\New_rxcq2012\New_rxcq2012.png"

def replace_color(image_path, output_path, target_color_range=((200, 210), (200, 210), (200, 210)), replacement_color=(0, 0, 0)):
    # 打开图像
    image = Image.open(image_path)

    # 将图像转换为RGB模式
    image = image.convert('RGB')
    
    

    # 将图像转换为NumPy数组
    img_array = np.array(image)

    # 定义目标颜色的条件（范围匹配）
    target_color_condition = (
        (img_array[:, :, 0] >= target_color_range[0][0]) & (img_array[:, :, 0] <= target_color_range[0][1]) &
        (img_array[:, :, 1] >= target_color_range[1][0]) & (img_array[:, :, 1] <= target_color_range[1][1]) &
        (img_array[:, :, 2] >= target_color_range[2][0]) & (img_array[:, :, 2] <= target_color_range[2][1])
    )

    # 将满足条件的像素替换为指定的颜色
    img_array[target_color_condition] = replacement_color

    # 将NumPy数组转换回图像
    modified_image = Image.fromarray(img_array)

    # 保存修改后的图像
    modified_image.save(output_path)

replace_color(input_image_path, output_image_path, target_color_range=((204, 206), (204, 206), (204, 206)), replacement_color=(0, 0, 0))
