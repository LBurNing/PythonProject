#旋转图片并输出
from PIL import Image, ImageFilter
import math
import sys
import os

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'Rotate\\Images\\origin'
    outRoot = 'Rotate\\Images\\Rotate'
    angle = -50
    type = 2
else:
    pathRoot = sys.argv[1]
    angle = int(sys.argv[2])
    type = int(sys.argv[3])
    outRoot = pathRoot
    print("Release模式\nreadPath: ", pathRoot, " angle: ", angle)

filePaths = os.listdir(pathRoot)

def transpose(img_path, out_path):
    # 打开PNG图片
    image = Image.open(img_path)

    # 水平翻转
    if type == 1:
        img_out = image.transpose(method=Image.FLIP_LEFT_RIGHT)

    # 垂直翻转
    if type == 2:
        img_out = image.transpose(method=Image.FLIP_TOP_BOTTOM)

    dir = os.path.dirname(out_path)
    exist = os.path.exists(dir)

    if not exist:
        os.makedirs(dir)

    # 将旋转后的图片保存到本地文件
    img_out.save(out_path)

def manageImages():
    for i in range(0, len(filePaths)):
        img_path = str(pathRoot + "\\" + filePaths[i])
        out_path = str(outRoot + "\\" + filePaths[i])

        if type == 0:
            rotation(img_path, out_path)
            print("图片旋转: ", img_path, " angle: ", angle)
        else:
            transpose(img_path, out_path)
            print("图片翻转: ", img_path, " angle: ", angle)

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

manageImages()
