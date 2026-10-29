"""PNG + PLIST 图集资源库。

兼容 Cocos2d / TexturePacker 图集(metadata.format 2/3):
- 同一资源库由多个分片组成,如 obj84_0.plist/png、obj84_1.plist/png
- 帧名末尾数字即库内索引(obj84_000000.png → 0)
- frame 是帧在图集中的矩形;rotated 时该矩形按旋转后尺寸存储
- sourceColorRect 是裁剪后的有效区域,sourceSize 是原图尺寸,
  offset 是裁边偏移 → 三者用于把帧还原到原始画布

接口与 MLibrary / PngLibrary 一致,输出 (h, w, 4) uint8 RGBA。
"""

import plistlib
import re
from collections import OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image

_SHARD_RE = re.compile(r"_(\d+)$")          # 分片序号:obj84_1
_TAIL_NUM_RE = re.compile(r"(\d+)$")        # 帧名末尾数字 = 库内索引
_NUMS_RE = re.compile(r"-?\d+(?:\.\d+)?")   # 坐标串里的数字

# 图集 PNG 按需打开并缓存;上限 6 片,避免大图集全部常驻内存
_MAX_ATLAS_CACHE = 6


def _nums(text) -> list[int]:
    """'{100,354}' / '{{0,0},{48,320}}' → 整数列表(坐标四舍五入)。"""
    if not isinstance(text, str):
        return []
    return [int(round(float(v))) for v in _NUMS_RE.findall(text)]


def _rect(info: dict, *keys) -> tuple[int, int, int, int] | None:
    """按候选键取矩形 {{x,y},{w,h}} → (x, y, w, h)。"""
    for key in keys:
        vals = _nums(info.get(key))
        if len(vals) >= 4:
            return vals[0], vals[1], vals[2], vals[3]
    return None


def _pair(info: dict, *keys) -> tuple[int, int] | None:
    """按候选键取二维值 {w,h} / {x,y} → (a, b)。"""
    for key in keys:
        vals = _nums(info.get(key))
        if len(vals) >= 2:
            return vals[0], vals[1]
    return None


def parse_frame(info: dict) -> dict | None:
    """解析单帧(format 2/3 键名兼容),缺少 frame 时返回 None。"""
    frame = _rect(info, "frame", "textureRect")
    if frame is None:
        return None
    fx, fy, fw, fh = frame
    return {
        "frame": frame,
        "color": _rect(info, "sourceColorRect", "spriteColorRect") or (0, 0, fw, fh),
        "size": _pair(info, "sourceSize", "spriteSourceSize") or (fw, fh),
        "offset": _pair(info, "offset", "spriteOffset") or (0, 0),
        "rotated": bool(info.get("rotated", info.get("textureRotated", False))),
    }


def frame_index(name: str) -> int | None:
    """帧名 → 库内索引:obj84_000000.png → 0;无末尾数字返回 None。"""
    m = _TAIL_NUM_RE.search(Path(str(name)).stem)
    return int(m.group(1)) if m else None


def _find_png(plist_path: Path) -> Path | None:
    """同名 .png(大小写不敏感)。"""
    png = plist_path.with_suffix(".png")
    if png.is_file():
        return png
    low = png.name.lower()
    try:
        for f in plist_path.parent.iterdir():
            if f.name.lower() == low:
                return f
    except OSError:
        pass
    return None


class PlistLibrary:
    """PNG + PLIST 图集资源库(一个资源库可由多个分片组成)。"""

    def __init__(self, plist_files: list[str | Path]) -> None:
        paths = sorted((Path(p) for p in plist_files), key=self._shard_no)
        self.name = _SHARD_RE.sub("", paths[0].stem) if paths else ""
        # index → (分片 png, 帧信息)
        self._frames: dict[int, tuple[Path, dict]] = {}
        self._atlas_cache: OrderedDict[Path, Image.Image] = OrderedDict()
        self._image_cache: dict[int, np.ndarray | None] = {}
        next_index = 0
        for p in paths:
            png = _find_png(p)
            if png is None:                  # 缺图分片跳过
                continue
            try:
                with open(p, "rb") as f:
                    root = plistlib.load(f)
            except Exception:                # 坏 plist 跳过,不影响其它分片
                continue
            if not isinstance(root, dict):
                continue
            frames = root.get("frames") or {}
            if isinstance(frames, dict):     # format 2
                items = list(frames.items())
            elif isinstance(frames, list):   # format 3
                items = [(str(fr.get("name") or fr.get("filename") or ""), fr)
                         for fr in frames if isinstance(fr, dict)]
            else:
                continue
            for frame_name, info in items:
                if not isinstance(info, dict):
                    continue
                parsed = parse_frame(info)
                if parsed is None:
                    continue
                idx = frame_index(frame_name)
                if idx is None:              # 无名帧:按出现顺序兜底
                    idx = next_index
                self._frames[idx] = (png, parsed)
                next_index = max(next_index, idx + 1)
        self._count = max(self._frames) + 1 if self._frames else 0

    @staticmethod
    def _shard_no(path: Path) -> tuple[int, str]:
        """分片排序键:obj84_0、obj84_1 …(无编号的排最前)。"""
        m = _SHARD_RE.search(path.stem)
        return (int(m.group(1)) if m else 0, path.name.lower())

    @property
    def count(self) -> int:
        return self._count

    def get_size(self, index: int) -> tuple[int, int] | None:
        """原图尺寸(sourceSize);缺失/非法返回 None。"""
        entry = self._frames.get(index)
        if entry is None:
            return None
        w, h = entry[1]["size"]
        return (w, h) if w > 0 and h > 0 else None

    def get_pxpy(self, index: int) -> tuple[int, int]:
        """plist 的 offset 是裁边偏移,不是 wzl 图头绘制偏移 → (0, 0)。"""
        return (0, 0)

    def get_image(self, index: int) -> np.ndarray | None:
        """解码为 (h, w, 4) uint8 RGBA(带缓存);缺失返回 None。"""
        if index in self._image_cache:
            return self._image_cache[index]
        img = self._decode(index)
        self._image_cache[index] = img
        return img

    def _decode(self, index: int) -> np.ndarray | None:
        entry = self._frames.get(index)
        if entry is None:
            return None
        png, info = entry
        cx, cy, cw, ch = info["color"]
        if cw <= 0 or ch <= 0:
            return None
        atlas = self._atlas(png)
        if atlas is None:
            return None

        fx, fy, fw, fh = info["frame"]
        if info["rotated"]:
            # 旋转存储:图集内矩形宽高互换,取出后转回原来的方向
            sprite = atlas.crop((fx, fy, fx + fh, fy + fw))
            sprite = sprite.transpose(Image.Transpose.ROTATE_90)
        else:
            sprite = atlas.crop((fx, fy, fx + fw, fy + fh))
        tile = np.asarray(sprite.convert("RGBA"))

        # 还原原始尺寸:按 sourceColorRect/offset 贴回透明画布
        sw, sh = info["size"]
        canvas = np.zeros((sh, sw, 4), np.uint8)
        ox, oy = info["offset"]
        px = (sw - cw) // 2 + ox
        py = (sh - ch) // 2 - oy
        h, w = tile.shape[:2]
        x0, y0 = max(px, 0), max(py, 0)
        x1, y1 = min(px + w, sw), min(py + h, sh)
        if x0 < x1 and y0 < y1:
            canvas[y0:y1, x0:x1] = tile[y0 - py:y1 - py, x0 - px:x1 - px]
        return canvas

    def _atlas(self, png: Path) -> Image.Image | None:
        """打开分片图集(RGBA,LRU 缓存),失败返回 None。"""
        im = self._atlas_cache.get(png)
        if im is not None:
            self._atlas_cache.move_to_end(png)
            return im
        try:
            with Image.open(png) as src:
                im = src.convert("RGBA")
        except Exception:
            return None
        self._atlas_cache[png] = im
        if len(self._atlas_cache) > _MAX_ATLAS_CACHE:
            _, old = self._atlas_cache.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
        return im

    def clear_cache(self) -> None:
        self._image_cache.clear()

    def close(self) -> None:
        self.clear_cache()
        for im in self._atlas_cache.values():
            try:
                im.close()
            except Exception:
                pass
        self._atlas_cache.clear()
