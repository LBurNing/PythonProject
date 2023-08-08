#图片叠加混合 去除带有alpha通道的黑色背景one one_minus_src_alpha
import sys
import os
from PIL import Image
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = 'D:\\RXCQ\\源资源\\magic\\'
    outRoot = 'D:\\RXCQ\\源资源\\magic\\'
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    print("Release模式\nreadPath: ", pathRoot, " outPath: ", outRoot)

filePaths = os.listdir(pathRoot)

#D:\UnityHub\Unity2021.3.19f1\Editor\Unity.exe -batchmode -quit -executeMethod GameBuildUtils.PackAll -projectPath D:\FGCQ\code\client\game -logFile unitylog.log

def blend_one_one_minus_src_alpha(src_color, dst_color):
    # 提取源颜色和目标颜色的RGBA分量
    src_r, src_g, src_b, src_a = src_color
    dst_r, dst_g, dst_b, dst_a = dst_color
    if src_r == 0 and src_g == 0 and src_b == 0:
        out_a = 0
        outColor = (0, 0, 0, 0)
        # 返回混合后的颜色
        return outColor

    d_r = (255 - src_a) * dst_r
    d_g = (255 - src_a) * dst_g
    d_b = (255 - src_a) * dst_b
    d_a = (255 - src_a) * dst_a

    # 计算混合后的RGBA分量
    out_r = src_r + int(d_r / 255.0) * 2
    out_g = src_g + int(d_g / 255.0) * 2
    out_b = src_b + int(d_b / 255.0) * 2
    out_a = src_a

    if out_r == 0 and out_b == 0 and out_g == 0:
        out_a = 0

    outColor = (out_r, out_g, out_b, out_a)

    # 返回混合后的颜色
    return outColor

def clip(img_path, out_path):
    mainTex = Image.open(img_path).convert("RGBA")
    blendedTex = Image.new("RGBA", mainTex.size)

    for y in range(mainTex.height):
        for x in range(mainTex.width):
            mainTexColor = mainTex.getpixel((x, y))
            a = max(mainTexColor[0], mainTexColor[1], mainTexColor[2])
            scrColor = (mainTexColor[0], mainTexColor[1], mainTexColor[2], a)
            colorTemp = blend_one_one_minus_src_alpha(scrColor, mainTexColor)
            blendedTex.putpixel((x, y), colorTemp)

    os.remove(img_path)
    # 保存处理后的图片
    blendedTex.save(out_path)
    return out_path

def blendImages():
    index = 1
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for i in range(0, len(filePaths)):
            img_path = str(pathRoot + "\\" + filePaths[i])
            fileName = str.replace(filePaths[i], '.bmp', '.png')
            fileName = str.replace(fileName, '.BMP', '.png')
            out_path = str(outRoot + "\\" + fileName)
            futures.append(executor.submit(clip, img_path, out_path))

            dir = os.path.dirname(out_path)
            exist = os.path.exists(dir)
            index = index + 1
            print("Alpha Blend: ", out_path, " progress: ", index, "/" , len(filePaths), " ", round((index / len(filePaths)) * 100, 2), "%")

            if not exist:
                os.makedirs(dir)

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(e)

blendImages()