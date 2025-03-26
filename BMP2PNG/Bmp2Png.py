#去除存黑的像素
import sys
from PIL import Image
import glob
import os
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = r'C:\Users\lihehui\Desktop\Map\塞外\Map\关外\Objects250\\'
    outRoot = r'C:\Users\lihehui\Desktop\Map\塞外\Map\关外\Objects250\\out\\'
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    print("Release模式\nreadPath: ", pathRoot, " outPath: ", outRoot)

def getFileName(path):
    file_name = os.path.basename(path)
    file_name_without_extension = os.path.splitext(file_name)[0]
    return file_name_without_extension

def cullBlack(image_path, out_path):
    # 打开图片
    image = Image.open(image_path)

    # 将图片转换为 RGBA 模式
    image = image.convert("RGBA")

    # 获取图片的像素数据
    data = image.getdata()

    # 创建一个新的像素列表，将黑色像素替换为透明
    new_data = []
    for item in data:
        # 判断当前像素是否为黑色
        if item[:3] == (0, 0, 0) or (item[0] < 10 and item[1] < 10 and item[2] < 10):
            # 如果是黑色像素，则将其改为透明
            new_data.append((0, 0, 0, 0))
        else:
            # 如果不是黑色像素，则保留原样
            new_data.append(item)

    # 将修改后的像素数据更新到图片中
    image.putdata(new_data)
    os.remove(image_path)
    image.save(out_path)
    return out_path

# 获取符合指定路径模式的文件列表
file_list = glob.glob(pathRoot + "*.bmp")
file_list.extend(glob.glob(pathRoot + "*.BMP"))
file_list.extend(glob.glob(pathRoot + "*.PNG"))
file_list.extend(glob.glob(pathRoot + "*.png"))

def cullBlacks():
    index = 1
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for file_path in file_list:
            fileName = getFileName(file_path)
            out_path = str(outRoot + fileName + '.png')
            futures.append(executor.submit(cullBlack, file_path, out_path))

            dir = os.path.dirname(out_path)
            exist = os.path.exists(dir)
            index = index + 1
            print("去除存黑像素: ", out_path, " progress: ", index, "/" , len(file_list), " ", round((index / len(file_list)) * 100, 2), "%")

            if not exist:
                os.makedirs(dir)

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(e)

cullBlacks()