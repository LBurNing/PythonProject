"""renderer 单元测试:合成地图验证绘制/混合/分块/输出。"""

import json
import struct
import zlib
from pathlib import Path

import numpy as np

from map_py.map_parser import CELL_HEIGHT, CELL_WIDTH, MapReader
from map_py.renderer import RenderConfig, Renderer
from map_py.wil_library import MLibrary

# ---------------- 合成资源 ----------------

PALETTE_FIXED = bytes(range(0, 256, 16)) * 16      # 16 色调色板索引


def make_wzl(tmp_path, name, w, h, color, px=0, py=0):
    """单图 wzl:w*h 全色(color 是 8bit 调色板索引),图头偏移 (px, py)。
    zlib 压缩存储(含行补位),与真实 wzl 一致。"""
    row_stride = ((w * 8 + 31) >> 5) * 4
    payload = (bytes([color]) * row_stride) * h
    compressed = zlib.compress(payload)
    wzl = b"\x00" * 64
    wzl += bytes([4]) + b"\x00" * 3
    wzl += struct.pack("<hhhh", w, h, px, py) + struct.pack("<i", len(compressed)) + compressed
    wzx = b"\x00" * 48 + struct.pack("<i", 64)
    (tmp_path / f"{name}.wzx").write_bytes(wzx)
    (tmp_path / f"{name}.wzl").write_bytes(wzl)
    return str(tmp_path / name)


def make_map(tmp_path, w, h, cells_bytes):
    """Type2 地图:52 头 + 每格 14 字节。"""
    return (tmp_path / "m.map").write_bytes(
        struct.pack("<hh", w, h) + b"\x00" * 48 + cells_bytes)


def t2(back_img, mid_img=0, front_img=0, back_idx=300, mid_idx=310,
       front_idx=320, door_off=0, anim=0):
    """Type2 单格 14 字节;anim = FrontAnimationFrame(bit7=blend)。"""
    return struct.pack("<hhhBBBBBBBB", back_img, mid_img, front_img,
                       0, door_off, anim, 0, front_idx - 120, 0,
                       back_idx - 100, mid_idx - 110)


def make_reader(tmp_path, w, h, cell_bytes):
    make_map(tmp_path, w, h, cell_bytes)
    return MapReader(tmp_path / "m.map")


def make_libs(tmp_path):
    # 槽位 300=地面, 310=中层, 320=前景;每槽一张 2x2 纯色瓦片
    libs = {
        300: MLibrary(make_wzl(tmp_path, "Tiles201", 2, 2, 1)),
        310: MLibrary(make_wzl(tmp_path, "SmTiles201", 2, 2, 2)),
        320: MLibrary(make_wzl(tmp_path, "Objects201", 2, 2, 3)),
    }
    return libs


# ---------------- 单图路径 ----------------

def test_render_single_tile(tmp_path):
    # 2x2 格地图:每格 2x2 瓦片 → 大图 96x64
    cell = t2(back_img=1)                      # back_image=1 → index 0
    reader = make_reader(tmp_path, 2, 2, cell * 4)
    libs = make_libs(tmp_path)
    out = tmp_path / "out"
    Renderer(reader, libs, RenderConfig(out_root=out, img_format="png",
                                        export_anim=True)).run()

    img_path = out / "m" / "m.png"
    assert img_path.is_file()
    from PIL import Image
    img = np.array(Image.open(img_path).convert("RGBA"))
    assert img.shape == (2 * CELL_HEIGHT, 2 * CELL_WIDTH, 4)

    # (0,0) 格:back_index=300 → 槽 300 的 2x2 瓦片正立画在格左上角(图像顶部)
    from map_py.palette import PALETTE
    np.testing.assert_array_equal(img[0, 0], PALETTE[1])
    np.testing.assert_array_equal(img[0, 1], PALETTE[1])
    np.testing.assert_array_equal(img[0, 2], [0, 0, 0, 0])   # 瓦片外透明
    # 地面只画偶数格:(1,0) 格空白
    np.testing.assert_array_equal(img[0, CELL_WIDTH], [0, 0, 0, 0])
    # JSON(animationDataList,与图片同目录)
    info = json.loads((out / "m" / "m_anim.json").read_text("utf-8"))
    assert info == []


def test_render_alpha_blend(tmp_path):
    # 中层不透明瓦片叠在地面上:颜色 = 中层色(C# 预乘混合)
    cell = t2(back_img=1, mid_img=1)
    reader = make_reader(tmp_path, 1, 1, cell)
    libs = make_libs(tmp_path)
    out = tmp_path / "out"
    Renderer(reader, libs, RenderConfig(out_root=out, img_format="png")).run()
    from PIL import Image
    from map_py.palette import PALETTE
    img = np.array(Image.open(out / "m" / "m.png").convert("RGBA"))
    # 2x2 瓦片非标准尺寸 → 大物体底部对齐(dy=30):中层画在底部,地面(dy=0)画在顶部
    np.testing.assert_array_equal(img[0, 0], PALETTE[1])                   # 地面
    np.testing.assert_array_equal(img[CELL_HEIGHT - 2, 0], PALETTE[2])     # 中层


def test_render_blend_animation(tmp_path):
    # blend 动画大物体:C# 规则 — 记录 animationDataList + skip 不画;
    # 动画帧图导出到 Animation/ 目录(50000+k.png + Placements txt)
    cell = t2(back_img=0, front_img=1, front_idx=320, anim=0x81)   # blend + 1 帧动画
    reader = make_reader(tmp_path, 1, 1, cell)
    libs = {320: MLibrary(make_wzl(tmp_path, "Objects201", 6, 6, 3, py=-3))}
    out = tmp_path / "out"
    Renderer(reader, libs, RenderConfig(out_root=out, img_format="png",
                                        export_anim=True)).run()
    from PIL import Image
    img = np.array(Image.open(out / "m" / "m.png").convert("RGBA"))
    assert not img.any()                        # blend 动画瓦片不画(全透明)

    # JSON:animationDataList(槽 320>199 → drawY-s.Height=(0+1)*32-6=26)
    info = json.loads((out / "m" / "m_anim.json").read_text("utf-8"))
    assert info == [{"animationName": "000000", "x": 0, "y": 26}]

    # 帧图:1 帧(50000.png = 资源库 img 0),该库只有 1 张 → 无 50001
    anim = out / "m" / "anims" / "m_000000"
    assert (anim / "50000.png").is_file()
    assert not (anim / "50001.png").exists()    # img=1 越界,无帧
    # txt:图头 px/py 两行
    assert (anim / "Placements" / "50000.txt").read_text("utf-8") == "0\n-3"


def test_render_json_paths(tmp_path):
    # 输出目录结构与 C# 一致(大小写 Maps/map/tiles)
    cell = t2(back_img=1)
    reader = make_reader(tmp_path, 1, 1, cell)
    libs = make_libs(tmp_path)
    out = tmp_path / "out"
    Renderer(reader, libs, RenderConfig(out_root=out, img_format="png",
                                        export_anim=True)).run()
    assert (out / "m" / "m.png").is_file()
    assert (out / "m" / "m_anim.json").is_file()


# ---------------- 分块路径 ----------------

def test_render_blocks(tmp_path):
    # 强制分块(>16384):合成大图 1x500 格 → 48 x 16000 像素(高>16384 不足,
    # 用自定义 texture_max_size=100 触发分块)
    cell = t2(back_img=1)
    reader = make_reader(tmp_path, 30, 1, cell * 30)     # 1440x32
    libs = make_libs(tmp_path)
    out = tmp_path / "out"
    cfg = RenderConfig(out_root=out, texture_max_size=200, img_format="png")
    Renderer(reader, libs, cfg).run()

    # bs_x = 1440//10 = 144, bs_y = 32//10 = 3;bx=10, by=11
    from PIL import Image
    tiles = sorted(out.glob("m/*.png"))
    assert len(tiles) == 11 * 10
    # 瓦片正立画在顶部(dy=0 → 块 0_0)
    from map_py.palette import PALETTE
    img = np.array(Image.open(out / "m" / "0_0.png").convert("RGBA"))
    np.testing.assert_array_equal(img[0, 0], PALETTE[1])
    # 底行块覆盖全局 y 30..32,瓦片在顶部(y 0..1) → 底块应全透明
    last = np.array(Image.open(out / "m" / "10_0.png").convert("RGBA"))
    assert last.shape[0] == 3
    np.testing.assert_array_equal(last[0, 0], [0, 0, 0, 0])
    np.testing.assert_array_equal(last[2, 0], [0, 0, 0, 0])
