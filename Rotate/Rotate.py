from PIL import Image
import math
import sys
import os

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'Rotate\\Images\\origin'
    outRoot = 'Rotate\\Images\\Rotate'
    angle = -50
else:
    pathRoot = sys.argv[1]
    angle = int(sys.argv[2])
    outRoot = pathRoot
    print("Release模式\nreadPath: ", pathRoot, " angle: ", angle)

filePaths = os.listdir(pathRoot)

def rotateImages():
    for i in range(0, len(filePaths)):
        img_path = str(pathRoot + "\\" + filePaths[i])
        out_path = str(outRoot + "\\" + filePaths[i])

        rotation(img_path, out_path)
        print("图片旋转: ", img_path, " angle: ", angle)

def rotation(img_path, out_path):
    # 打开PNG图片
    image = Image.open(img_path)
    
    # 旋转图片
    rotated_image = image.rotate(angle, resample=Image.BICUBIC, expand=True)

    dir = os.path.dirname(out_path)
    exist = os.path.exists(dir)

    if not exist:
        os.makedirs(dir)

    # 将旋转后的图片保存到本地文件
    rotated_image.save(out_path)

rotateImages()
