"""涂抹擦除逻辑(与 GUI 解耦, 可独立测试)。
擦除区域用归一化圆列表表示 (nx, ny, nr): 与帧尺寸无关, 各帧尺寸不同也能正确映射。"""

from PIL import Image, ImageDraw


def map_circles(circles, w, h):
    """归一化圆 (nx, ny, nr) -> 原图坐标圆 [(cx, cy, r)], 整数化, 半径最小 1"""
    out = []
    for nx, ny, nr in circles:
        cx = round(nx * w)
        cy = round(ny * h)
        r = max(1, round(nr * min(w, h)))
        out.append((cx, cy, r))
    return out


def erase_circles(im, circles):
    """在图上把圆区域画为全透明 (RGBA), 其余像素不变, 返回新图 (不修改原图)"""
    im = im.convert('RGBA')
    d = ImageDraw.Draw(im)
    for cx, cy, r in circles:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 0))
    return im
