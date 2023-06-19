#以中心点为中心 裁切指定大小的图片
import sys
import os
from PIL import Image, ImageOps
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'D:\\测试资源\\头盔\\待机'
    outRoot = 'D:\\测试资源\\头盔\\待机\\Cut'
    w = 200
    h = 150
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    w = int(sys.argv[3])
    h = int(sys.argv[4])
    print("Release模式\nreadPath: ", pathRoot, " outPath: ", outRoot)

filePaths = []
for root, dirs, files in os.walk(pathRoot):
    for fileName in files:
        if fileName.endswith('.png') or fileName.endswith('.PNG'):
            filePaths.append(os.path.join(root, fileName))

def cutImage(img_path, out_path):
    # 打开图片
    img = Image.open(img_path)

    # 获取图片尺寸
    width, height = img.size

    # 设置裁切区域中心点坐标和宽高
    x = width / 2
    y = height / 2

    # 计算裁切区域左上角和右下角坐标
    left = x - w / 2
    top = y - h / 2
    right = x + w / 2
    bottom = y + h / 2

    # 裁切图片
    img_crop = img.crop((left, top, right, bottom))

    # 保存裁切后的图片
    img_crop.save(out_path)
    return out_path

def cutImages():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for i in range(0, len(filePaths)):
            img_path = filePaths[i]
            out_path = outRoot + "\\" + os.path.basename(img_path)
            futures.append(executor.submit(cutImage, img_path, out_path))

            dir = os.path.dirname(out_path)
            exist = os.path.exists(dir)

            if not exist:
                os.makedirs(dir)

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(e)
            
            print("图片裁切完成: ", future.result())

cutImages()