"""羽化擦除逻辑(与 GUI 解耦, 可独立测试)。
擦除区域用归一化圆列表表示 (nx, ny, nr): 与帧尺寸无关, 各帧尺寸不同也能正确映射,
导出时所有帧统一应用同一批圆。
效果: 每笔硬核内全透明, 边缘 smoothstep 缓入缓出 (软边), 多次涂抹累积更透明。
性能: 全部圆的保留因子先合并到一张浮点蒙版 (每笔只算自身子区域), 最后一次性写回 alpha,
避免逐笔的 PIL 往返开销 (100 帧 512x512/20 笔约 7s -> ~1.5s)。"""

import numpy as np
from PIL import Image


def map_circles(circles, w, h):
    """归一化圆 (nx, ny, nr) -> 原图坐标圆 [(cx, cy, r)], 整数化, 半径最小 1"""
    out = []
    for nx, ny, nr in circles:
        cx = round(nx * w)
        cy = round(ny * h)
        r = max(1, round(nr * min(w, h)))
        out.append((cx, cy, r))
    return out


def apply_soft_erase(im, circles_px, feather):
    """羽化擦除: 逐笔累积透明, 其余像素不变, 返回新图 (不修改原图)。
    circles_px: 原图坐标圆 [(cx, cy, r), ...]; feather: 羽化比例 0-1 (相对半径, 0=硬边)。
    保留因子 = 硬核内 0 (全透明), 硬核外 smoothstep 缓入缓出过渡到 1 (不透明),
    各笔因子相乘 = 多次涂抹累积透明; 与原 alpha multiply 后写回。"""
    im = im.convert('RGBA')
    if not circles_px:
        return im
    w, h = im.size
    # 全部圆的并集包围盒
    x0 = max(0, min(cx - r for cx, cy, r in circles_px))
    y0 = max(0, min(cy - r for cx, cy, r in circles_px))
    x1 = min(w, max(cx + r + 1 for cx, cy, r in circles_px))
    y1 = min(h, max(cy + r + 1 for cx, cy, r in circles_px))
    if x1 <= x0 or y1 <= y0:
        return im
    bw, bh = x1 - x0, y1 - y0
    factor = np.ones((bh, bw), dtype=np.float32)
    # 坐标网格预分配一次 (并集区域), 每笔用切片视图, 避免逐笔 mgrid 分配开销
    Y, X = np.mgrid[0:bh, 0:bw]
    for cx, cy, r in circles_px:
        # 该圆的子区域 (在并集内的局部偏移)
        bx0 = max(x0, cx - r) - x0
        by0 = max(y0, cy - r) - y0
        bx1 = min(x1, cx + r + 1) - x0
        by1 = min(y1, cy + r + 1) - y0
        if bx1 <= bx0 or by1 <= by0:
            continue
        cxr, cyr = cx - x0 - bx0, cy - y0 - by0   # 圆心在子区域内的局部坐标
        d = np.sqrt((X[by0:by1, bx0:bx1] - cxr) ** 2 + (Y[by0:by1, bx0:bx1] - cyr) ** 2)
        if feather <= 0:
            keep = np.where(d <= r, 0.0, 1.0).astype(np.float32)  # 硬边: 圆内透明
        else:
            hard_r = max(0.0, r * (1 - feather))          # 硬核半径 (内全透明)
            tw = max(1e-6, r - hard_r)                    # 过渡带宽度
            t = np.clip((d - hard_r) / tw, 0.0, 1.0)
            keep = (t * t * (3.0 - 2.0 * t)).astype(np.float32)  # smoothstep
        factor[by0:by1, bx0:bx1] *= keep                  # 累积透明
    alpha = im.getchannel('A')
    region = np.asarray(alpha.crop((x0, y0, x1, y1)), dtype=np.float32) * factor
    alpha.paste(Image.fromarray(region.astype('uint8'), 'L'), (x0, y0))
    im.putalpha(alpha)
    return im
