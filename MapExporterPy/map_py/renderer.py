"""地图渲染与导出。

复刻 C# 版 Assets/Scripts/Map/MapTools.cs + MapBlock.cs:
- 三层绘制:DrawBack(偶数格) / DrawMidd / DrawFront(大物体底部对齐、门补画)
- 预乘 Alpha 混合(SetMapColor / MapBlock.SetColor)
- 直接输出单张完整大图(不按 C# 的 Unity 16384 分块;Python/PIL 无此限制)
- 输出目录与 C# 版一致:{out}/Maps/map/tiles/{mapName}/、{out}/Maps/map/Json/
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .map_parser import CELL_HEIGHT, CELL_WIDTH

# 标准瓦片尺寸(C# DrawMidd/Front 的大物体判断)
_TILE_SIZES = ((CELL_WIDTH, CELL_HEIGHT), (CELL_WIDTH * 2, CELL_HEIGHT * 2))


@dataclass
class RenderConfig:
    out_root: Path
    map_name: str | None = None        # 导出地图名(默认取 .map 文件名)
    export_anim: bool = False          # 是否导出动画序列帧
    img_format: str = "jpg"            # 大图格式:jpg / png(默认 jpg)
    jpg_quality: int = 90              # jpg 品质(1-100)
    bg_color: tuple[int, int, int] = (0, 0, 0)   # jpg 透明背景色(默认黑)
    preview: bool = False          # 预览模式:跳过 alpha 混合(快速渲染)


class Renderer:
    """reader + libs(槽位 dict) → 输出 PNG/JSON。"""

    def __init__(self, reader, libs: dict, cfg: RenderConfig, progress=None) -> None:
        self._reader = reader
        self._libs = libs
        self._cfg = cfg
        self._progress = progress or (lambda cur, total, msg: None)
        self._ops = []                 # 全部绘制操作,按 Back→Midd→Front 顺序
        self._animations = []          # 动画数据(lib, img, x, y, anim 帧数)
        self._alpha_kind: dict[tuple[int, int], int] = {}   # (lib,img) → alpha 类型缓存
        # 0=全透明 1=全不透明 2=二元(0/255) 3=半透明;类型是瓦片固有属性,缓存免重复扫描

    # ---------------- 公共入口 ----------------

    def run(self) -> None:
        pw, ph = self._reader.pixel_width, self._reader.pixel_height
        self._progress(0, 1, "解析绘制操作...")
        self._collect_ops()
        total = len(self._ops)
        steps = total + 2               # 绘制 + 保存 + 动画/JSON 收尾

        buf = np.zeros((ph, pw, 4), np.uint8)
        for i, op in enumerate(self._ops):
            self._blend_into(buf, op)
            if i % 10 == 0:
                self._progress(i, steps, "绘制中...")
        self._progress(total, steps, f"保存 {self._cfg.img_format.upper()}...")
        self._save_texture(buf, self.export_name)
        del buf                                  # 释放 6.1GB 渲染缓冲
        # 动画 JSON 与序列帧:仅勾选"导出动画"时输出
        if self._cfg.export_anim:
            self._progress(total + 1, steps, "导出动画...")
            self._save_animations()
            self._save_json()
        self._progress(steps, steps, "完成")

    @property
    def export_name(self) -> str:
        """导出名:配置覆盖或 .map 文件名。"""
        return self._cfg.map_name or self._reader.map_name

    # ---------------- 操作收集(严格复刻三层循环) ----------------

    def _collect_ops(self) -> None:
        cells = self._reader.cells
        w, h = self._reader.width, self._reader.height
        libs = self._libs
        ops = self._ops
        append = ops.append
        anims = self._animations
        CW, CH = CELL_WIDTH, CELL_HEIGHT

        def check(lib: int, img: int):
            """内联 _check:越界检查 + 尺寸头,返回 (lib, img, size) 或 None。
            (绘制不用 pxpy,省掉 get_pxpy 调用)"""
            if not 0 <= lib < 400:
                return None
            lib_obj = libs.get(lib)
            if lib_obj is None or not 0 <= img < lib_obj.count:
                return None
            size = lib_obj.get_size(img)
            return (lib, img, size) if size is not None else None

        # DrawBack(MapTools.cs:282-350):只画偶数 x/y 格;y 降序
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                cell = cells[x, y]
                # (BackImage & 0x1FFFFFFF) - 1:bit29 是隐藏标志
                img = (int(cell["back_image"]) & 0x1FFFFFFF) - 1
                lib = int(cell["back_index"])
                info = check(lib, img)
                if info is not None:
                    _, _, size = info
                    append((lib, img, x * CW, y * CH, size[0], size[1]))

        # DrawMidd(MapTools.cs:352-415):全格;动画帧推进(非恒 0)
        for y in range(0, h):
            for x in range(0, w):
                cell = cells[x, y]
                img = int(cell["middle_image"]) - 1
                lib = int(cell["middle_index"])
                anim = int(cell["middle_anim_frame"])
                if 0 < anim < 255:
                    if (anim & 0x0F) > 0:
                        anim &= 0x0F
                    if anim > 0:
                        tick = int(cell["middle_anim_tick"])
                        img += (1 % (anim + anim * tick)) // (1 + tick)
                dx = x * CW
                info = check(lib, img)
                if info is None:
                    continue
                size = info[2]
                if size not in _TILE_SIZES:          # 大物体底部对齐
                    dy = (y + 1) * CH - size[1]
                else:
                    dy = y * CH
                append((lib, img, dx, dy, size[0], size[1]))

        # DrawFront(MapTools.cs:417-530):全格;blend 标志;动画推进;门补画
        # 动画大物体记录到 animationDataList(C# DrawFront isAnimation 规则):
        #   blend → 记录 + skip 不画;非 blend → 记录 + 正常画
        for y in range(0, h):
            for x in range(0, w):
                cell = cells[x, y]
                img = (int(cell["front_image"]) & 0x7FFF) - 1   # bit15 混合标志
                lib = int(cell["front_index"])
                if lib == 0:
                    # 12 字节旧格式:无索引字段,front 槽位 = 120 + area(Objects{area+1})
                    lib = 120 + int(cell["area"])
                dx = x * CW
                anim = int(cell["front_anim_frame"])
                blend = (anim & 0x80) > 0
                animation = anim & 0x7F
                if animation > 0:
                    tick = int(cell["front_anim_tick"])
                    img += (1 % (animation + animation * tick)) // (1 + tick)
                door_offset = int(cell["door_offset"])
                info = check(lib, img)
                if info is None:
                    continue
                size = info[2]

                if size not in _TILE_SIZES:          # 大物体
                    if animation > 0:
                        # C#:新盛大地图(libIndex 100-199)用 drawY-3*32,否则 drawY-s.Height
                        anim_y = (y + 1) * CH - \
                            (3 * CH if 100 < lib < 199 else size[1])
                        anims.append((lib, img, dx, anim_y, animation))
                        if blend:
                            skip_main = True          # 只记录动画,不画到大图
                        else:
                            dy = anim_y
                            skip_main = False
                    else:
                        dy = (y + 1) * CH - size[1]
                        skip_main = False
                else:
                    dy = y * CH
                    skip_main = False
                if not skip_main:
                    append((lib, img, dx, dy, size[0], size[1]))

                # 显示门打开:补画 index+DoorOffset(不受 blend skip 影响)
                if door_offset > 0:
                    info2 = check(lib, img + door_offset)
                    if info2 is not None:
                        size2 = info2[2]
                        append((lib, img + door_offset, dx,
                                (y + 1) * CH - size2[1], size2[0], size2[1]))

    # ---------------- 混合 ----------------

    def _blend_into(self, buf: np.ndarray, op, origin=(0, 0)) -> None:
        """单次预乘 Alpha 混合(C# SetMapColor / MapBlock.SetColor)。
        origin = 缓冲左上角的全局像素坐标。
        op 第 7 个元素 = blend 标志:混合算法(去黑 alpha=max 通道 + over)。

        快速路径:瓦片 alpha 全 0 → 跳过;全 255 → over 混合结果 = 原像素,
        直接覆盖(省掉整片 float 混合)。仅半透明瓦片走 float 路径。"""
        oy, ox = origin
        lib, img, dx, dy, w, h = op[:6]
        tile = self._libs[lib].get_image(img)
        if tile is None:
            return
        # C# SetMapColor:瓦片顶部(GetPixel j=h-1)落在图像行 drawY,
        # 即瓦片正立放在 drawY(Unity 纹理 y=0 是底部,PNG 行 0 是顶部,
        # 经 SetPixel 的 y = PH-drawY-h+j 与 EncodeToPNG 两次翻转后等效直放)
        ty = dy
        # 与缓冲(局部坐标)求交集,越界裁剪(C# 小图路径越界会抛,这里容错)
        x0, x1 = max(dx - ox, 0), min(dx + w - ox, buf.shape[1])
        y0, y1 = max(ty - oy, 0), min(ty + h - oy, buf.shape[0])
        if x0 >= x1 or y0 >= y1:
            return
        src = tile[y0 - (ty - oy):y1 - (ty - oy), x0 - (dx - ox):x1 - (dx - ox)]
        dst = buf[y0:y1, x0:x1]

        if self._cfg.preview:
            # 预览模式:跳过 Alpha 混合,不透明像素直接覆盖(快速渲染)
            mask = src.any(axis=2)
            if not mask.any():
                return
            dst2 = dst.copy()
            dst2[..., :3] = np.where(mask[..., None], src[..., :3], dst[..., :3])
            dst2[..., 3] = np.where(mask, src[..., 3], dst[..., 3])
            buf[y0:y1, x0:x1] = dst2
            return
        kind = self._alpha_kind.get((lib, img))
        if kind is None:
            a_full = tile[..., 3]            # 按整瓦片分类(固有属性,缓存)
            a_min, a_max = int(a_full.min()), int(a_full.max())
            if a_max == 0:
                kind = 0                     # 全透明
            elif a_min == 255:
                kind = 1                     # 全不透明:over 结果 = 原像素
            elif not ((a_full > 0) & (a_full < 255)).any():
                kind = 2                     # 二元 alpha(0/255,调色板瓦片)
            else:
                kind = 3                     # 半透明,需 float 混合
            self._alpha_kind[(lib, img)] = kind
        if kind == 0:
            return
        if kind == 1:
            dst[...] = src
            return
        mask = src[..., 3] != 0              # src 透明像素混合结果 = dst
        if kind == 2:
            np.copyto(dst, src, where=mask[..., None])   # 就地掩码拷贝(快于 fancy index)
            return
        s = src.astype(np.float32) / 255.0
        d = dst.astype(np.float32) / 255.0
        sa = s[..., 3:4]
        da = d[..., 3:4]
        out_a = sa + da * (1.0 - sa)
        rgb = (s[..., :3] * sa + d[..., :3] * da * (1.0 - sa)) / np.maximum(out_a, 1e-30)
        new = np.concatenate([rgb, out_a], -1)
        # Unity SetPixel 量化:trunc(x*255+0.5)
        out_u8 = np.trunc(np.clip(new, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        result = dst.copy()
        result[mask] = out_u8[mask]
        buf[y0:y1, x0:x1] = result

    # ---------------- 输出 ----------------

    def _save_texture(self, buf: np.ndarray, name: str) -> None:
        """保存大图:jpg(默认,透明合背景)或 png。

        内存控制:RGB 拷贝完成后立即释放渲染缓冲,避免
        6.1GB(buf) + 4.6GB(rgb) 同时驻留导致换页。"""
        fmt = self._cfg.img_format.lower()
        path = self._tiles_dir / f"{name}.{fmt}"
        if fmt == "jpg":
            # JPEG 无 alpha:透明像素合成背景色
            alpha = buf[..., 3]
            rgb = buf[..., :3].copy()
            if not (alpha == 255).all():
                rgb[alpha == 0] = self._cfg.bg_color
            del buf                        # 释放渲染缓冲(峰值内存减半)
            Image.fromarray(rgb, "RGB").save(path, quality=self._cfg.jpg_quality)
        else:
            Image.fromarray(buf, "RGBA").save(path)   # fromarray 零拷贝视图

    def _save_json(self) -> None:
        """动画 JSON(animationDataList,C# JsonConvert 序列化),与大图同目录。
        文件名为 {导出名}_anim.json。"""
        anim_json = json.dumps(
            [{"animationName": f"{img:06d}", "x": x, "y": y}
             for _, img, x, y, _ in self._animations],
            separators=(",", ":"))
        (self._json_dir / f"{self.export_name}_anim.json").write_text(anim_json, "utf-8")

    def _save_animations(self) -> None:
        """导出动画序列帧与定位文件(参考 C# 导出规则):

        {out}/{mapName}/anims/{mapName}_{img:06d}/
            50000+k.png            # 帧图 = 资源库 index+k(k=0..动画帧数-1)
            Placements/50000+k.txt # 两行:图头 px、py(绘制偏移)
        """
        anim_root = self._cfg.out_root / self.export_name / "anims"
        for lib, img, x, y, anim in self._animations:
            lib_obj = self._libs.get(lib)
            if lib_obj is None:
                continue
            folder = anim_root / f"{self.export_name}_{img:06d}"
            folder.mkdir(parents=True, exist_ok=True)
            placements = folder / "Placements"
            placements.mkdir(parents=True, exist_ok=True)
            for k in range(anim):
                frame = img + k
                if not 0 <= frame < lib_obj.count:
                    continue
                tile = lib_obj.get_image(frame)
                if tile is None:
                    continue
                px, py = lib_obj.get_pxpy(frame)
                Image.fromarray(tile).save(folder / f"{50000 + k}.png")
                (placements / f"{50000 + k}.txt").write_text(f"{px}\n{py}", "utf-8")

    @property
    def _tiles_dir(self) -> Path:
        # 简化路径:{out}/{导出名}/(用户要求去除深路径)
        p = self._cfg.out_root / self.export_name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def _json_dir(self) -> Path:
        return self._tiles_dir
