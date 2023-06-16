import sys
import os
from PIL import Image, ImageOps
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'C:\\Users\\lihehui\\Desktop\\100109阶套装\\王者之刃内观\\待机'
    outRoot = 'C:\\Users\\lihehui\\Desktop\\100109阶套装\\王者之刃内观\\待机\\Scale'
    scale = 0.8
    offset_x = 0
    offset_y = 0
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    scale = float(sys.argv[3])
    offset_x = int(sys.argv[4])
    offset_y = int(sys.argv[5])
    print("Release模式\nreadPath: ", pathRoot, " outPath: ", outRoot)

filePaths = []
for root, dirs, files in os.walk(pathRoot):
    for fileName in files:
        if fileName.endswith('.png') or fileName.endswith('.PNG'):
            filePaths.append(os.path.join(root, fileName))

def scaleImage(img_path, out_path):
    # 缩放图片
    img = Image.open(img_path)
    new_size = (int(img.width * scale), int(img.height * scale))
    new_img = img.resize(new_size, Image.Resampling.LANCZOS)

    # 创建新的图片对象
    background = Image.new('RGBA', new_size, (0, 0, 0, 0))

    # 将缩放后的图片粘贴到新的图片上，并进行偏移
    background.paste(new_img, (offset_x, -offset_y))

    # 保存处理后的图片
    background.save(out_path)
    return out_path

def scaleImages():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for i in range(0, len(filePaths)):
            img_path = filePaths[i]
            out_path = outRoot + "\\" + os.path.basename(img_path)
            futures.append(executor.submit(scaleImage, img_path, out_path))

            dir = os.path.dirname(out_path)
            exist = os.path.exists(dir)

            if not exist:
                os.makedirs(dir)

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(e)
            
            print("图片缩放完成: ", future.result())

scaleImages()