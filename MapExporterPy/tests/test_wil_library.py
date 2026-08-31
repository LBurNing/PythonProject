"""wil_library 单元测试:合成 wzl/wzx 验证解码各分支。"""

import struct
import zlib

import numpy as np

from map_py.palette import PALETTE
from map_py.wil_library import MLibrary, WilLibrary, decode_image_data
from main import scan_libraries


def make_wzl_files(tmp_path, images, name="test"):
    """images: list[(is16bit, w, h, payload, compressed=False)]
    compressed=True 时 nSize=len(payload)(zlib 流);False 时 nSize=0(裸数据)。
    写入 {name}.wzx/.wzl,返回 stem。"""
    offsets = []
    wzl = b"\x00" * 64                       # 真实 wzl 的 64 字节文件头(首图偏移从 64 起)
    for is16, w, h, payload, *rest in images:
        compressed = rest[0] if rest else False
        offsets.append(len(wzl))
        header = bytes([5 if is16 else 4]) + b"\x00" * 3
        header += struct.pack("<hhhh", w, h, 0, 0)
        header += struct.pack("<i", len(payload) if compressed else 0)
        wzl += header + payload
    wzx = b"\x00" * 48
    for off in offsets:
        wzx += struct.pack("<i", off)
    (tmp_path / f"{name}.wzx").write_bytes(wzx)
    (tmp_path / f"{name}.wzl").write_bytes(wzl)
    return str(tmp_path / name)


# ---------------- decode_image_data ----------------

def test_decode_8bit_palette():
    out = decode_image_data(bytes([1, 5]), 2, 1, False)
    assert out.shape == (1, 2, 4)
    np.testing.assert_array_equal(out[0, 0], PALETTE[1])
    np.testing.assert_array_equal(out[0, 1], PALETTE[5])


def test_decode_16bit_no_alpha():
    # 0xF800 → r=248, g=0, b=0;无 alpha 平面 → a=255
    out = decode_image_data(struct.pack("<H", 0xF800), 1, 1, True)
    np.testing.assert_array_equal(out[0, 0], [248, 0, 0, 255])


def test_decode_16bit_black_is_transparent():
    out = decode_image_data(struct.pack("<H", 0x0000), 1, 1, True)
    np.testing.assert_array_equal(out[0, 0], [0, 0, 0, 0])


def test_decode_16bit_alpha_plane():
    # w=2 h=1:2 像素 RGB565(4 字节)+ alpha 平面 1 字节 = 5 字节 → len*2==hw*5 命中
    rgb = struct.pack("<HH", 0x07E0, 0x001F)     # 绿 / 蓝
    alpha_byte = 0xA0                             # 像素0(偶)=高4位 0xA×17=170;像素1(奇)=低4位 0
    out = decode_image_data(rgb + bytes([alpha_byte]), 2, 1, True)
    np.testing.assert_array_equal(out[0, 0], [0, 252, 0, 170])
    np.testing.assert_array_equal(out[0, 1], [0, 0, 248, 0])


def test_decode_row_stride_16bit():
    # w=3 h=2,16bit:每行 6 字节 + 2 字节补位(对齐到 8)
    row = struct.pack("<HHH", 0xF800, 0x07E0, 0x001F) + b"\xAA\xBB"   # 6+2
    out = decode_image_data(row * 2, 3, 2, True)
    assert out.shape == (2, 3, 4)
    np.testing.assert_array_equal(out[1, 0], [248, 0, 0, 255])   # 行序自下而上:最后写 top
    np.testing.assert_array_equal(out[1, 1], [0, 252, 0, 255])
    np.testing.assert_array_equal(out[1, 2], [0, 0, 248, 255])
    np.testing.assert_array_equal(out[0, 0], [248, 0, 0, 255])


def test_decode_row_stride_8bit():
    # w=3 h=1,8bit:每行 3 字节 + 1 字节补位(对齐到 4)
    out = decode_image_data(bytes([1, 2, 3, 0xEE]), 3, 1, False)
    np.testing.assert_array_equal(out[0, 0], PALETTE[1])
    np.testing.assert_array_equal(out[0, 2], PALETTE[3])


def test_decode_truncated_row_stays_transparent():
    # 行数据不足时剩余行保持透明(异常文件容错)
    out = decode_image_data(struct.pack("<H", 0xF800), 1, 3, True)
    np.testing.assert_array_equal(out[2, 0], [248, 0, 0, 255])
    np.testing.assert_array_equal(out[1, 0], [0, 0, 0, 0])


# ---------------- MLibrary ----------------

def test_library_8bit_and_zlib(tmp_path):
    raw = bytes([3, 7, 12, 5])
    stem = make_wzl_files(tmp_path, [(False, 4, 1, zlib.compress(raw), True)])
    lib = MLibrary(stem)
    assert lib.count == 1
    assert lib.get_size(0) == (4, 1)
    img = lib.get_image(0)
    np.testing.assert_array_equal(img[0, 0], PALETTE[3])
    np.testing.assert_array_equal(img[0, 2], PALETTE[12])
    lib.close()


def test_library_raw_uncpompressed(tmp_path):
    stem = make_wzl_files(tmp_path, [(True, 2, 2, struct.pack("<HHHH", 0x001F, 0, 0, 0))])
    lib = MLibrary(stem)
    img = lib.get_image(0)
    np.testing.assert_array_equal(img[1, 0], [0, 0, 248, 255])
    lib.close()


def test_library_empty_offset_zero(tmp_path):
    # 索引 0 的图偏移为 0 = 空图(真实 Objects222 里有 32 张这样的空图)
    wzl = b"\x00" * 64
    wzl += bytes([4]) + b"\x00" * 3 + struct.pack("<hhhh", 4, 1, 0, 0)
    wzl += struct.pack("<i", 0) + b"\x01\x02\x03\x04"     # nSize=0 裸数据
    wzx = b"\x00" * 48 + struct.pack("<i", 0) + struct.pack("<i", 64)
    (tmp_path / "empty.wzx").write_bytes(wzx)
    (tmp_path / "empty.wzl").write_bytes(wzl)
    lib = MLibrary(str(tmp_path / "empty"))
    assert lib.get_size(0) is None
    assert lib.get_image(0) is None
    assert lib.get_size(1) == (4, 1)        # 正常图不受影响
    lib.close()


def test_library_index_out_of_range(tmp_path):
    stem = make_wzl_files(tmp_path, [(False, 1, 1, b"\x01")])
    lib = MLibrary(stem)
    assert lib.get_size(-1) is None
    assert lib.get_size(5) is None
    assert lib.get_image(5) is None
    lib.close()


def test_library_missing_wzx(tmp_path):
    lib = MLibrary(str(tmp_path / "nope"))
    assert lib.count == 0
    lib.close()


def test_library_cache(tmp_path):
    stem = make_wzl_files(tmp_path, [(False, 4, 1, b"\x05\x05\x05\x05")])
    lib = MLibrary(stem)
    img1 = lib.get_image(0)
    img2 = lib.get_image(0)
    assert img1 is img2                       # 同一缓存对象
    lib.clear_cache()
    img3 = lib.get_image(0)
    assert img3 is not img1
    lib.close()


def test_library_multi_image_wzx_index(tmp_path):
    # 3 张图,验证 wzx 偏移索引正确(第 2 张偏移 = 第 1 张头+数据)
    raw1 = bytes([1, 2, 3, 4])
    raw2 = zlib.compress(bytes([4, 5, 6, 7]))
    raw3 = bytes([6, 7, 8, 9])
    stem = make_wzl_files(tmp_path, [
        (False, 4, 1, raw1),
        (False, 4, 1, raw2, True),
        (False, 4, 1, raw3),
    ])
    lib = MLibrary(stem)
    assert lib.count == 3
    np.testing.assert_array_equal(lib.get_image(0)[0, 0], PALETTE[1])
    np.testing.assert_array_equal(lib.get_image(1)[0, 0], PALETTE[4])
    np.testing.assert_array_equal(lib.get_image(2)[0, 0], PALETTE[6])
    lib.close()


def test_library_small_image_skipped(tmp_path):
    # W*H < 4 → 不创建纹理
    stem = make_wzl_files(tmp_path, [(False, 1, 2, bytes([1, 2]))])
    lib = MLibrary(stem)
    assert lib.get_size(0) == (1, 2)
    assert lib.get_image(0) is None
    lib.close()


# ---------------- 24bit BGR 格式 ----------------

def test_decode_24bit_bgr():
    # 2x2 像素,24bit BGR,行序自下而上(数据第一段 = 底部行)
    raw = bytes([0, 0, 255,      # 底部行左: B=0 G=0 R=255 → (255,0,0) 红
                 255, 0, 0,      # 底部行右: B=255 G=0 R=0 → (0,0,255) 蓝
                 0, 255, 0,      # 顶部行左: B=0 G=255 R=0 → (0,255,0) 绿
                 0, 0, 0])       # 顶部行右: 黑 → 透明
    out = decode_image_data(raw, 2, 2, False, is24bit=True)
    assert out.shape == (2, 2, 4)
    np.testing.assert_array_equal(out[1, 0], [255, 0, 0, 255])   # 底部行
    np.testing.assert_array_equal(out[1, 1], [0, 0, 255, 255])
    np.testing.assert_array_equal(out[0, 0], [0, 255, 0, 255])   # 顶部行
    np.testing.assert_array_equal(out[0, 1], [0, 0, 0, 255])     # 黑像素不透明


def test_library_get_pxpy(tmp_path):
    # 图头 X/Y 绘制偏移字段(官方引擎 blend 瓦片定位用)
    wzl = b"\x00" * 64
    wzl += bytes([6]) + b"\x00" * 3 + struct.pack("<hhhh", 2, 2, 3, -7)
    wzl += struct.pack("<i", 0) + b"\x00" * 12
    wzx = b"\x00" * 48 + struct.pack("<i", 64)
    (tmp_path / "px.wzx").write_bytes(wzx)
    (tmp_path / "px.wzl").write_bytes(wzl)
    lib = MLibrary(str(tmp_path / "px"))
    assert lib.get_pxpy(0) == (3, -7)
    assert lib.get_pxpy(5) == (0, 0)          # 越界 → (0,0)
    assert lib.get_size(0) == (2, 2)          # 尺寸不受影响
    lib.close()


def test_library_24bit(tmp_path):
    # wzl 单图 24bit:头 bo16bit=6,数据 = w*h*3
    payload = bytes([0, 0, 255] * 2 + [0, 255, 0] * 2)   # 2x2: 底行红, 顶行绿(12 字节)
    wzl = b"\x00" * 64
    wzl += bytes([6]) + b"\x00" * 3 + struct.pack("<hhhh", 2, 2, 0, 0)
    wzl += struct.pack("<i", 0) + payload
    wzx = b"\x00" * 48 + struct.pack("<i", 64)
    (tmp_path / "t24.wzx").write_bytes(wzx)
    (tmp_path / "t24.wzl").write_bytes(wzl)
    lib = MLibrary(str(tmp_path / "t24"))
    assert lib.count == 1
    assert lib.get_size(0) == (2, 2)
    img = lib.get_image(0)
    np.testing.assert_array_equal(img[1, 0], [255, 0, 0, 255])
    np.testing.assert_array_equal(img[0, 0], [0, 255, 0, 255])
    lib.close()


# ---------------- WilLibrary(wil/wix) ----------------

def make_wil_files(tmp_path, images, name="test"):
    """合成 .wil/.wix:56 字节头 + 1024 字节调色板 + 每图 8 字节头 + 像素。

    images: list[(w, h, px, py, is16bit, payload)]
    - is16bit=False:payload = w*h 字节调色板索引(行序自下而上)
    - is16bit=True:payload = w*h*2 字节 RGB565(行序自下而上)
    调色板第 i 项 BGRX = (0, 0, i, 0) → 读出 RGB = (i, 0, 0)。"""
    palette = b"".join(bytes([0, 0, i, 0]) for i in range(256))
    wil = b"\x00" * 56 + palette
    offsets = []
    for (w, h, px, py, is16, data) in images:
        offsets.append(len(wil))
        wil += struct.pack("<hhhh", w, h, px, py) + data
    wix = b"\x00" * 48
    for off in offsets:
        wix += struct.pack("<i", off)
    (tmp_path / f"{name}.wix").write_bytes(wix)
    (tmp_path / f"{name}.wil").write_bytes(wil)
    return str(tmp_path / name)


def test_wil_8bit_decode(tmp_path):
    # 2x2 调色板索引,行序自下而上(数据第一段 = 底部行)
    stem = make_wil_files(tmp_path, [(2, 2, 0, 0, False,
                                      bytes([3, 0, 1, 2]))])
    lib = WilLibrary(stem)
    assert lib.count == 1
    img = lib.get_image(0)
    np.testing.assert_array_equal(img[0, 0], [1, 0, 0, 255])   # 顶部行 = 数据第二段
    np.testing.assert_array_equal(img[0, 1], [2, 0, 0, 255])
    np.testing.assert_array_equal(img[1, 0], [3, 0, 0, 255])   # 底部行 = 数据第一段
    np.testing.assert_array_equal(img[1, 1], [0, 0, 0, 0])     # 索引 0(黑)= 透明
    lib.close()


def test_wil_16bit_decode(tmp_path):
    # 16bit RGB565:图 0 靠"下一图间距 == 8+w*h*2"判定;黑 = 透明,行序翻转
    raw16 = struct.pack("<HHHH", 0xF800, 0x0000, 0x07E0, 0x001F)   # 红/黑/绿/蓝
    stem = make_wil_files(tmp_path, [
        (4, 1, 0, 0, True, raw16),
        (4, 1, 0, 0, False, bytes([5, 6, 7, 8])),
    ])
    lib = WilLibrary(stem)
    assert lib.count == 2
    img = lib.get_image(0)
    assert img is not None
    np.testing.assert_array_equal(img[0, 0], [248, 0, 0, 255])
    np.testing.assert_array_equal(img[0, 1], [0, 0, 0, 0])     # 黑 = 透明
    np.testing.assert_array_equal(img[0, 2], [0, 252, 0, 255])
    np.testing.assert_array_equal(img[0, 3], [0, 0, 248, 255])
    # 图 1 正常解码(8bit),不受上一图 16bit 影响
    np.testing.assert_array_equal(lib.get_image(1)[0, 0], [5, 0, 0, 255])
    lib.close()


def test_wil_pxpy_and_empty(tmp_path):
    # px/py 从 8 字节图头读;offset==0 的空图返回 None
    img_off = 56 + 1024                    # 文件头 + 调色板 = 图像数据起点
    wil = b"\x00" * 56 + b"\x00" * 1024
    wil += struct.pack("<hhhh", 2, 2, 3, -7) + bytes([1, 2, 3, 4])
    wix = b"\x00" * 48 + struct.pack("<i", 0) + struct.pack("<i", img_off)
    (tmp_path / "e.wix").write_bytes(wix)
    (tmp_path / "e.wil").write_bytes(wil)
    lib = WilLibrary(str(tmp_path / "e"))
    assert lib.count == 2
    assert lib.get_size(0) is None              # 空图
    assert lib.get_pxpy(0) == (0, 0)
    assert lib.get_size(1) == (2, 2)
    assert lib.get_pxpy(1) == (3, -7)
    assert lib.get_image(0) is None
    lib.close()


def test_wil_out_of_range_and_missing(tmp_path):
    stem = make_wil_files(tmp_path, [(1, 4, 0, 0, False, bytes([1, 2, 3, 4]))])
    lib = WilLibrary(stem)
    assert lib.get_size(-1) is None
    assert lib.get_size(5) is None
    assert lib.get_pxpy(5) == (0, 0)
    assert lib.get_image(5) is None
    lib.close()
    lib2 = WilLibrary(str(tmp_path / "nope"))
    assert lib2.count == 0
    assert lib2.get_image(0) is None
    lib2.close()


def test_wil_16bit_last_image_gap_to_eof(tmp_path):
    # 最后一图没有下一图:用文件尾判定位深(数据延伸到 EOF)
    raw = struct.pack("<HHHH", 0xF800, 0x07E0, 0x001F, 0xF800)
    stem = make_wil_files(tmp_path, [(4, 1, 0, 0, True, raw)])
    lib = WilLibrary(stem)
    img = lib.get_image(0)
    assert img is not None
    np.testing.assert_array_equal(img[0, 0], [248, 0, 0, 255])   # 16bit 红
    np.testing.assert_array_equal(img[0, 1], [0, 252, 0, 255])   # 绿
    np.testing.assert_array_equal(img[0, 3], [248, 0, 0, 255])
    lib.close()


def test_wil_8bit_last_image_gap_to_eof(tmp_path):
    # 最后一图 8bit(数据 w*h 字节到 EOF)→ 仍按调色板解码
    stem = make_wil_files(tmp_path, [(4, 1, 0, 0, False, bytes([3, 4, 5, 6]))])
    lib = WilLibrary(stem)
    img = lib.get_image(0)
    assert img is not None
    np.testing.assert_array_equal(img[0, 0], [3, 0, 0, 255])
    lib.close()


def test_wil_last_image_odd_gap_fallback(tmp_path):
    # 最后一图数据长度异常(非 w*h 非 w*h*2)→ 8bit 容错,不崩溃
    stem = make_wil_files(tmp_path, [(2, 2, 0, 0, False, bytes([9, 9, 9, 9, 0, 0]))])
    lib = WilLibrary(stem)
    assert lib.get_image(0) is not None
    lib.close()


def test_wil_cache(tmp_path):
    stem = make_wil_files(tmp_path, [(2, 2, 0, 0, False, bytes([1, 2, 3, 4]))])
    lib = WilLibrary(stem)
    img1 = lib.get_image(0)
    assert lib.get_image(0) is img1             # 缓存
    lib.clear_cache()
    assert lib.get_image(0) is not img1
    lib.close()


def test_wil_case_insensitive(tmp_path):
    # 真实文件可能是 Tiles.Wil / Tiles.WIX
    stem = make_wil_files(tmp_path, [(4, 1, 0, 0, False, bytes([1, 2, 3, 4]))], name="Tiles")
    (tmp_path / "Tiles.wil").rename(tmp_path / "Tiles.WIL")
    (tmp_path / "Tiles.wix").rename(tmp_path / "Tiles.WIX")
    lib = WilLibrary(str(tmp_path / "tiles"))
    assert lib.count == 1
    np.testing.assert_array_equal(lib.get_image(0)[0, 0], [1, 0, 0, 255])
    lib.close()


# ---------------- scan_libraries(递归 + 无数字后缀) ----------------

def test_scan_recursive_subdir_no_suffix(tmp_path):
    # wil/wix 在深层子目录,且无数字后缀(经典 Tiles/Objects)
    sub = tmp_path / "Data" / "Map" / "0"
    sub.mkdir(parents=True)
    make_wil_files(sub, [(4, 1, 0, 0, False, bytes([1, 2, 3, 4]))], name="Tiles")
    make_wil_files(sub, [(4, 1, 0, 0, False, bytes([3, 4, 5, 6]))], name="Objects")
    libs = scan_libraries(tmp_path)
    assert 100 in libs                          # Tiles → 100
    assert 120 in libs                          # Objects → 120
    assert isinstance(libs[100], WilLibrary)
    np.testing.assert_array_equal(libs[100].get_image(0)[0, 0], [1, 0, 0, 255])
    libs[100].close()
    libs[120].close()


def test_scan_numeric_suffix_slot(tmp_path):
    make_wil_files(tmp_path, [(4, 1, 0, 0, False, bytes([1, 2, 3, 4]))], name="Tiles222")
    make_wil_files(tmp_path, [(4, 1, 0, 0, False, bytes([1, 2, 3, 4]))], name="SmTiles3")
    libs = scan_libraries(tmp_path)
    assert 321 in libs                          # Tiles222 → 100+0+222-1
    assert 112 in libs                          # SmTiles3 → 100+10+3-1
    libs[321].close()
    libs[112].close()


def test_scan_img_dir_preferred_over_wil(tmp_path):
    # 同名图片目录与 wil 并存:图片目录优先
    make_wil_files(tmp_path, [(4, 1, 0, 0, False, bytes([9, 9, 9, 9]))], name="Tiles")
    img_dir = tmp_path / "Tiles"
    img_dir.mkdir()
    from PIL import Image
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(img_dir / "00000.png")
    libs = scan_libraries(tmp_path)
    from map_py.wil_library import PngLibrary
    assert isinstance(libs[100], PngLibrary)
    assert libs[100].count == 1


def test_scan_shallow_wins(tmp_path):
    # 根目录与子目录同名资源:浅层优先
    make_wil_files(tmp_path, [(4, 1, 0, 0, False, bytes([1, 2, 3, 4]))], name="Tiles")
    sub = tmp_path / "deep"
    sub.mkdir()
    make_wil_files(sub, [(4, 1, 0, 0, False, bytes([7, 8, 9, 10]))], name="Tiles")
    libs = scan_libraries(tmp_path)
    np.testing.assert_array_equal(libs[100].get_image(0)[0, 0], [1, 0, 0, 255])
    libs[100].close()


def test_scan_missing_lib_dir_returns_empty(tmp_path):
    assert scan_libraries(tmp_path / "nope") == {}
