"""涂抹擦除逻辑单元测试 (python -m unittest test_eraser)"""
import unittest

from PIL import Image

from eraser import erase_circles, map_circles


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


class TestEraseCircles(unittest.TestCase):
    def setUp(self):
        self.im = Image.new('RGBA', (100, 100), (255, 0, 0, 255))  # 全红不透明

    def test_erase_center_circle(self):
        out = erase_circles(self.im, [(50, 50, 10)])
        self.assertEqual(out.getpixel((50, 50))[3], 0)      # 圆心透明
        self.assertEqual(out.getpixel((50, 50)), (0, 0, 0, 0))
        self.assertEqual(out.getpixel((0, 0)), (255, 0, 0, 255))  # 圆外不变
        self.assertEqual(out.getpixel((50, 65)), (255, 0, 0, 255))  # 圆外 (r=10)

    def test_erase_two_circles(self):
        out = erase_circles(self.im, [(20, 20, 5), (80, 80, 5)])
        self.assertEqual(out.getpixel((20, 20))[3], 0)
        self.assertEqual(out.getpixel((80, 80))[3], 0)
        self.assertEqual(out.getpixel((50, 50)), (255, 0, 0, 255))

    def test_erase_does_not_mutate_input(self):
        erase_circles(self.im, [(50, 50, 10)])
        self.assertEqual(self.im.getpixel((50, 50)), (255, 0, 0, 255))  # 原图不变

    def test_rgb_input_converted(self):
        rgb = Image.new('RGB', (50, 50), (0, 0, 255))
        out = erase_circles(rgb, [(25, 25, 5)])
        self.assertEqual(out.mode, 'RGBA')
        self.assertEqual(out.getpixel((25, 25)), (0, 0, 0, 0))
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 255, 255))


if __name__ == '__main__':
    unittest.main()
