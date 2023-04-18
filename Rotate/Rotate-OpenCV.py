import os
import cv2
import numpy as np
import os
import sys
from PIL import Image, ImageFilter

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

def mergeImages():
    for i in range(0, len(filePaths)):
        img_path = str(pathRoot + "\\" + filePaths[i])
        out_path = str(outRoot + "\\" + filePaths[i])

        rotation(img_path, out_path)
        print("图片旋转: ", img_path, " angle: ", angle)

def rotation(img_path, output_path):
    # 读取图像，包括 alpha 通道
    # img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

    # 获取图像尺寸
    (h, w) = img.shape[:2]

    # 定义旋转中心
    center = (w // 2, h // 2)

    # 定义旋转矩阵
    M = cv2.getRotationMatrix2D(center, angle, 1.0)

    # 应用旋转矩阵
    rotated = cv2.warpAffine(img, M, (w, h))

    # 将旋转矩阵应用于 alpha 通道
    alpha = cv2.split(rotated)[3]
    alpha = cv2.warpAffine(alpha, M, (w, h))

    # 阈值化图像
    thresh = cv2.threshold(alpha, -10, 255, cv2.THRESH_BINARY)[1]

    # 创建掩膜
    mask = np.zeros_like(thresh)

    # 获取轮廓
    contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]

    # 填充轮廓
    cv2.drawContours(mask, contours, -1, (255, 255, 255), -1)

    # 应用掩膜
    result = cv2.bitwise_and(rotated, rotated, mask=mask)

    dir = os.path.dirname(output_path)
    exist = os.path.exists(dir)
    if not exist:
        os.makedirs(dir)

    # 保存旋转后的图像
    cv2.imencode('.png', result)[1].tofile(output_path)

    # 关闭所有窗口
    cv2.destroyAllWindows()

# mergeImages()
image = Image.open('Rotate\\Images\\origin\\50000.png')
img = image.filter(ImageFilter.SHARPEN)
img.save('sharpened_image.png')