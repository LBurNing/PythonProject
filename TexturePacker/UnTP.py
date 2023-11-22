import os
import plistlib
from PIL import Image
import sys

direction_mapping = {
    0: 1,
    1: 2,
    2: 3,
    3: 4,
    4: 5,
    5: 6,
    6: 7,
    7: 8,
}

index2name_mapping = {
    0: "待机",
    1: "走路",
    2: "攻击",
    3: "3未知",
    4: "死亡",
    5: "5未知",
    6: "6未知",
    7: "受击",
}

debug = sys.gettrace()
if debug:
    plist_dir = "E:\\plist\\怪物模型"
else:
    plist_dir = sys.argv[1]

def gen_png_from_plist(plist_filename, png_filename):
    # 打开要读取的.plist文件
    with open(plist_filename, 'rb') as file:
        # 调用load方法来解析.plist文件
        root = plistlib.load(file)

    frames = root['frames']
    to_list = lambda x: x.replace('{', '').replace('}', '').split(',')
    to_int = lambda x: int(x)
    for frame in frames:
        framename = frame.replace('.png', '')

        # 提取规则中的数字部分
        filename_parts = framename.split('_')
        main_folder = f"monster_{filename_parts[1]}"
        sub_folder = f"{filename_parts[3]}"
        sub_folder = index2name_mapping[int(sub_folder)]
        file_path = os.path.join(os.path.dirname(plist_filename) + "\\out\\", main_folder, sub_folder)
        big_image = Image.open(png_filename)

        index = substring = filename_parts[-2]
        substring = filename_parts[-1]
        framename = direction_mapping[int(index)] * 10000 + int(substring)

        size = frames[frame]['sourceColorRect']
        size = to_list(size)
        size = list(map(to_int, size))

        spriteSize = frames[frame]['sourceSize']
        spriteSize = to_list(spriteSize)
        spriteSize = list(map(to_int, spriteSize))

        textureRect = frames[frame]['frame']
        textureRect = to_list(textureRect)
        textureRect = list(map(to_int, textureRect))

        offset = frames[frame]['offset']
        offset = to_list(offset)
        offset = list(map(to_int, offset))

        result_box = textureRect
        result_image = Image.new('RGBA', spriteSize, 0)
        if frames[frame]['rotated']:
            result_box[0] = int(textureRect[0])
            result_box[1] = int(textureRect[1])

            #如果有旋转, 裁切矩阵宽高调换
            width = textureRect[2]
            height = textureRect[3]
            result_box[2] = int(textureRect[0] + height)
            result_box[3] = int(textureRect[1] + width)
        else:
            result_box[0] = int(textureRect[0])
            result_box[1] = int(textureRect[1])
            result_box[2] = int(textureRect[0] + textureRect[2])
            result_box[3] = int(textureRect[1] + textureRect[3])
        
        rect_on_big = big_image.crop(result_box)
        if frames[frame]['rotated']:
            rect_on_big = rect_on_big.transpose(Image.ROTATE_90)
        result_image.paste(rect_on_big)

        if not os.path.isdir(file_path):
            os.makedirs(file_path)

        outfile = os.path.join(file_path, str(framename) + '.png')
        if os.path.exists(outfile):
            continue
        
        print(outfile, "generated")

        # 获取图片尺寸
        width, height = result_image.size
        x_offset = offset[0]
        y_offset = offset[1]

        # 计算偏移后的新坐标
        new_x = abs(x_offset) + width * 2 + 40
        new_y = abs(y_offset) + height * 2 + 40
        
        # 创建一个新的空白图片，尺寸为偏移后的坐标
        new_image = Image.new("RGBA", (new_x, new_y), (0, 0, 0, 0))

        # 将原始图片粘贴到新图片的偏移位置
        new_image.paste(result_image, (new_x // 2 + x_offset, new_y // 2 - y_offset))  
        new_image.save(outfile)


for filename in os.listdir(plist_dir):
    if filename.endswith(".plist"):
        plist_path = os.path.join(plist_dir, filename)
        png_path = os.path.join(plist_dir, filename.replace(".plist", ".png"))
        gen_png_from_plist(plist_path, png_path)

# filename = "monster_52013_0_2_3.plist"
# plist_path = os.path.join(plist_dir, filename)
# png_path = os.path.join(plist_dir, filename.replace(".plist", ".png"))
# gen_png_from_plist(plist_path, png_path)
