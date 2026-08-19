"""Mir2 .map 文件解析。

复刻 C# 版 Assets/Scripts/Map/MapCode.cs 的 MapReader:
- 格式识别链 detect_format(仅支持 Type2/Type100/Type3,其余抛 MapParseError)
- 向量化(structured dtype + np.frombuffer)解析为统一 Cell 结构化数组
- 大图尺寸 = 格数 x 48 / 32 像素(MapTools.CellWidth/CellHeight)

所有多字节字段小端序(BitConverter 默认小端)。
"""

from pathlib import Path
import struct

import numpy as np

# 每格像素尺寸(MapTools.cs:65-66)
CELL_WIDTH = 48
CELL_HEIGHT = 32

# 渲染只依赖这一套统一字段(下标 [x, y],宽在前)
STD_DTYPE = np.dtype([
    ("back_index", "<i4"),      # 图库槽位(400 槽数组下标)
    ("back_image", "<i4"),      # 图库内图片索引(解码后需 -1)
    ("middle_index", "<i4"),
    ("middle_image", "<i4"),
    ("front_index", "<i4"),
    ("front_image", "<i4"),
    ("door_index", "u1"),
    ("door_offset", "u1"),
    ("front_anim_frame", "u1"),
    ("front_anim_tick", "u1"),
    ("middle_anim_frame", "u1"),
    ("middle_anim_tick", "u1"),
    ("tile_anim_image", "<i4"),
    ("tile_anim_offset", "<i4"),
    ("tile_anim_frames", "u1"),
    ("light", "u1"),
])

# ---- 各格式原始布局(itemsize 显式固定,防对齐填充)----

# Type2(14 字节/格,数据从 52 起)
T2_DTYPE = np.dtype([
    ("back_image", "<i2"), ("middle_image", "<i2"), ("front_image", "<i2"),
    ("door_index", "u1"), ("door_offset", "u1"),
    ("front_anim_frame", "u1"), ("front_anim_tick", "u1"),
    ("front_index_raw", "u1"), ("light", "u1"),
    ("back_index_raw", "u1"), ("middle_index_raw", "u1"),
])

# Type3(40 字节/格,数据从 52 起)= Type2 的 14 字节 + 26 字节扩展
T3_DTYPE = np.dtype([
    ("back_image", "<i2"), ("middle_image", "<i2"), ("front_image", "<i2"),
    ("door_index", "u1"), ("door_offset", "u1"),
    ("front_anim_frame", "u1"), ("front_anim_tick", "u1"),
    ("front_index_raw", "u1"), ("light", "u1"),
    ("back_index_raw", "u1"), ("middle_index_raw", "u1"),
    ("tile_anim_image", "<i2"),
    ("pad", "u1", 7),               # 2 动画帧 + 2 空 + 2 backtiles 索引 + 1 文件号
    ("tile_anim_frames", "u1"),
    ("tile_anim_offset", "<i2"),
    ("pad2", "u1", 14),             # 光照/混合相关,不用
])

# Type100(26 字节/格,数据从 8 起;BackImage 是 Int32,Index 在 Image 前)
T100_DTYPE = np.dtype([
    ("back_index", "<i2"), ("back_image", "<i4"),
    ("middle_index", "<i2"), ("middle_image", "<i2"),
    ("front_index", "<i2"), ("front_image", "<i2"),
    ("door_index", "u1"), ("door_offset", "u1"),
    ("front_anim_frame", "u1"), ("front_anim_tick", "u1"),
    ("middle_anim_frame", "u1"), ("middle_anim_tick", "u1"),
    ("tile_anim_image", "<i2"), ("tile_anim_offset", "<i2"),
    ("tile_anim_frames", "u1"), ("light", "u1"),
])


class MapParseError(Exception):
    """不支持的 .map 格式或解析失败。"""


def detect_format(data: bytes) -> int:
    """复刻 MapCode.cs initiate() 的识别链,返回 2/3/100,其他格式抛 MapParseError。"""
    if len(data) < 52:
        raise MapParseError(f"文件过小({len(data)} 字节),不是合法的 .map 文件")
    if data[2] == 0x43 and data[3] == 0x23:      # "C#" 自定义格式
        return 100
    if data[0] == 0:                             # Wemade Mir3 无标题
        raise MapParseError("Type5(Wemade Mir3)暂不支持")
    if data[0] == 0x0F and data[5] == 0x53 and data[14] == 0x33:   # "(C) SNDA, MIR3"
        raise MapParseError("Type6(Shanda Mir3)暂不支持")
    if data[0] == 0x15 and data[4] == 0x32 and data[6] == 0x41 and data[19] == 0x31:
        raise MapParseError("Type4(Mir2 AntiHack 加密)暂不支持")
    if data[0] == 0x10 and data[2] == 0x61 and data[7] == 0x31 and data[14] == 0x31:
        raise MapParseError("Type1(Map 2010 加密)暂不支持")
    if data[4] == 0x0F and data[18] == 0x0D and data[19] == 0x0A:
        w = data[0] | (data[1] << 8)
        h = data[2] | (data[3] << 8)
        return 3 if len(data) > 52 + w * h * 14 else 2
    if data[0] == 0x0D and data[1] == 0x4C and data[7] == 0x20 and data[11] == 0x6D:
        raise MapParseError("Type7(3/4 英雄)暂不支持")
    return 2                                   # 默认旧格式


def parse_map(data: bytes, fmt: int) -> tuple[int, int, np.ndarray]:
    """解析为 (width, height, cells)。cells 下标 [x, y],字段见 STD_DTYPE。"""
    if fmt == 2:
        return _parse_t2(data)
    if fmt == 3:
        return _parse_t3(data)
    if fmt == 100:
        return _parse_t100(data)
    raise MapParseError(f"不支持的格式 Type{fmt}")


def _check_len(data: bytes, need: int, fmt: str) -> None:
    if len(data) < need:
        raise MapParseError(f"{fmt} 文件长度不足:需要 {need} 字节,实际 {len(data)}")


def _parse_t2(data: bytes) -> tuple[int, int, np.ndarray]:
    w, h = struct.unpack_from("<hh", data, 0)
    _check_w_h(w, h)
    _check_len(data, 52 + w * h * 14, "Type2")
    raw = np.frombuffer(data, dtype=T2_DTYPE, count=w * h, offset=52).reshape(w, h)
    cells = np.zeros((w, h), dtype=STD_DTYPE)
    for f in ("back_image", "middle_image", "front_image"):
        cells[f] = raw[f]
    cells["door_index"] = raw["door_index"] & 0x7F
    cells["door_offset"] = raw["door_offset"]
    cells["front_anim_frame"] = raw["front_anim_frame"]
    cells["front_anim_tick"] = raw["front_anim_tick"]
    cells["light"] = raw["light"]
    cells["front_index"] = raw["front_index_raw"].astype(np.int32) + 120
    cells["back_index"] = raw["back_index_raw"].astype(np.int32) + 100
    cells["middle_index"] = raw["middle_index_raw"].astype(np.int32) + 110
    _bit15_to_bit29(cells["back_image"])
    return w, h, cells


def _parse_t3(data: bytes) -> tuple[int, int, np.ndarray]:
    w, h = struct.unpack_from("<hh", data, 0)
    _check_w_h(w, h)
    _check_len(data, 52 + w * h * 40, "Type3")
    raw = np.frombuffer(data, dtype=T3_DTYPE, count=w * h, offset=52).reshape(w, h)
    cells = np.zeros((w, h), dtype=STD_DTYPE)
    for f in ("back_image", "middle_image", "front_image"):
        cells[f] = raw[f]
    cells["door_index"] = raw["door_index"] & 0x7F
    cells["door_offset"] = raw["door_offset"]
    cells["front_anim_frame"] = raw["front_anim_frame"]
    cells["front_anim_tick"] = raw["front_anim_tick"]
    cells["light"] = raw["light"]
    cells["front_index"] = raw["front_index_raw"].astype(np.int32) + 120
    cells["back_index"] = raw["back_index_raw"].astype(np.int32) + 100
    cells["middle_index"] = raw["middle_index_raw"].astype(np.int32) + 110
    cells["tile_anim_image"] = raw["tile_anim_image"]
    cells["tile_anim_frames"] = raw["tile_anim_frames"]
    cells["tile_anim_offset"] = raw["tile_anim_offset"]
    _bit15_to_bit29(cells["back_image"])
    return w, h, cells


def _parse_t100(data: bytes) -> tuple[int, int, np.ndarray]:
    if data[0] != 1 or data[1] != 0:
        raise MapParseError("Type100 仅支持版本 1")
    w, h = struct.unpack_from("<hh", data, 4)
    _check_w_h(w, h)
    _check_len(data, 8 + w * h * 26, "Type100")
    raw = np.frombuffer(data, dtype=T100_DTYPE, count=w * h, offset=8).reshape(w, h)
    cells = np.zeros((w, h), dtype=STD_DTYPE)
    for f in ("back_index", "back_image", "middle_index", "middle_image",
              "front_index", "front_image"):
        cells[f] = raw[f]
    cells["door_index"] = raw["door_index"] & 0x7F
    cells["door_offset"] = raw["door_offset"]
    cells["front_anim_frame"] = raw["front_anim_frame"]
    cells["front_anim_tick"] = raw["front_anim_tick"]
    cells["middle_anim_frame"] = raw["middle_anim_frame"]
    cells["middle_anim_tick"] = raw["middle_anim_tick"]
    cells["tile_anim_image"] = raw["tile_anim_image"]
    cells["tile_anim_offset"] = raw["tile_anim_offset"]
    cells["tile_anim_frames"] = raw["tile_anim_frames"]
    cells["light"] = raw["light"]
    return w, h, cells


def _check_w_h(w: int, h: int) -> None:
    if w <= 0 or h <= 0 or w * h > 100_000_000:
        raise MapParseError(f"非法宽高 {w}x{h}")


def _bit15_to_bit29(back_image: np.ndarray) -> None:
    """MapCode.cs:296-297:BackImage 的 bit15 置位时改写为 bit29(0x20000000 标志)。"""
    hi = (back_image & 0x8000) != 0
    back_image[hi] = (back_image[hi] & 0x7FFF) | 0x20000000


class MapReader:
    """.map 文件入口。"""

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"地图文件不存在: {path}")
        self._path = path
        data = path.read_bytes()
        self.format_type = detect_format(data)
        self.width, self.height, self.cells = parse_map(data, self.format_type)

    @property
    def map_name(self) -> str:
        return self._path.stem

    @property
    def pixel_width(self) -> int:
        return self.width * CELL_WIDTH

    @property
    def pixel_height(self) -> int:
        return self.height * CELL_HEIGHT

    def cell(self, x: int, y: int) -> dict:
        """调试用:单格字段可读视图。"""
        return {f: int(self.cells[x, y][f]) for f in self.cells.dtype.names}
