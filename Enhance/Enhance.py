#缩放图片并输出
import sys
import os
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'C:\\Users\\lihehui\\Desktop\\2'
    outRoot = 'C:\\Users\\lihehui\\Desktop\\2\\out'
    sharpness_factor = 2.0
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    sharpness_factor = float(sys.argv[3])
    print("Release模式\nreadPath: ", pathRoot, " outPath: ", outRoot)

filePaths = []
for root, dirs, files in os.walk(pathRoot):
    for fileName in files:
        if fileName.endswith('.png') or fileName.endswith('.PNG'):
            filePaths.append(os.path.join(root, fileName))

def scaleImage(img_path, out_path):
    img = Image.open(img_path)
    
    enhancer = ImageEnhance.Sharpness(img)
    enhanced_image = enhancer.enhance(sharpness_factor)

    # 保存处理后的图片
    enhanced_image.save(out_path)
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
            
            print("图片增强: ", future.result())

scaleImages()