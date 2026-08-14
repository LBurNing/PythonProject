"""内容收缩逻辑(与 GUI 解耦, 可独立测试)。
拆切时把裁剪框收缩到框内真实内容(非透明区域)的实际范围, 去掉多余透明边。"""

ALPHA_THRESHOLD = 16  # alpha < 阈值 视为透明 (滤掉边缘半透明噪点)


def shrink_box(im, box, threshold=ALPHA_THRESHOLD):
    """返回框内非透明内容的最小范围 (x, y, w, h, 原图坐标)。
    框内全透明返回 None。无 alpha 通道的图整框视为内容。"""
    x0, y0, x1, y1 = box
    region = im.crop((x0, y0, x1, y1)).convert('RGBA')
    # alpha 阈值化后求非零边界: 半透明噪点 (a < threshold) 不算内容
    alpha = region.getchannel('A').point(lambda a: 255 if a >= threshold else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        return None
    bx, by, bx1, by1 = bbox
    return (x0 + bx, y0 + by, bx1 - bx, by1 - by)
