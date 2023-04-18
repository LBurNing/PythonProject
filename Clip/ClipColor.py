import cv2
import numpy as np
import sys
import os
from PIL import Image, ImageFilter

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'Clip\\Images\\origin'
    outRoot = 'Clip\\Images\\Clip'
    angle = -50
else:
    pathRoot = sys.argv[1]
    angle = int(sys.argv[2])
    outRoot = pathRoot
    print("Release模式\nreadPath: ", pathRoot, " angle: ", angle)

filePaths = os.listdir(pathRoot)

def clipImages():
    for i in range(0, len(filePaths)):
        img_path = str(pathRoot + "\\" + filePaths[i])
        out_path = str(outRoot + "\\" + str.replace(filePaths[i], '.bmp', '.png'))

        clip(img_path, out_path)
        print("图片去色: ", img_path, " angle: ", angle)

def clip(img_path, out_path):
        # 打开 BMP 图像并将其转换为灰度图像
        image = Image.open(img_path)

       # Create a new image with the same size and a white background
        background = Image.new("RGB", image.size, (255, 255, 255))

        # Alpha composite the image and the background to create a new image with a white background and the original image on top
        image_with_white_bg = Image.alpha_composite(background, image)

        # Invert the colors of the image with a white background
        inverted_image = ImageOps.invert(image_with_white_bg)

        # Create a new image with the same size and a black background
        black_bg = Image.new("RGB", image.size, (0, 0, 0))

        # Alpha composite the inverted image and the black background to create a new image with a black background and the original image on top
        image_with_black_bg = Image.alpha_composite(black_bg, inverted_image)

        # Invert the colors of the image with a black background
        result = ImageOps.invert(image_with_black_bg)

        dir = os.path.dirname(out_path)
        exist = os.path.exists(dir)

        if not exist:
            os.makedirs(dir)

        result.save(out_path)
        # 保存去色后的图像
        # cv2.imencode('.png', img)[1].tofile(out_path)

clipImages()

