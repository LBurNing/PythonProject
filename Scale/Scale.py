#缩放图片并输出
import sys
import os
from PIL import Image, ImageOps, ImageEnhance
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'C:\\Users\\lihehui\\Desktop\\通用\\外观\\待机'
    outRoot = 'C:\\Users\\lihehui\\Desktop\\通用\\外观\\待机'
    scale = 1
    offset_x = -50
    offset_y = -50
    dir = 8 #8表示无方向
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    scale = float(sys.argv[3])
    offset_x = int(sys.argv[4])
    offset_y = int(sys.argv[5])
    dir = int(sys.argv[6])
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

    fileName = os.path.basename(img_path)
    if dir == 8 or fileName[:len(str(dir))] == str(dir):
        background.paste(new_img, (offset_x, -offset_y))
    else:
        background.paste(new_img, (0, 0))

    if scale != 1:
        enhancer = ImageEnhance.Sharpness(background)
        enhanced_image = enhancer.enhance(2.0)

        # 保存处理后的图片
        enhanced_image.save(out_path)
    else:
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