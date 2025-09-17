import sys
import os
from PIL import Image

# ---------------- Debug/Release 区分 ----------------
debug = sys.gettrace()  # True 表示在调试器下运行

if debug:
    print("Debug模式")
    pathRoot = r'D:\WXWork\Cache\WXWork\1688858110580230\Cache\File\2025-09\英灵2\修正后的PNG资源\61040\1\1'
    outRoot = os.path.join(pathRoot, "out")
else:
    if len(sys.argv) < 3:
        print("Release模式需要传入参数: 输入路径 输出路径")
        sys.exit(1)

    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    print("Release模式\nreadPath:", pathRoot, " outPath:", outRoot)

os.makedirs(outRoot, exist_ok=True)

# ---------------- 裁剪并对齐序列帧 ----------------
frames_info = []  # [(filename, cropped_img, left, top, right, bottom)]

for filename in sorted(os.listdir(pathRoot)):
    if not filename.lower().endswith(".png"):
        continue

    path = os.path.join(pathRoot, filename)
    img = Image.open(path).convert("RGBA")
    bbox = img.getbbox()
    if not bbox:
        continue

    left, top, right, bottom = bbox
    cropped = img.crop(bbox)
    frames_info.append((filename, cropped, left, top, right, bottom))

# 计算统一画布尺寸（最小包围）
min_left = min(f[2] for f in frames_info)
min_top = min(f[3] for f in frames_info)
max_right = max(f[4] for f in frames_info)
max_bottom = max(f[5] for f in frames_info)

canvas_width = max_right - min_left
canvas_height = max_bottom - min_top

print(f"统一画布大小: {canvas_width}x{canvas_height}")

# 生成最终帧
for filename, cropped, left, top, right, bottom in frames_info:
    new_img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    paste_x = left - min_left
    paste_y = top - min_top
    new_img.paste(cropped, (paste_x, paste_y))
    out_path = os.path.join(outRoot, filename)
    new_img.save(out_path)

print("序列帧裁切完成，已保存到:", outRoot)