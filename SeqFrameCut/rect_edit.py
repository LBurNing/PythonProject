"""裁剪框矩形编辑逻辑(与 GUI 解耦, 可独立测试)。
坐标基于画布坐标系(显示缩放后的图区域); 缩放/移动时钳制在画布内, 保持最小尺寸。
拖动处理: 四角 > 四边 > 内部移动, 不命中返回 None。"""


class RectEdit:
    MIN = 4  # 最小边长(画布像素)

    def __init__(self, cw=0, ch=0):
        self.cw, self.ch = cw, ch       # 画布尺寸
        self.rect = [0, 0, cw, ch]      # [x, y, w, h]
        self._drag = None               # (handle, start_x, start_y, orig_rect)

    # ---------- 基础操作 ----------
    def reset(self):
        """框恢复为整张画布"""
        self.rect = [0, 0, self.cw, self.ch]

    def resize_canvas(self, cw, ch):
        """画布尺寸变化: 按比例换算矩形并钳制 (窗口 resize 时用)"""
        x, y, w, h = self.rect
        if self.cw > 0 and self.ch > 0:
            nx, ny = x * cw / self.cw, y * ch / self.ch
            nw, nh = w * cw / self.cw, h * ch / self.ch
            self.rect = [round(nx), round(ny), round(nw), round(nh)]
        else:
            self.rect = [0, 0, cw, ch]  # 画布首次初始化: 框 = 全图
        self.cw, self.ch = cw, ch
        self._clamp()

    def hit_test(self, px, py, margin=6):
        """返回命中区域: tl/tr/bl/br 角 > l/r/t/b 边 > move 内部 > None 框外。
        框小于 2*margin 时退化为整体移动。"""
        x, y, w, h = self.rect
        m = margin
        if w <= 2 * m or h <= 2 * m:
            return 'move' if x <= px <= x + w and y <= py <= y + h else None
        if abs(px - x) <= m and abs(py - y) <= m:
            return 'tl'
        if abs(px - (x + w)) <= m and abs(py - y) <= m:
            return 'tr'
        if abs(px - x) <= m and abs(py - (y + h)) <= m:
            return 'bl'
        if abs(px - (x + w)) <= m and abs(py - (y + h)) <= m:
            return 'br'
        if y <= py <= y + h and abs(px - x) <= m:
            return 'l'
        if y <= py <= y + h and abs(px - (x + w)) <= m:
            return 'r'
        if x <= px <= x + w and abs(py - y) <= m:
            return 't'
        if x <= px <= x + w and abs(py - (y + h)) <= m:
            return 'b'
        if x < px < x + w and y < py < y + h:
            return 'move'
        return None

    # ---------- 拖动 ----------
    def start_drag(self, px, py):
        self._drag = (self.hit_test(px, py), px, py, list(self.rect))

    def drag_to(self, px, py):
        """更新矩形(钳制在画布内/保持最小尺寸), 返回 (handle, x, y, w, h) 或 None"""
        if not self._drag:
            return None
        handle, sx, sy, (x, y, w, h) = self._drag
        if handle is None:
            return None
        MIN = self.MIN
        if handle == 'move':
            x = min(max(x + px - sx, 0), self.cw - w)
            y = min(max(y + py - sy, 0), self.ch - h)
        else:
            rx, by = x + w, y + h  # 固定对边, 拖左/上边时宽高随之收缩
            if 'l' in handle:
                x = min(max(px, 0), rx - MIN)
                w = rx - x
            if 'r' in handle:
                w = min(max(px - x, MIN), self.cw - x)
            if 't' in handle:
                y = min(max(py, 0), by - MIN)
                h = by - y
            if 'b' in handle:
                h = min(max(py - y, MIN), self.ch - y)
        self.rect = [x, y, w, h]
        return (handle, x, y, w, h)

    def end_drag(self):
        self._drag = None

    # ---------- 坐标映射 ----------
    def to_original(self, orig_w, orig_h):
        """映射回原图整数坐标 (x, y, w, h): 四舍五入并钳制到原图内"""
        if self.cw <= 0 or self.ch <= 0:
            return (0, 0, orig_w, orig_h)
        x, y, w, h = self.rect
        ox = round(x * orig_w / self.cw)
        oy = round(y * orig_h / self.ch)
        ow = min(round(w * orig_w / self.cw), orig_w - ox)
        oh = min(round(h * orig_h / self.ch), orig_h - oy)
        return (ox, oy, max(ow, 1), max(oh, 1))

    # ---------- 内部 ----------
    def _clamp(self):
        x, y, w, h = self.rect
        cw, ch, m = self.cw, self.ch, self.MIN
        w = min(max(w, m), cw)
        h = min(max(h, m), ch)
        x = min(max(x, 0), cw - w)
        y = min(max(y, 0), ch - h)
        self.rect = [x, y, w, h]
