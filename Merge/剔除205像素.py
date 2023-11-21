from PIL import Image

def replace_white_with_black(image_path, output_path):
    # 打开图像
    image = Image.open(image_path)

    # 获取图像的宽度和高度
    width, height = image.size

    # 遍历图像的每个像素
    for x in range(width):
        for y in range(height):
            # 获取像素的RGBA值
            r, g, b, a = image.getpixel((x, y))

            # 如果是白色，则将其替换为黑色
            if r == 205 and g == 205 and b == 205:
                image.putpixel((x, y), (0, 0, 0, a))

    # 保存修改后的图像
    image.save(output_path)

# 指定输入图像和输出路径
input_image_path = "C:\\Users\\lihehui\\Desktop\\out\\7.jpg"
output_image_path = "C:\\Users\\lihehui\\Desktop\\out\\7_1.png"

# 执行替换操作
replace_white_with_black(input_image_path, output_image_path)
