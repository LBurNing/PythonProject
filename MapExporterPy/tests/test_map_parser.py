"""map_parser 单元测试:合成字节验证 Type2/Type100/Type3 解析与格式识别。"""

import struct

import numpy as np
import pytest

from map_py.map_parser import (
    CELL_HEIGHT, CELL_WIDTH, MapParseError, MapReader, detect_format, parse_map,
)


def make_t2_file(w: int, h: int, cell_bytes: bytes) -> bytes:
    """Type2/Type3 共用头部:W/H @0/2 + 48 字节标题区(数据从 52 起)。"""
    return struct.pack("<hh", w, h) + b"\x00" * 48 + cell_bytes


def t2_cell(back=1, mid=2, front=3, door_idx=0, door_off=0, anim_f=0, anim_t=0,
            front_idx=10, light=0, back_idx=200, mid_idx=210) -> bytes:
    """Type2 单格 14 字节(按 MapCode.cs:281-295 顺序)。"""
    return struct.pack(
        "<hhhBBBBBBBB", back, mid, front, door_idx, door_off, anim_f, anim_t,
        front_idx, light, back_idx, mid_idx)


# ---------------- detect_format ----------------

def test_detect_type100_magic():
    data = b"\x00\x00\x43\x23" + b"\x00" * 48
    assert detect_format(data) == 100


def test_detect_type5_raises():
    data = b"\x00" * 52
    with pytest.raises(MapParseError, match="Type5"):
        detect_format(data)


def test_detect_type3_vs_type2_by_size():
    # 头部命中 Shanda 2012 判定链,按文件长度区分
    header = bytearray(52)
    header[0:2] = struct.pack("<h", 2)
    header[2:4] = struct.pack("<h", 2)
    header[4] = 0x0F
    header[18] = 0x0D
    header[19] = 0x0A
    # 52 + 2*2*14 = 108;>108 → Type3,否则 Type2
    data2 = bytes(header) + b"\x00" * 56          # 108 字节
    data3 = bytes(header) + b"\x00" * 80          # 132 字节
    assert detect_format(data2) == 2
    assert detect_format(data3) == 3


def test_detect_default_type2():
    data = b"\x01\x00\x02\x00" + b"\x11" * 48
    assert detect_format(data) == 2


def test_detect_unsupported_formats_raise():
    # Wemade Mir3(空字节开头)已覆盖;再验证 2010 加密
    data = bytearray(52)
    data[0] = 0x10
    data[2] = 0x61
    data[7] = 0x31
    data[14] = 0x31
    with pytest.raises(MapParseError, match="Type1"):
        detect_format(bytes(data))


def test_detect_too_small():
    with pytest.raises(MapParseError, match="过小"):
        detect_format(b"\x00" * 10)


# ---------------- Type2 ----------------

def test_type2_basic_fields():
    cell = t2_cell(back=5, mid=6, front=7, door_idx=0x81, door_off=2, anim_f=3,
                   anim_t=4, front_idx=10, light=105, back_idx=200, mid_idx=210)
    data = make_t2_file(1, 1, cell)
    w, h, cells = parse_map(data, 2)
    assert (w, h) == (1, 1)
    c = cells[0, 0]
    assert c["back_image"] == 5
    assert c["middle_image"] == 6
    assert c["front_image"] == 7
    assert c["door_index"] == 1        # 0x81 & 0x7F
    assert c["door_offset"] == 2
    assert c["front_anim_frame"] == 3
    assert c["front_anim_tick"] == 4
    assert c["front_index"] == 130     # 10 + 120
    assert c["light"] == 105
    assert c["back_index"] == 300      # 200 + 100
    assert c["middle_index"] == 320    # 210 + 110


def test_type2_bit15_to_bit29():
    cell = t2_cell(back=-32765)        # 0x8003 的有符号 short:bit15 置位
    w, h, cells = parse_map(make_t2_file(1, 1, cell), 2)
    assert cells[0, 0]["back_image"] == (0x0003 | 0x20000000)


def test_type2_shape_x_outer():
    # 2x2 格:文件顺序是 C# 的 for x { for y } → x 慢变,y 快变
    c00 = t2_cell(back=1)
    c01 = t2_cell(back=2)
    c10 = t2_cell(back=3)
    c11 = t2_cell(back=4)
    data = make_t2_file(2, 2, c00 + c01 + c10 + c11)
    w, h, cells = parse_map(data, 2)
    assert cells.shape == (2, 2)
    assert cells[0, 0]["back_image"] == 1
    assert cells[0, 1]["back_image"] == 2    # y 快变:第二格是 (0,1)
    assert cells[1, 0]["back_image"] == 3    # 第三格是 (1,0)
    assert cells[1, 1]["back_image"] == 4


def test_type2_truncated_raises():
    data = make_t2_file(4, 4, b"\x00" * 10)   # 不足 16 格
    with pytest.raises(MapParseError, match="长度不足"):
        parse_map(data, 2)


# ---------------- Type100 ----------------

def test_type100_fields_and_order():
    # 版本 1 + W/H @4/6,数据从 8 起
    header = b"\x01\x00" + b"\x00\x00" + struct.pack("<hh", 1, 1)
    cell = struct.pack(
        "<hi hh hh BBBBBB hh BB",
        300,              # back_index i16
        0x12345678,       # back_image i32(注意负数截断,见下)
        310,              # middle_index i16
        5,                # middle_image i16
        320,              # front_index i16
        6,                # front_image i16
        0x81, 2, 3, 4, 5, 6,   # door_index/offset + 4 动画帧
        7, 8,             # tile_anim_image / tile_anim_offset
        9, 10,            # tile_anim_frames / light
    )
    # 手动核对 26 字节:2+4+2+2+2+2+6+2+2+2 = 26
    assert len(cell) == 26
    data = header + cell
    w, h, cells = parse_map(data, 100)
    c = cells[0, 0]
    assert c["back_index"] == 300
    assert c["back_image"] == 0x12345678          # Int32 不截断
    assert c["middle_index"] == 310
    assert c["middle_image"] == 5
    assert c["front_index"] == 320
    assert c["front_image"] == 6
    assert c["door_index"] == 1                   # 0x81 & 0x7F
    assert c["door_offset"] == 2
    assert c["front_anim_frame"] == 3
    assert c["front_anim_tick"] == 4
    assert c["middle_anim_frame"] == 5
    assert c["middle_anim_tick"] == 6
    assert c["tile_anim_image"] == 7
    assert c["tile_anim_offset"] == 8
    assert c["tile_anim_frames"] == 9
    assert c["light"] == 10


def test_type100_version_check():
    data = b"\x02\x00" + b"\x00" * 50
    with pytest.raises(MapParseError, match="版本"):
        parse_map(data, 100)


# ---------------- Type3 ----------------

def test_type3_40_bytes_per_cell():
    # 每格 40 字节 = Type2 的 14 + tile_anim_image(2) + pad(7) + frames(1)
    #                + tile_anim_offset(2) + pad2(14)
    base = t2_cell(back=5, front_idx=10, back_idx=200, mid_idx=210)
    ext = struct.pack("<h", 123) + b"\x00" * 7 + struct.pack("B", 7) + struct.pack("<h", 456) + b"\x00" * 14
    cell = base + ext
    assert len(cell) == 40
    data = make_t2_file(1, 1, cell)
    w, h, cells = parse_map(data, 3)
    c = cells[0, 0]
    assert c["back_image"] == 5
    assert c["front_index"] == 130
    assert c["back_index"] == 300
    assert c["middle_index"] == 320
    assert c["tile_anim_image"] == 123
    assert c["tile_anim_frames"] == 7
    assert c["tile_anim_offset"] == 456


def test_type3_bit15_to_bit29():
    base = t2_cell(back=-32765)
    cell = base + b"\x00" * 26
    w, h, cells = parse_map(make_t2_file(1, 1, cell), 3)
    assert cells[0, 0]["back_image"] == (0x0003 | 0x20000000)


# ---------------- MapReader 入口 ----------------

def test_map_reader_real_format(tmp_path):
    cell = t2_cell(back=1, front_idx=10)
    p = tmp_path / "test.map"
    p.write_bytes(make_t2_file(2, 3, cell * 6))
    r = MapReader(p)
    assert r.map_name == "test"
    assert (r.width, r.height) == (2, 3)
    assert (r.pixel_width, r.pixel_height) == (2 * CELL_WIDTH, 3 * CELL_HEIGHT)
    assert r.cells.shape == (2, 3)


def test_map_reader_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        MapReader(tmp_path / "nope.map")


def test_map_reader_unsupported_format(tmp_path):
    p = tmp_path / "mir3.map"
    p.write_bytes(b"\x00" * 52)
    with pytest.raises(MapParseError, match="Type5"):
        MapReader(p)
