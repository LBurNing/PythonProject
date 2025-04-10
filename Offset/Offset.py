#图片中心点偏移
import sys
import os
from PIL import Image, ImageOps
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = r'D:\UnityProject\Card\Assets\Res\Textures\Animation\1004\\'
    outRoot = r'D:\UnityProject\Card\Assets\Res\Textures\Animation\1004\\'
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    print("Release模式\nreadPath: ", pathRoot, " outPath: ", outRoot)

filePaths = []
for root, dirs, files in os.walk(pathRoot):
    for fileName in files:
        if fileName.endswith('.png') or fileName.endswith('.PNG'):
            filePaths.append(os.path.join(root, fileName))

def offsetImage(img_path, out_path):
    image = Image.open(img_path)
    offset_text = os.path.dirname(img_path)
    text_filename = os.path.splitext(os.path.basename(img_path))[0] + ".txt"
    offset_text = os.path.join(offset_text + "/Placements/", text_filename)

    offsets = []
    f = open(offset_text, "r") 
    lines = f.readlines()      #读取全部内容 ，并以列表方式返回
    for line in lines:
        offsets.append(int(line))

    # 获取图片尺寸
    width, height = image.size
    x_offset = offsets[0]
    y_offset = offsets[1]

    # 计算偏移后的新坐标
    new_x = abs(x_offset) + width * 2 + 200
    new_y = abs(y_offset) + height * 2 + 200
    
    # 创建一个新的空白图片，尺寸为偏移后的坐标
    new_image = Image.new("RGBA", (new_x, new_y), (0, 0, 0, 0))

    # Unity0,0点在左下角, python中图片操作是在左上角
    # 将原始图片粘贴到新图片的偏移位置
    new_image.paste(image, (new_x // 2 - width // 2 + x_offset, new_y // 2 - height // 2 - y_offset))
    
    # 保存处理后的图片
    new_image.save(out_path)
    return out_path

def offsetImages():
        for i in range(0, len(filePaths)):
            img_path = filePaths[i]
            out_path = outRoot + "\\" + os.path.basename(img_path)
            dir = os.path.dirname(out_path)
            exist = os.path.exists(dir)

            if not exist:
                os.makedirs(dir)
            
            offsetImage(img_path, out_path)
            print("图片偏移完成: ", out_path)

offsetImages()