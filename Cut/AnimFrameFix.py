# 以全局中心点为中心裁切最大像素区域
import sys
import os
from PIL import Image
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = r'D:\WXWork\Cache\WXWork\1688858110580230\Cache\File\2025-09\英灵2\61040'
    outRoot = pathRoot + r"\out"
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    print("Release模式\nreadPath:", pathRoot, " outPath:", outRoot)

os.makedirs(outRoot, exist_ok=True)

# ---------------- 获取所有 PNG ----------------
def get_png_files(path):
    png_files = []
    for root, dirs, files in os.walk(path):
        for fileName in files:
            if fileName.lower().endswith('.png'):
                filePath = os.path.join(root, fileName)
                png_files.append(filePath)
    return png_files

filePaths = get_png_files(pathRoot)

# ---------------- 计算全局 bbox ----------------
bboxes = {}
min_left, min_top = float("inf"), float("inf")
max_right, max_bottom = 0, 0

for f in filePaths:
    img = Image.open(f).convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        left, top, right, bottom = bbox
        bboxes[f] = bbox
        min_left = min(min_left, left)
        min_top = min(min_top, top)
        max_right = max(max_right, right)
        max_bottom = max(max_bottom, bottom)
    else:
        bboxes[f] = None  # 全透明

# 全局宽高（保证偶数）
w = (max_right - min_left)
h = (max_bottom - min_top)
w += w % 2
h += h % 2

print(f"统一裁切区域: {w}x{h}")

# ---------------- 裁切函数 ----------------
def cutImage(img_path, out_path):
    if bboxes[img_path] is None:
        return "跳过全透明: " + img_path

    img = Image.open(img_path).convert("RGBA")
    width, height = img.size
    # 设置裁切区域中心点坐标和宽高
    x = width / 2
    y = height / 2

    # 以全局中心点为基准裁切
    left = x - w / 2
    top = y - h / 2
    right = x + w / 2
    bottom = y + h / 2

    # 保证不超过图片边界
    left = max(0, left)
    top = max(0, top)
    right = min(width, right)
    bottom = min(height, bottom)

    img_crop = img.crop((left, top, right, bottom))
    img_crop.save(out_path)
    return out_path

# ---------------- 多线程批处理 ----------------
def cutImages():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for img_path in filePaths:
            out_path = os.path.join(outRoot, os.path.basename(img_path))
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            futures.append(executor.submit(cutImage, img_path, out_path))

        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                print("图片裁切完成:", result)
            except Exception as e:
                print("裁切出错:", e)

cutImages()