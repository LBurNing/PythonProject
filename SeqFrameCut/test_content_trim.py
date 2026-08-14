"""内容收缩逻辑单元测试 (python -m unittest test_content_trim)"""
import unittest

from PIL import Image

from content_trim import ALPHA_THRESHOLD, shrink_box


def make_rgba(w, h, content):
    """造图: content = (cx, cy, cw, ch, alpha) 在指定区域填不透明色, 其余透明"""
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    cx, cy, cw, ch, a = content
    px = im.load()
    for y in range(cy, cy + ch):
        for x in range(cx, cx + cw):
            px[x, y] = (200, 50, 50, a)
    return im


class TestShrinkBox(unittest.TestCase):
    def test_shrink_to_content(self):
        im = make_rgba(200, 200, (30, 40, 80, 60, 255))
        self.assertEqual(shrink_box(im, (0, 0, 200, 200)), (30, 40, 80, 60))

    def test_shrink_within_frame_box(self):
        # 用户框框住部分区域 (框比内容小或偏移)
        im = make_rgba(200, 200, (30, 40, 80, 60, 255))
        # 框: x=0..100, y=0..100 -> 内容在此框内只有 (30,40,70,60)
        self.assertEqual(shrink_box(im, (0, 0, 100, 100)), (30, 40, 70, 60))

    def test_shrink_offset_frame_box(self):
        im = make_rgba(200, 200, (30, 40, 80, 60, 255))
        # 框: x=20..120, y=30..110 -> 内容收缩到框内交集 (30,40,80,60)
        self.assertEqual(shrink_box(im, (20, 30, 120, 110)), (30, 40, 80, 60))

    def test_transparent_region_returns_none(self):
        im = make_rgba(100, 100, (0, 0, 0, 0, 255))  # 全透明
        self.assertIsNone(shrink_box(im, (0, 0, 100, 100)))

    def test_alpha_threshold(self):
        # alpha=10 < 16 视为透明, alpha=16 >= 16 视为内容
        im = make_rgba(100, 100, (10, 10, 20, 20, ALPHA_THRESHOLD - 1))
        self.assertIsNone(shrink_box(im, (0, 0, 100, 100)))
        im2 = make_rgba(100, 100, (10, 10, 20, 20, ALPHA_THRESHOLD))
        self.assertEqual(shrink_box(im2, (0, 0, 100, 100)), (10, 10, 20, 20))

    def test_rgb_image_full_frame(self):
        # 无 alpha 通道: 整框视为内容
        im = Image.new('RGB', (64, 48), (255, 255, 255))
        self.assertEqual(shrink_box(im, (5, 6, 50, 40)), (5, 6, 45, 34))

    def test_single_pixel_content(self):
        im = make_rgba(50, 50, (25, 25, 1, 1, 255))
        self.assertEqual(shrink_box(im, (0, 0, 50, 50)), (25, 25, 1, 1))


if __name__ == '__main__':
    unittest.main()
