"""涂抹效果逻辑(与 GUI 解耦, 可独立测试)。
涂抹区域用归一化圆列表表示 (nx, ny, nr): 与帧尺寸无关, 各帧尺寸不同也能正确映射。
效果: radius <= 0 区域全透明; radius > 0 区域高斯虚化。"""

from PIL import Image, ImageDraw, ImageFilter


def map_circles(circles, w, h):
    """归一化圆 (nx, ny, nr) -> 原图坐标圆 [(cx, cy, r)], 整数化, 半径最小 1"""
    out = []
    for nx, ny, nr in circles:
        cx = round(nx * w)
        cy = round(ny * h)
        r = max(1, round(nr * min(w, h)))
        out.append((cx, cy, r))
    return out


def apply_effect(im, circles, radius):
    """涂抹区域应用效果: radius <= 0 全透明, radius > 0 高斯虚化。
    虚化只处理圆区域包围盒 (不整图模糊, 大图也快)。返回新图, 不修改原图。"""
    im = im.convert('RGBA')
    circles_px = map_circles(circles, im.width, im.height) if circles else []
    if not circles_px:
        return im
    if radius <= 0:
        # 全透明: 直接画透明圆
        d = ImageDraw.Draw(im)
        for cx, cy, r in circles_px:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 0))
        return im
    # 虚化: 求圆区域包围盒并钳制到图内
    x0 = max(0, min(cx - r for cx, cy, r in circles_px))
    y0 = max(0, min(cy - r for cx, cy, r in circles_px))
    x1 = min(im.width, max(cx + r for cx, cy, r in circles_px))
    y1 = min(im.height, max(cy + r for cx, cy, r in circles_px))
    if x1 <= x0 or y1 <= y0:
        return im
    bw, bh = x1 - x0, y1 - y0
    sub = im.crop((x0, y0, x1, y1))
    sub_blur = sub.filter(ImageFilter.GaussianBlur(radius))
    # 蒙版: 圆内白色, 圆外黑色 (只把圆区域贴回模糊图)
    mask = Image.new('L', (bw, bh), 0)
    d = ImageDraw.Draw(mask)
    for cx, cy, r in circles_px:
        d.ellipse((cx - r - x0, cy - r - y0, cx + r - x0, cy + r - y0), fill=255)
    im.paste(sub_blur, (x0, y0), mask)
    return im
