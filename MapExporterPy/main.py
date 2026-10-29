"""地图导出工具 CLI。

用法:
  python main.py <map文件或目录> --lib-dir <资源目录> -o <输出目录>
  python main.py --gui                       # 打开图形界面

资源扫描:--lib-dir 下递归查找(子目录中的资源同样识别),按文件名映射槽位:
  Tiles/SmTiles/Objects/obj 前缀(数字后缀可选)→ 槽位 100+偏移+n-1
  格式:数字图片目录(PNG/JPG/BMP)优先,其次 png+plist 图集(obj84_0.plist/png …),
       再 wzl/wzx → wil/wix → pak
输出(单张完整大图,无 Unity 16384 分块限制):
  {out}/{mapName}/{mapName}.png + 可选动画序列帧
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

from map_py.map_parser import MapReader, MapParseError
from map_py.plist_library import PlistLibrary
from map_py.renderer import RenderConfig, Renderer
from map_py.wil_library import MLibrary, PakLibrary, PngLibrary, WilLibrary, _IMG_EXTS

# 数字后缀可选:经典资源不带数字(Tiles/SmTiles/Objects),扩展资源带数字(Tiles222)
RES_PATTERNS = [
    # obj84 / object84 / objects84 都视为 Objects 资源组
    (re.compile(r"^(objects?|objs?)(\d*)$", re.I), 20),
    (re.compile(r"^(smtiles)(\d*)$", re.I), 10),
    (re.compile(r"^(tiles)(\d*)$", re.I), 0),
]

DEFAULT_INDEX = 100      # MapTools.DEFAULT_INDEX

# 资源目录递归深度:wil/wix 可能在数据目录更深层级(如 Data/Map/0/xxx)
MAX_SCAN_DEPTH = 4


def slot_of(name: str) -> int | None:
    """资源名 → 槽位。无数字后缀按第 1 组:Tiles→100, SmTiles→110, Objects→120。"""
    for pat, offset in RES_PATTERNS:
        m = pat.match(name)
        if m:
            n = int(m.group(2)) if m.group(2) else 1
            return DEFAULT_INDEX + offset + n - 1
    return None


def _walk_entries(lib_dir: Path, max_depth: int):
    """递归遍历目录树,产出 (depth, dir, files);BFS 浅层优先。

    目录不可读或超出 max_depth 的子树不再深入(避免扫到无关深目录)。
    用 os.scandir 的目录项缓存判断类型,避免每个文件再做一次 stat ——
    Windows 上两万文件的目录能省 1 秒以上。"""
    stack = [(Path(lib_dir), 0)]
    while stack:
        d, depth = stack.pop(0)
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name.lower())
        except OSError:
            continue
        subdirs, files = [], []
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    subdirs.append(Path(e.path))
                else:
                    files.append(Path(e.path))
            except OSError:
                continue
        yield depth, d, files
        if depth < max_depth:
            for sd in subdirs:
                stack.append((sd, depth + 1))


_PLIST_SHARD_RE = re.compile(r"^(.+)_(\d+)$")     # obj84_0.plist → obj84


def _has_numbered_images(files: list[Path]) -> bool:
    """目录内是否有数字命名图片(00000.png / 00000.PNG …)。"""
    return any(f.suffix.lower() in _IMG_EXTS and re.match(r"\d+\.", f.name)
               for f in files)


def scan_libraries(lib_dir: str | Path, max_depth: int = MAX_SCAN_DEPTH,
                   ) -> dict[int, MLibrary | PngLibrary | PlistLibrary]:
    """扫描资源目录(递归),按文件名 → 槽位映射加载资源库。

    逐槽位独立选择:数字图片目录优先,其次 png+plist 图集,缺失槽位再用
    wzl/wzx → wil/wix → pak 二进制兜底。子目录中的资源同样识别,
    同槽位先到先得(浅层优先)。预览与导出共用,规则一致。

    目录树只遍历一次(五个阶段共用结果),避免大目录被反复扫描。"""
    lib_dir = Path(lib_dir)
    libs: dict[int, MLibrary | PngLibrary | PlistLibrary] = {}

    def add(slot: int, lib) -> None:
        libs.setdefault(slot, lib)          # 浅层优先:已占用槽位不再覆盖

    entries = list(_walk_entries(lib_dir, max_depth))
    wzl: list[Path] = []
    wil: list[Path] = []
    pak: list[Path] = []
    for _, _, files in entries:
        for f in files:
            suffix = f.suffix.lower()
            if suffix == ".wzl":
                wzl.append(f)
            elif suffix == ".wil":
                wil.append(f)
            elif suffix == ".pak":
                pak.append(f)

    # 1. 数字图片目录(png/jpg/bmp,大小写不敏感)优先
    for _, d, files in entries:
        slot = slot_of(d.name)
        if slot is not None and _has_numbered_images(files):
            add(slot, PngLibrary(str(d)))
    # 2. png+plist 图集(分片 obj84_0.plist / obj84_1.plist 合并为一个资源库)
    for _, _, files in entries:
        groups: dict[str, list[Path]] = {}
        for f in files:
            if f.suffix.lower() != ".plist":
                continue
            m = _PLIST_SHARD_RE.match(f.stem)
            base = m.group(1) if m else f.stem
            if slot_of(base) is not None:
                groups.setdefault(base, []).append(f)
        for base, plist_files in groups.items():
            slot = slot_of(base)
            if slot is None or slot in libs:   # 数字图片目录已优先占用
                continue
            lib = PlistLibrary(plist_files)
            if lib.count:                   # 缺同名 png 的组不占槽位
                add(slot, lib)
            else:
                lib.close()
    # 3. wzl 兜底缺失槽位(24bit,大小写不敏感,真实文件可能是 Objects222.Wzl)
    for f in wzl:
        slot = slot_of(f.stem)
        if slot is not None:
            add(slot, MLibrary(str(f.with_suffix(""))))
    # 4. wil 兜底(旧版调色板/16bit)
    for f in wil:
        slot = slot_of(f.stem)
        if slot is not None:
            add(slot, WilLibrary(str(f.with_suffix(""))))
    # 5. pak 兜底(GEE 引擎 .GEEPAK3)
    for f in pak:
        slot = slot_of(f.stem)
        if slot is not None:
            add(slot, PakLibrary(str(f.with_suffix(""))))
    return libs


def export_map(map_path: str | Path, libs: dict[int, MLibrary], cfg: RenderConfig,
               progress=None) -> str:
    """导出单张地图,返回导出名。"""
    reader = MapReader(map_path)
    renderer = Renderer(reader, libs, cfg, progress)
    renderer.run()
    return cfg.map_name or reader.map_name


def export_maps(map_paths: list[str | Path], libs, cfg: RenderConfig, verbose=False):
    t_start = time.time()
    for p in map_paths:
        if verbose:
            def progress(cur, total, msg, _p=p):
                if total:
                    print(f"\r  {_p.stem}: {msg}{cur}/{total}", end="", flush=True)
        else:
            progress = None
        try:
            t0 = time.time()
            name = export_map(p, libs, cfg, progress)
            cost = time.time() - t0
            if verbose:
                print(f"\r  {name}: 导出完成 ({_fmt_time(cost)})")
            else:
                print(f"导出完成: {name} ({_fmt_time(cost)})")
        except (MapParseError, FileNotFoundError) as e:
            print(f"跳过 {Path(p).name}: {e}", file=sys.stderr)
    print(f"总耗时: {_fmt_time(time.time() - t_start)}")


def _fmt_time(seconds: float) -> str:
    """耗时格式化:小于 1 分钟显示秒,否则 分+秒。"""
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    return f"{int(seconds // 60)} 分 {seconds % 60:.0f} 秒"


def collect_maps(arg: str) -> list[Path]:
    """收集 .map 文件:目录递归查找(与资源扫描一致,支持深层子目录)。"""
    p = Path(arg)
    if p.is_dir():
        return sorted(p.glob("**/*.map"))
    return [p]


def main(argv=None) -> int:
    # Windows GBK 控制台兼容:无法编码的字符不崩溃
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="地图导出工具",
        description="Mir2 地图二进制(.map + 图片目录、png/plist 图集、wzl/wzx、wil/wix、"
                    "pak 资源库)导出为大图 PNG")
    parser.add_argument("maps", nargs="*", help=".map 文件或目录(可多个)")
    parser.add_argument("--lib-dir", "-l",
                        help="资源目录(递归扫描 Tiles/SmTiles/Objects/obj 的图片目录、"
                             "png+plist 图集或 wzl/wil/pak)")
    parser.add_argument("--out", "-o", default="output", help="输出根目录(默认 output)")
    parser.add_argument("--gui", action="store_true", help="打开图形界面")
    parser.add_argument("--name", help="导出地图名(默认取 .map 文件名)")
    parser.add_argument("--anim", action="store_true", help="导出动画序列帧(默认不导出)")
    parser.add_argument("--format", default="jpg", choices=["jpg", "png"], help="大图格式(默认 jpg)")
    parser.add_argument("--quality", type=int, default=90, help="jpg 品质(默认 90)")
    args = parser.parse_args(argv)

    if args.gui or not args.maps:
        from gui import run_gui
        return run_gui()

    if not args.lib_dir:
        # 未指定资源目录:单个目录参数时自动使用该目录(自动检测 PNG/wzl)
        dirs = [Path(a) for a in args.maps if Path(a).is_dir()]
        if len(dirs) == 1:
            args.lib_dir = dirs[0]
        else:
            parser.error("缺少 --lib-dir 资源目录")

    libs = scan_libraries(args.lib_dir)
    if not libs:
        print("警告:资源目录中未找到 Tiles/SmTiles/Objects 的资源(图片目录或 wzl/wil/pak)",
              file=sys.stderr)

    maps = [m for arg in args.maps for m in collect_maps(arg)]
    if not maps:
        parser.error("未找到 .map 文件")
    cfg = RenderConfig(out_root=Path(args.out), map_name=args.name,
                       export_anim=args.anim, img_format=args.format,
                       jpg_quality=args.quality)
    export_maps(maps, libs, cfg, verbose=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
