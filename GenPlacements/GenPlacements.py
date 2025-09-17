import json
import os
from PIL import Image

# === 你的路径 ===
atlas_path = r"c:\Users\lihehui\Desktop\205548-529-24815716(1)\assets\builtin\anims\decoded_pngs\174919440852925.png"
json_path = r"c:\Users\lihehui\Desktop\205548-529-24815716(1)\assets\builtin\anims\174919440854526.mjson"
output_image_dir = "output_frames"
output_offset_dir = "Placements"

os.makedirs(output_image_dir, exist_ok=True)
os.makedirs(output_offset_dir, exist_ok=True)

# === 加载资源 ===
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

atlas = Image.open(atlas_path).convert("RGBA")
frames = data["anim"]["00"]["frames"]

# === 第一步：找出包围所有帧图像的区域 ===
min_x = min(f["offset"]["x"] for f in frames)
min_y = min(f["offset"]["y"] for f in frames)
max_x = max(f["offset"]["x"] + (f["rect"]["h"] if f.get("rotated", False) else f["rect"]["w"]) for f in frames)
max_y = max(f["offset"]["y"] + (f["rect"]["w"] if f.get("rotated", False) else f["rect"]["h"]) for f in frames)

canvas_width = max_x - min_x
canvas_height = max_y - min_y

print(f"统一画布尺寸: {canvas_width}x{canvas_height}")

# === 第二步：绘制每帧 ===
for i, frame in enumerate(frames):
    rect = frame["rect"]
    offset = frame["offset"]
    rotated = frame.get("rotated", False)

    x, y, w, h = rect["x"], rect["y"], rect["w"], rect["h"]
    crop_box = (x, y, x + w, y + h)
    cropped = atlas.crop(crop_box)

    if rotated:
        cropped = cropped.rotate(90, expand=True)
        w, h = h, w

    # === 创建统一画布，并把图像放在偏移后的位置 ===
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

    # 锚点对齐：offset - min_offset = 图像左上角在画布中的位置
    paste_x = offset["x"] - min_x
    paste_y = offset["y"] - min_y

    canvas.paste(cropped, (paste_x, paste_y), cropped)

    # 保存图像和 offset.txt
    frame_name = f"frame_{i:02d}"
    image_path = os.path.join(output_image_dir, frame_name + ".png")
    offset_path = os.path.join(output_offset_dir, frame_name + ".txt")

    canvas.save(image_path)

    with open(offset_path, "w") as f:
        f.write(f"{offset['x']}\n{offset['y']}")

    print(f"✅ 已保存: {image_path} 对齐锚点 ({offset['x']},{offset['y']})")