# -*- coding: utf-8 -*-
"""羽化擦除单元测试: 归一化映射 / 硬边 / 软边渐变 / 累积透明 / 包围盒钳制 / 非 RGBA"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
from eraser import apply_soft_erase, map_circles

W, H = 200, 100


def make_image(mode='RGBA'):
    return Image.new(mode, (W, H), (255, 0, 0, 255) if mode == 'RGBA' else (255, 0, 0))


def test_map_circles():
    out = map_circles([(0.5, 0.5, 0.1)], W, H)
    assert out == [(100, 50, 10)], out
    out = map_circles([(0, 0, 0.0001)], W, H)
    assert out[0][2] == 1, out  # 半径最小 1
    print('map_circles 通过')


def test_hard_edge():
    im = apply_soft_erase(make_image(), [(100, 50, 10)], 0.0)
    a = im.getchannel('A')
    assert a.getpixel((100, 50)) == 0, a.getpixel((100, 50))   # 圆心全透明
    assert a.getpixel((100, 41)) == 0                          # 核内透明
    assert a.getpixel((100, 25)) == 255                        # 圆外不变
    print('硬边 (feather=0) 通过')


def test_soft_edge():
    im = apply_soft_erase(make_image(), [(100, 50, 10)], 0.5)
    a = im.getchannel('A')
    assert a.getpixel((100, 50)) == 0            # 圆心全透明
    assert a.getpixel((100, 46)) == 0            # 硬核 (r*0.5=5) 内透明
    assert a.getpixel((100, 10)) == 255          # 远离圆处不变
    edge = a.getpixel((100, 56))                 # 过渡带: 距离 6, 在硬核 5 与圆边界 10 之间
    assert 0 < edge < 255, edge                  # 边缘渐变 (非硬边)
    print('软边 (feather=0.5) 通过')


def test_accumulate():
    im = apply_soft_erase(make_image(), [(100, 50, 10)], 0.5)
    a1 = im.getchannel('A').getpixel((100, 56))
    im2 = apply_soft_erase(im, [(100, 50, 10)], 0.5)   # 同位置再刷一笔
    a2 = im2.getchannel('A').getpixel((100, 56))
    assert a2 < a1, (a1, a2)   # 累积更透明
    assert a2 > 0              # 过渡带未完全透明 (a1 * inv/255)
    print('累积透明通过:', a1, '->', a2)


def test_edge_clamp():
    circles_px = map_circles([(0.05, 0.5, 0.1)], W, H)  # 圆心 (10,50), 贴左边缘
    im = apply_soft_erase(make_image(), circles_px, 0.0)
    a = im.getchannel('A')
    assert a.getpixel((0, 50)) == 0      # 贴边裁剪后仍透明
    assert a.getpixel((30, 50)) == 255   # 圆外不变
    assert a.size == (W, H)              # 尺寸不变
    print('包围盒钳制通过')


def test_non_rgba_input():
    im = apply_soft_erase(make_image('RGB'), [(100, 50, 10)], 0.0)
    assert im.mode == 'RGBA'
    assert im.getchannel('A').getpixel((100, 50)) == 0
    print('非 RGBA 输入通过')


if __name__ == '__main__':
    test_map_circles()
    test_hard_edge()
    test_soft_edge()
    test_accumulate()
    test_edge_clamp()
    test_non_rgba_input()
    print('test_eraser 全部通过')
