import json
from PIL import Image
import os

def get_files(folder_path, suffix):
    file_paths = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if(filename.endswith(suffix)):
                file_paths.append(os.path.join(root, filename))
    return file_paths

def split_spritesheet(json_file):
    """
    根据 JSON 文件描述，对大图进行切割，并保存每个小图到与 JSON 文件同级目录下。

    参数：
    - json_file: 包含图集描述的 JSON 文件名

    返回值：
    切割后的图像文件名列表
    """
    # 读取 JSON 文件
    with open(json_file, 'r') as file:
        data = json.load(file)

    # 获取 JSON 文件所在目录路径
    json_dir = os.path.dirname(json_file)

    # 加载大图
    image_file = os.path.join(json_dir, data['meta']['image'])
    image = Image.open(image_file)

    # 创建保存切割后图片的目录
    output_dir = os.path.splitext(json_file)[0]  # 去掉文件后缀
    os.makedirs(output_dir, exist_ok=True)

    # 保存切割后的图像文件名列表
    sprite_filenames = []

   # 遍历每个帧的描述
    for frame_id, frame_data in data['frames'].items():
        # 获取帧的位置和尺寸
        frame = frame_data['frame']
        x, y, w, h = frame['x'], frame['y'], frame['w'], frame['h']
        
        # 获取精灵在大图中的偏移值
        source_size = frame_data['spriteSourceSize']
        source_x, source_y = int(source_size['x']), int(source_size['y'])
        
        # 切割图像
        sprite_image = image.crop((x, y, x + w, y + h))

        # 对切割后的图片进行偏移
        new_width = w * 2 + 40 + abs(source_x)
        new_height = h * 2 + 40 + abs(source_y)

        offset_image = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
        offset_image.paste(sprite_image, (new_width // 2 + source_x, new_height // 2 + source_y))  
        
        # 保存切割后的图像
        sprite_filename = os.path.join(output_dir, f"{frame_id}.png")
        offset_image.save(sprite_filename)
        sprite_filenames.append(sprite_filename)

        print(f"Saved sprite {frame_id} as {sprite_filename}")

floder_path = r'E:\anfeng\product\h5\res\action\3\301047'
act_files = get_files(floder_path, '.act')
for filepath in act_files:
    split_spritesheet(filepath)