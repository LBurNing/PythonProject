from PIL import Image

def replace_white_with_transparency(input_image_path, output_image_path):
    # 打开图片
    image = Image.open(input_image_path).convert("RGBA")
    width, height = image.size
    pixels = image.load()

    # 遍历每个像素
    for x in range(width):
        for y in range(height):
            r, g, b, a = pixels[x, y]
            # 判断是否为白色像素（可根据实际情况调整阈值）
            if r > 240 and g > 240 and b > 240:
                # 将白色像素的透明度设置为 0
                pixels[x, y] = (r, g, b, 0)

    # 保存处理后的图片为 PNG 格式
    image.save(output_image_path, "PNG")

# 输入图片路径
input_image_path = r"C:\Users\lihehui\Desktop\Res\1.jpg"
# 输出图片路径
output_image_path = r"C:\Users\lihehui\Desktop\Res\out.png"

# 调用函数进行处理
replace_white_with_transparency(input_image_path, output_image_path)