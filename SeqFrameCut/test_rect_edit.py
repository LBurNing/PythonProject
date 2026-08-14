"""裁剪框逻辑单元测试 (python -m unittest test_rect_edit)"""
import unittest

from rect_edit import RectEdit


class TestHitTest(unittest.TestCase):
    def test_hit_regions(self):
        e = RectEdit(100, 100)          # 全图框
        self.assertEqual(e.hit_test(3, 3), 'tl')
        self.assertEqual(e.hit_test(97, 3), 'tr')
        self.assertEqual(e.hit_test(3, 97), 'bl')
        self.assertEqual(e.hit_test(97, 97), 'br')
        self.assertEqual(e.hit_test(50, 3), 't')
        self.assertEqual(e.hit_test(50, 97), 'b')
        self.assertEqual(e.hit_test(3, 50), 'l')
        self.assertEqual(e.hit_test(97, 50), 'r')
        self.assertEqual(e.hit_test(50, 50), 'move')
        self.assertIsNone(e.hit_test(150, 150))   # 框外
        self.assertIsNone(e.hit_test(50, 150))

    def test_small_rect_moves_only(self):
        e = RectEdit(100, 100)
        e.rect = [50, 50, 6, 6]         # 小于 2*margin, 退化整体移动
        self.assertEqual(e.hit_test(53, 53), 'move')
        self.assertIsNone(e.hit_test(46, 53))     # 框外


class TestMove(unittest.TestCase):
    def test_move_clamps_to_canvas(self):
        e = RectEdit(100, 100)
        e.rect = [20, 20, 30, 30]
        e.start_drag(35, 35)
        e.drag_to(135, 135)             # 拖超右下
        self.assertEqual(e.rect, [70, 70, 30, 30])
        e.start_drag(85, 85)            # 移动后框在 [70,70,30,30], 内部点为 (85,85)
        e.drag_to(-50, -50)             # 拖超左上
        self.assertEqual(e.rect, [0, 0, 30, 30])


class TestResize(unittest.TestCase):
    def test_resize_right_bottom(self):
        e = RectEdit(100, 100)
        e.rect = [10, 10, 40, 40]
        # 角命中: 右下角 (50, 50)
        e.start_drag(50, 50)
        self.assertEqual(e.hit_test(50, 50), 'br')
        e.drag_to(90, 90)
        self.assertEqual(e.rect, [10, 10, 80, 80])

    def test_resize_clamps_min_and_edge(self):
        e = RectEdit(100, 100)
        e.rect = [10, 10, 40, 40]
        e.start_drag(50, 50)            # 'br'
        e.drag_to(150, -50)             # 拖出画布: 角点钳制在画布内
        self.assertEqual(e.rect, [10, 10, 90, 4])    # 右到画布边界, 上收至最小
        e.rect = [10, 10, 40, 40]       # 重新开始
        e.start_drag(50, 50)            # 'br', 反拖
        e.drag_to(12, 12)               # 小于最小尺寸
        self.assertEqual(e.rect, [10, 10, 4, 4])     # 保持最小 4x4

    def test_resize_left_edge(self):
        e = RectEdit(100, 100)
        e.rect = [40, 10, 40, 40]
        e.start_drag(40, 30)            # 'l'
        e.drag_to(95, 30)
        self.assertEqual(e.rect, [76, 10, 4, 40])    # 左边界最多推到右边界-MIN, 宽随之收缩


class TestOriginalMapping(unittest.TestCase):
    def test_map_back_rounds(self):
        e = RectEdit(50, 50)            # 画布(显示) 50x50
        e.rect = [12, 24, 25, 13]
        self.assertEqual(e.to_original(200, 200), (48, 96, 100, 52))

    def test_map_back_clamps(self):
        e = RectEdit(50, 50)
        e.rect = [0, 0, 50, 50]         # 全图
        self.assertEqual(e.to_original(199, 99), (0, 0, 199, 99))

    def test_map_zero_canvas_falls_back_full(self):
        e = RectEdit(0, 0)
        e.rect = [0, 0, 0, 0]
        self.assertEqual(e.to_original(64, 32), (0, 0, 64, 32))


class TestCanvasResize(unittest.TestCase):
    def test_resize_canvas_keeps_ratio(self):
        e = RectEdit(100, 100)
        e.rect = [10, 10, 40, 40]
        e.resize_canvas(200, 100)       # 宽翻倍
        self.assertEqual(e.rect, [20, 10, 80, 40])

    def test_resize_canvas_from_zero(self):
        e = RectEdit(0, 0)
        e.resize_canvas(80, 60)
        self.assertEqual(e.rect, [0, 0, 80, 60])    # 初始=全图


if __name__ == '__main__':
    unittest.main()
