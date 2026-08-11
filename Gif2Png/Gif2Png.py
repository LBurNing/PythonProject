# 将 GIF 动画拆成序列帧 PNG（转 RGB 不透明）
from PIL import Image, ImageSequence
import os
import sys


def gif2frames(gif_path, out_dir):
    im = Image.open(gif_path)
    total = im.n_frames
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(gif_path))[0]
    print(f"GIF: {gif_path}  帧数: {total}")
    for i, frame in enumerate(ImageSequence.Iterator(im)):
        try:
            out_path = os.path.join(out_dir, f"{50000 + i}.png")
            w = 1000
            h = round(w * frame.height / frame.width / 2) * 2  # 高取偶数
            frame.convert("RGB").resize((w, h)).save(out_path, "JPEG", quality=90)  # JPEG 数据，后缀 .png
            print(f"progress: {i + 1}/{total} ({100.0 * (i + 1) / total:.2f}%)  {out_path}")
        except Exception as e:
            print(f"帧 {i} 失败: {e}")
    print("转换完成！")


def main():
    debug = sys.gettrace()
    if debug:
        print("Debug模式")
        gif_path = r'C:\Users\lihehui\Desktop\test.gif'
        out_dir = r'C:\Users\lihehui\Desktop\frames'
    else:
        print("Release模式")
        gif_path = sys.argv[1]
        out_dir = sys.argv[2]
    gif2frames(gif_path, out_dir)


main()
