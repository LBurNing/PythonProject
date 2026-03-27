import os
import plistlib
from PIL import Image
import re

def parse_group_name(filename):
    """
    提取编号：
    obj108_0.plist -> 108
    tiles109_1.plist -> 109
    """
    match = re.search(r'(\d+)', filename)
    return match.group(1) if match else None

def get_output_dir(base_dir, filename, group_id):
    """
    生成输出目录
    """
    if filename.startswith("obj"):
        folder_name = f"Objects{group_id}"
    elif filename.startswith("tiles"):
        folder_name = f"Tiles{group_id}"
    else:
        folder_name = f"Other{group_id}"

    out_dir = os.path.join(base_dir, "out", folder_name)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    return out_dir


def gen_png_from_plist(plist_filename, png_filename, output_dir):
    with open(plist_filename, 'rb') as file:
        root = plistlib.load(file)

    frames = root['frames']

    to_list = lambda x: x.replace('{', '').replace('}', '').split(',')
    to_int = lambda x: int(x)

    big_image = Image.open(png_filename)

    for frame in frames:
        framename = frame.split('_')[-1]
        outfile = os.path.join(output_dir, framename)

        if os.path.exists(outfile):
            continue

        size = list(map(to_int, to_list(frames[frame]['sourceColorRect'])))
        spriteSize = list(map(to_int, to_list(frames[frame]['sourceSize'])))
        textureRect = list(map(to_int, to_list(frames[frame]['frame'])))
        offset = list(map(to_int, to_list(frames[frame]['offset'])))

        if frames[frame]['rotated']:
            result_box = [
                textureRect[0],
                textureRect[1],
                textureRect[0] + textureRect[3],
                textureRect[1] + textureRect[2]
            ]
        else:
            result_box = [
                textureRect[0],
                textureRect[1],
                textureRect[0] + textureRect[2],
                textureRect[1] + textureRect[3]
            ]

        rect_on_big = big_image.crop(result_box)

        if frames[frame]['rotated']:
            rect_on_big = rect_on_big.transpose(Image.ROTATE_90)

        # ===== 还原原始尺寸 =====
        orig_w, orig_h = spriteSize
        result_image = Image.new("RGBA", (orig_w, orig_h), (0, 0, 0, 0))

        rect_x, rect_y, rect_w, rect_h = size
        offset_x, offset_y = offset

        paste_x = int((orig_w - rect_w) / 2 + offset_x)
        paste_y = int((orig_h - rect_h) / 2 - offset_y)

        result_image.paste(rect_on_big, (paste_x, paste_y))
        result_image.save(outfile)

        print(f"Saved {outfile}")


def process_folder(base_dir):
    for filename in os.listdir(base_dir):
        if not filename.endswith(".plist"):
            continue

        group_id = parse_group_name(filename)
        if not group_id:
            continue

        plist_path = os.path.join(base_dir, filename)
        png_path = os.path.join(base_dir, filename.replace(".plist", ".png"))

        if not os.path.exists(png_path):
            print(f"缺少png: {png_path}")
            continue

        output_dir = get_output_dir(base_dir, filename, group_id)

        gen_png_from_plist(plist_path, png_path, output_dir)


# ===== 入口 =====
if __name__ == "__main__":
    base_path = r"C:\Users\lihehui\Desktop\Map\复古套图dt326\新建文件夹\objects"   # 改这里
    process_folder(base_path)

    base_path_tiles = r"C:\Users\lihehui\Desktop\Map\复古套图dt326\新建文件夹\tiles"  # tiles路径
    process_folder(base_path_tiles)