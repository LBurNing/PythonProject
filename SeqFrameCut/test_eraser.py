"""涂抹效果逻辑单元测试 (python -m unittest test_eraser)"""
import unittest

from PIL import Image

from eraser import apply_effect, map_circles


class TestMapCircles(unittest.TestCase):
    def test_map_normalized_to_pixel(self):
        # 归一化 (0.25, 0.5, 0.1) 于 200x100 图 -> (50, 50, 10) (半径按 min 边长)
        self.assertEqual(map_circles([(0.25, 0.5, 0.1)], 200, 100), [(50, 50, 10)])

    def test_radius_at_least_1(self):
        self.assertEqual(map_circles([(0.5, 0.5, 0.0)], 100, 100), [(50, 50, 1)])

    def test_multi_circles(self):
        cs = map_circles([(0.0, 0.0, 0.1), (1.0, 1.0, 0.2)], 100, 100)
        self.assertEqual(cs, [(0, 0, 10), (100, 100, 20)])

    def test_rounding(self):
        cs = map_circles([(0.333, 0.667, 0.05)], 100, 100)
        self.assertEqual(cs, [(33, 67, 5)])


class TestEraseToTransparent(unittest.TestCase):
    """radius <= 0: 圆区域全透明"""

    def setUp(self):
        self.im = Image.new('RGBA', (100, 100), (255, 0, 0, 255))  # 全红不透明

    def test_erase_center_circle(self):
        out = apply_effect(self.im, [(0.5, 0.5, 0.1)], 0)
        self.assertEqual(out.getpixel((50, 50)), (0, 0, 0, 0))      # 圆心透明
        self.assertEqual(out.getpixel((0, 0)), (255, 0, 0, 255))    # 圆外不变
        self.assertEqual(out.getpixel((50, 65)), (255, 0, 0, 255))  # 圆外 (r=10)

    def test_does_not_mutate_input(self):
        apply_effect(self.im, [(0.5, 0.5, 0.1)], 0)
        self.assertEqual(self.im.getpixel((50, 50)), (255, 0, 0, 255))

    def test_rgb_input_converted(self):
        rgb = Image.new('RGB', (50, 50), (0, 0, 255))
        out = apply_effect(rgb, [(0.5, 0.5, 0.1)], 0)
        self.assertEqual(out.mode, 'RGBA')
        self.assertEqual(out.getpixel((25, 25)), (0, 0, 0, 0))
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 255, 255))


class TestBlurEffect(unittest.TestCase):
    """radius > 0: 圆区域高斯虚化"""

    def setUp(self):
        # 左半红右半蓝, 边界清晰: 虚化后边界处像素应混合
        im = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        px = im.load()
        for y in range(100):
            for x in range(100):
                px[x, y] = (255, 0, 0, 255) if x < 50 else (0, 0, 255, 255)
        self.im = im

    def test_blur_mixes_boundary(self):
        out = apply_effect(self.im, [(0.5, 0.5, 0.1)], 8)  # 圆在红蓝边界上
        # 圆心 (50,50) 处: 红蓝混合 -> 既不是纯红也不是纯蓝
        px = out.getpixel((50, 50))
        self.assertNotEqual(px[:3], (255, 0, 0))
        self.assertNotEqual(px[:3], (0, 0, 255))
        self.assertEqual(px[3], 255)
        # 圆外远处保持纯色
        self.assertEqual(out.getpixel((10, 50)), (255, 0, 0, 255))
        self.assertEqual(out.getpixel((90, 50)), (0, 0, 255, 255))

    def test_blur_small_radius_close_to_original(self):
        out = apply_effect(self.im, [(0.5, 0.5, 0.1)], 1)
        # 距边界远的点基本不变
        self.assertEqual(out.getpixel((10, 50)), (255, 0, 0, 255))
        self.assertEqual(out.getpixel((90, 50)), (0, 0, 255, 255))

    def test_blur_outside_unchanged(self):
        out = apply_effect(self.im, [(0.5, 0.5, 0.1)], 8)
        self.assertEqual(out.getpixel((10, 10)), (255, 0, 0, 255))
        self.assertEqual(out.getpixel((90, 90)), (0, 0, 255, 255))

    def test_empty_circles_returns_copy(self):
        out = apply_effect(self.im, [], 8)
        self.assertEqual(out.getpixel((50, 50)), self.im.getpixel((50, 50)))

    def test_circle_at_edge_clamps(self):
        # 圆贴图边缘: 包围盒钳制不越界
        im = Image.new('RGBA', (50, 50), (10, 20, 30, 255))
        out = apply_effect(im, [(0.0, 0.0, 0.3)], 5)  # 圆心在 (0,0), 半径 15
        self.assertEqual(out.size, (50, 50))
        # 圆心周围应被虚化 (仍为 alpha 255)
        self.assertEqual(out.getpixel((0, 0))[3], 255)


if __name__ == '__main__':
    unittest.main()
