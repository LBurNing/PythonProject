"""WZL/WZX 资源库解码。

复刻 C# 版 Assets/Scripts/Map/MLibrary.cs:
- .wzx:48 字节头,之后每 4 字节一个 Int32 索引(图在 .wzl 中的偏移)
- .wzl 单图 16 字节头 + 像素数据(zlib 压缩或裸数据)
- 解码分支:8bit 调色板 / 16bit RGB565(+4bit alpha 半字节平面)
- 行序自下而上,每行 4 字节对齐补位

输出统一为 (h, w, 4) uint8 RGBA 数组。
"""

import struct
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

from .palette import PALETTE

# 本地小块图片支持的扩展名(大小写不敏感)
_IMG_EXTS = (".png", ".jpg", ".bmp")


def decode_image_data(raw: bytes, width: int, height: int, is16bit: bool,
                      is24bit: bool = False) -> np.ndarray:
    """像素数据解码(纯函数)。

    - is24bit:每像素 3 字节 BGR(bo16bit=6 的盛大 24bit 格式),数据第一段为底部行
    - is16bit:RGB565(+4bit alpha 平面)
    - 其他:8bit 调色板索引
    """
    if is24bit:
        # 24bit BGR:行序自下而上(与 C# Bitmap 一致),BGR → RGB
        bgr = np.frombuffer(raw, "u1", count=width * height * 3).reshape(height, width, 3)
        out = np.zeros((height, width, 4), np.uint8)
        out[:, :, :3] = bgr[::-1, :, ::-1]
        out[:, :, 3] = 255          # 纯黑像素不改为透明(用户要求)
        return out

    hw = height * width
    # C# 判定 bytes.Length == Height*Width*2.5(浮点);整数化:len*2 == hw*5
    has_alpha = len(raw) * 2 == hw * 5
    bits = 16 if is16bit else 8
    row_bytes = width * (2 if is16bit else 1)
    row_stride = ((width * bits + 31) >> 5) * 4      # 每行 4 字节对齐(MLibrary.cs:502-505)

    out = np.zeros((height, width, 4), np.uint8)
    pos = 0
    for y in range(height - 1, -1, -1):              # 行序自下而上
        row = raw[pos:pos + row_bytes]
        pos += row_stride
        if len(row) < row_bytes:                     # 数据不足(异常文件),剩余行保持透明
            break
        if is16bit:
            c16 = np.frombuffer(row, "<u2", width)   # RGB565 小端
            r = (c16 & 0xF800) >> 8
            g = (c16 & 0x07E0) >> 3
            b = (c16 & 0x001F) << 3
            rgb = np.stack([r, g, b], -1).astype(np.uint8)
            zero = (rgb == 0).all(axis=1)            # C# (color & 0xFFFFFF)==0:RGB 全 0 → 全透明
            if has_alpha:
                # alpha 平面连续存于 raw[hw*2:],每字节 2 像素
                # C#: bytes[HW_2 + y*Width/2 + x/2](整数除法)
                x = np.arange(width)
                raw_u1 = np.frombuffer(raw, "u1")
                nib = raw_u1[hw * 2 + (y * width) // 2 + x // 2]
                a = np.where((x % 2) != 0, (nib & 0x0F) * 17, ((nib & 0xF0) >> 4) * 17)
                a = a.astype(np.uint8)
            else:
                a = np.full(width, 255, np.uint8)
            out[y] = np.where(zero[:, None], 0, np.concatenate([rgb, a[:, None]], -1))
        else:                                        # 8bit 调色板索引
            idx = np.frombuffer(row, "u1", width)
            out[y] = PALETTE[idx]
    return out


class PngLibrary:
    """PNG 小块目录资源库(与 MLibrary 同接口)。

    瓦片先由 wzl 导出为小块 PNG(如 Tiles222/00000.PNG),渲染时直接读取,
    颜色为导出时的显示调色板(正确渲染)。文件名为数字补零,位数自动检测。
    """

    _NAME_FORMATS = ("{:05d}.PNG", "{:05d}.png", "{:06d}.PNG", "{:06d}.png", "{:04d}.PNG")

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self.name = self._dir.name         # 资源库名(如 Objects222)
        self._image_cache: dict[int, np.ndarray | None] = {}
        self._size_cache: dict[int, tuple[int, int]] = {}
        # 同名 wzl/wzx:提供图头绘制偏移(px/py)(PNG 本身无头)
        self._wzl = None
        self._index_list: list[int] = []
        wzl_path = next((p for p in self._dir.parent.iterdir()
                         if p.suffix.lower() == ".wzl" and p.stem.lower() == self._dir.name.lower()),
                        None)
        if wzl_path is not None:
            self._wzl = open(wzl_path, "rb")
            wzx_path = next((p for p in self._dir.parent.iterdir()
                             if p.suffix.lower() == ".wzx" and p.stem.lower() == self._dir.name.lower()),
                            None)
            if wzx_path is not None:
                data = wzx_path.read_bytes()
                self._index_list = list(struct.unpack(f"<{(len(data) - 48) // 4}i", data[48:]))
        # 检测命名位数与图数:取目录中第一个数字命名的图片(png/jpg/bmp,大小写不敏感)
        self._count = 0
        self._fmt = None
        import re
        files = [f for f in sorted(self._dir.iterdir())
                 if f.is_file() and f.suffix.lower() in _IMG_EXTS
                 and re.match(r"\d+\.", f.name)]
        if files:
            m = re.match(r"(\d+)\.", files[0].name)
            self._fmt = "{{:0{}d}}".format(len(m.group(1)))   # 不含扩展名
            # 图数:最后一个数字文件的索引 + 1(空洞图跳过)
            last = 0
            for f in files:
                last = max(last, int(re.match(r"(\d+)\.", f.name).group(1)))
            self._count = last + 1

    @property
    def count(self) -> int:
        return self._count

    def _path(self, index: int) -> Path | None:
        """数字图片路径:尝试 png/jpg/bmp,后缀大小写都兼容。"""
        if self._fmt is None:
            return None
        base = self._dir / self._fmt.format(index)
        for ext in _IMG_EXTS:
            for name in (base.name + ext, base.name + ext.upper()):
                p = base.with_name(name)
                if p.is_file():
                    return p
        return None

    def get_size(self, index: int) -> tuple[int, int] | None:
        if index < 0 or index >= self._count:
            return None
        if index in self._size_cache:
            return self._size_cache[index]
        p = self._path(index)
        if p is None:
            return None
        with Image.open(p) as im:
            size = im.size
        self._size_cache[index] = size
        return size

    def get_pxpy(self, index: int) -> tuple[int, int]:
        """PNG 小块无头,从同名 wzl 读图头偏移 (px, py);无 wzl 返回 (0, 0)。"""
        if self._wzl is None or not 0 <= index < len(self._index_list):
            return (0, 0)
        off = self._index_list[index]
        if off == 0:
            return (0, 0)
        self._wzl.seek(off)
        hdr = self._wzl.read(16)
        if len(hdr) < 16:
            return (0, 0)
        _, _, px, py = struct.unpack_from("<hhhh", hdr, 4)
        return (px, py)

    def get_image(self, index: int) -> np.ndarray | None:
        if index in self._image_cache:
            return self._image_cache[index]
        img = self._decode(index)
        self._image_cache[index] = img
        return img

    def _decode(self, index: int) -> np.ndarray | None:
        p = self._path(index)
        if p is None:
            return None
        with Image.open(p) as im:
            return np.asarray(im.convert("RGBA"))

    def clear_cache(self) -> None:
        self._image_cache.clear()

    def close(self) -> None:
        if self._wzl is not None:
            self._wzl.close()
            self._wzl = None


class MLibrary:
    """一个 wzl/wzx 资源库,懒加载 + 解码缓存。"""

    def __init__(self, stem: str | Path) -> None:
        stem = Path(stem)
        self.name = stem.name              # 资源库名(如 Objects222)
        self._wzl = None
        self._size_cache: dict[int, tuple[int, int, int, bool]] = {}
        self._image_cache: dict[int, np.ndarray | None] = {}

        # 大小写不敏感查找(真实文件可能是 Objects222.Wzl / .WZX)
        def _find(name: str) -> Path | None:
            p = stem.with_name(name)
            if p.is_file():
                return p
            low = name.lower()
            for f in stem.parent.iterdir():
                if f.name.lower() == low:
                    return f
            return None

        wzx = _find(stem.name + ".wzx")
        if wzx is not None:
            with open(wzx, "rb") as f:
                f.seek(48)
                data = f.read()
            n = len(data) // 4
            self._index_list = list(struct.unpack(f"<{n}i", data[: n * 4]))
        else:
            self._index_list = []

        wzl = _find(stem.name + ".wzl")
        if wzl is not None:
            self._wzl = open(wzl, "rb")

    @property
    def count(self) -> int:
        return len(self._index_list)

    def _read_header(self, offset: int) -> tuple[int, int, int, int, int, int]:
        """16 字节单图头,返回 (w, h, px, py, nsize, fmt)。
        fmt: 5=16bit RGB565, 6=24bit BGR, 其他=8bit 调色板索引。
        px/py: 绘制偏移(官方引擎中 blend 瓦片定位用,普通图恒为 0)。"""
        cached = self._size_cache.get(offset)
        if cached is not None:
            return cached
        assert self._wzl is not None
        self._wzl.seek(offset)
        header = self._wzl.read(16)
        fmt = header[0]
        w, h, px, py = struct.unpack_from("<hhhh", header, 4)
        nsize = struct.unpack_from("<i", header, 12)[0]
        info = (w, h, px, py, nsize, fmt)
        self._size_cache[offset] = info
        return info

    def get_size(self, index: int) -> tuple[int, int] | None:
        """C# GetSize 语义;索引无效或空图(offset==0)返回 None。"""
        if index < 0 or index >= self.count:
            return None
        offset = self._index_list[index]
        if offset == 0:                              # MImage 构造函数 Position==0 直接返回
            return None
        w, h, _, _, _, _ = self._read_header(offset)
        return (w, h)

    def get_pxpy(self, index: int) -> tuple[int, int]:
        """图头绘制偏移 (px, py);无效/空图返回 (0, 0)。"""
        if index < 0 or index >= self.count:
            return (0, 0)
        offset = self._index_list[index]
        if offset == 0:
            return (0, 0)
        _, _, px, py, _, _ = self._read_header(offset)
        return (px, py)

    def get_image(self, index: int) -> np.ndarray | None:
        """解码为 (h, w, 4) uint8 RGBA(带缓存);空图/无效返回 None。"""
        if index in self._image_cache:
            return self._image_cache[index]
        img = self._decode(index)
        self._image_cache[index] = img
        return img

    def _decode(self, index: int) -> np.ndarray | None:
        if index < 0 or index >= self.count or self._wzl is None:
            return None
        offset = self._index_list[index]
        if offset == 0:
            return None
        w, h, _, _, nsize, fmt = self._read_header(offset)
        if w * h < 4:                                # CheckImage:宽高都小则不创建纹理
            return None
        self._wzl.seek(offset + 16)
        if nsize == 0:
            bpp = 2 if fmt == 5 else (3 if fmt == 6 else 1)
            raw = self._wzl.read(w * h * bpp)
        else:
            raw = zlib.decompress(self._wzl.read(nsize))
        if fmt == 5:
            return decode_image_data(raw, w, h, True)
        if fmt == 6:
            return decode_image_data(raw, w, h, False, is24bit=True)
        return decode_image_data(raw, w, h, False)

    def clear_cache(self) -> None:
        self._image_cache.clear()

    def close(self) -> None:
        if self._wzl is not None:
            self._wzl.close()
            self._wzl = None


class WilLibrary:
    """旧版 .wil/.wix 资源库(8bit 调色板,MirWil.pas 布局,实测验证)。

    - .wix:48 字节头(标题 44 + IndexCount)+ 每 4 字节 Int32 索引
    - .wil:56 字节头(标题 44 + ImageCount@44 + ColorCount@48 + PaletteSize@52)
      + 256 项调色板 @56(BGRX,4 字节/项)+ 图数据 @1080
    - 每图:TImageInfo 8 字节(W, H, PX, PY)+ w*h 字节 8bit 调色板索引
    - 行序自下而上(第一段数据 = 底部行);索引 0(黑)= 透明(colorkey 0)
    """

    def __init__(self, stem: str | Path) -> None:
        stem = Path(stem)
        self.name = stem.name
        self._wil = None
        self._index_list: list[int] = []
        self._palette = None
        self._image_cache: dict[int, np.ndarray | None] = {}

        def _find(name: str) -> Path | None:
            p = stem.with_name(name)
            if p.is_file():
                return p
            low = name.lower()
            for f in stem.parent.iterdir():
                if f.name.lower() == low:
                    return f
            return None

        wix = _find(stem.name + ".wix")
        if wix is not None:
            data = wix.read_bytes()
            self._index_list = list(struct.unpack(f"<{(len(data) - 48) // 4}i", data[48:]))
        wil_path = _find(stem.name + ".wil")
        if wil_path is not None:
            self._wil = open(wil_path, "rb")
            self._wil.seek(56)
            paldata = self._wil.read(1024)
            if len(paldata) == 1024:
                bgr = np.frombuffer(paldata, "u1").reshape(256, 4)[:, :3][:, ::-1]
                self._palette = np.zeros((256, 4), np.uint8)
                self._palette[:, :3] = bgr
                self._palette[:, 3] = 255
                self._palette[0, 3] = 0           # 索引 0(黑色)= 透明

    @property
    def count(self) -> int:
        return len(self._index_list)

    def _header(self, offset: int) -> tuple[int, int, int, int] | None:
        if self._wil is None:
            return None
        self._wil.seek(offset)
        hdr = self._wil.read(8)
        if len(hdr) < 8:
            return None
        return struct.unpack("<hhhh", hdr)

    def get_size(self, index: int) -> tuple[int, int] | None:
        if not 0 <= index < self.count:
            return None
        off = self._index_list[index]
        if off == 0:
            return None
        hd = self._header(off)
        return (hd[0], hd[1]) if hd else None

    def get_pxpy(self, index: int) -> tuple[int, int]:
        if not 0 <= index < self.count:
            return (0, 0)
        off = self._index_list[index]
        if off == 0:
            return (0, 0)
        hd = self._header(off)
        return (hd[2], hd[3]) if hd else (0, 0)

    def get_image(self, index: int) -> np.ndarray | None:
        if index in self._image_cache:
            return self._image_cache[index]
        img = self._decode(index)
        self._image_cache[index] = img
        return img

    def _decode(self, index: int) -> np.ndarray | None:
        if not 0 <= index < self.count:
            return None
        off = self._index_list[index]
        if off == 0:
            return None
        hd = self._header(off)
        if hd is None:
            return None
        w, h = hd[0], hd[1]
        if w * h < 4:
            return None
        # 判定像素格式:图间距 = 8 + w*h(8bit 调色板)或 8 + w*h*2(16bit RGB565)
        nxt = self._index_list[index + 1] if index + 1 < self.count else None
        self._wil.seek(off + 8)
        if nxt is not None and nxt - off - 8 == w * h * 2:
            raw = self._wil.read(w * h * 2)
            if len(raw) < w * h * 2:
                return None
            c16 = np.frombuffer(raw, "<u2", w * h).reshape(h, w)
            r = (c16 & 0xF800) >> 8
            g = (c16 & 0x07E0) >> 3
            b = (c16 & 0x001F) << 3
            rgb = np.stack([r, g, b], -1).astype(np.uint8)
            out = np.zeros((h, w, 4), np.uint8)
            out[:, :, :3] = rgb
            out[:, :, 3] = np.where((rgb == 0).all(axis=2), 0, 255)   # 黑 = 透明
            return out[::-1]                     # 行序自下而上 → 翻转
        # 8bit 调色板
        if self._palette is None:
            return None
        raw = self._wil.read(w * h)
        if len(raw) < w * h:
            return None
        idx = np.frombuffer(raw, "u1", w * h).reshape(h, w)
        out = self._palette[idx]                 # 行序自下而上 → 翻转
        return out[::-1]

    def clear_cache(self) -> None:
        self._image_cache.clear()

    def close(self) -> None:
        if self._wil is not None:
            self._wil.close()
            self._wil = None


class PakLibrary:
    """GEE 引擎 .pak 资源库(.GEEPAK3 实测逆向)。

    - 文件头(签名 + 图数/索引区)加密,不可解析
    - 数据区:每张图 = 一个 zlib 压缩流,**流顺序 = 图顺序**(索引 1..N → 流 0..N-1)
    - 像素:24bit BGR,宽 64(高 = 解压长度/3/宽),行序自下而上,黑 = 透明
    """

    def __init__(self, stem: str | Path) -> None:
        stem = Path(stem)
        self.name = stem.name
        self._streams: list[tuple[int, int, int]] = []   # (数据偏移, 压缩长, 解压长)
        pak_path = next((p for p in stem.parent.iterdir()
                         if p.suffix.lower() == ".pak" and p.stem.lower() == stem.name.lower()),
                        None)
        if pak_path is None:
            return
        self._pak_data = pak_path.read_bytes()
        data = self._pak_data
        # 流式扫描全部 zlib 流(0x78 开头,deflate 32K 窗口)
        n = len(data)
        i = 0
        while i < n - 2:
            if data[i] == 0x78 and data[i + 1] in (0x9C, 0xDA, 0x01, 0x5E, 0x99):
                dobj = zlib.decompressobj()
                try:
                    out = dobj.decompress(data[i:i + 2_000_000])
                    comp = len(data[i:i + 2_000_000]) - len(dobj.unused_data)
                    self._streams.append((i, comp, len(out)))
                    i += comp
                    continue
                except Exception:
                    pass
            i += 1

    @property
    def count(self) -> int:
        return len(self._streams)

    def _real_height(self, index: int) -> int:
        """真实高度:去掉底部白色填充行(实测 Tiles126 = 64x96 + 64x32 白填充)。"""
        pos, comp, dlen = self._streams[index]
        h = dlen // 3 // 64
        if h < 4:
            return 0
        out = zlib.decompress(self._pak_data[pos:pos + comp])
        bgr = np.frombuffer(out, "u1", 64 * h * 3).reshape(h, 64, 3)
        real = h
        for row in range(h - 1, 0, -1):
            if (bgr[row] == 255).all():
                real -= 1
            else:
                break
        return real

    def get_size(self, index: int) -> tuple[int, int] | None:
        if not 0 <= index < self.count:
            return None
        h = self._real_height(index)
        if h < 4:
            return None
        return (64, h)

    def get_pxpy(self, index: int) -> tuple[int, int]:
        return (0, 0)

    def get_image(self, index: int) -> np.ndarray | None:
        if not 0 <= index < self.count:
            return None
        pos, comp, dlen = self._streams[index]
        h = dlen // 3 // 64
        if h < 4:
            return None
        out = zlib.decompress(self._pak_data[pos:pos + comp])
        bgr = np.frombuffer(out, "u1", 64 * h * 3).reshape(h, 64, 3)
        # 去掉底部白色填充行
        real = h
        for row in range(h - 1, 0, -1):
            if (bgr[row] == 255).all():
                real -= 1
            else:
                break
        bgr = bgr[:real]
        out_img = np.zeros((real, 64, 4), np.uint8)
        out_img[:, :, :3] = bgr[:, :, ::-1]        # BGR → RGB
        out_img[:, :, 3] = 255                     # 24bit 无 alpha,黑像素不透明(实测为内容)
        return out_img[::-1]                        # 行序自下而上 → 翻转

    def clear_cache(self) -> None:
        pass

    def close(self) -> None:
        pass
