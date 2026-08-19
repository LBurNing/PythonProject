"""地图导出工具 CLI。

用法:
  python main.py <map文件或目录> --lib-dir <资源目录> -o <输出目录>
  python main.py --gui                       # 打开图形界面

资源扫描:--lib-dir 下按文件名前缀映射槽位(C# MapResData.Index):
  Tiles 数字    → 100 + 0 + n - 1
  SmTiles 数字  → 100 + 10 + n - 1
  Objects 数字  → 100 + 20 + n - 1
输出结构(与 C# 版一致):
  {out}/Maps/map/tiles/{mapName}/{mapName}.png + {mapName}.json
  {out}/Maps/map/Json/{mapName}.json
"""

import argparse
import re
import sys
from pathlib import Path

from map_py.map_parser import MapReader, MapParseError
from map_py.renderer import RenderConfig, Renderer
from map_py.wil_library import MLibrary, PngLibrary

RES_PATTERNS = [
    (re.compile(r"^(objects)(\d+)$", re.I), 20),
    (re.compile(r"^(smtiles)(\d+)$", re.I), 10),
    (re.compile(r"^(tiles)(\d+)$", re.I), 0),
]

DEFAULT_INDEX = 100      # MapTools.DEFAULT_INDEX


def scan_libraries(lib_dir: str | Path) -> dict[int, MLibrary | PngLibrary]:
    """扫描资源目录,按文件名 → 槽位映射加载资源库。

    优先 PNG 小块目录(读取本地图片);PNG 缺失时用 wzl/wzx 二进制兜底。"""
    lib_dir = Path(lib_dir)
    libs: dict[int, MLibrary | PngLibrary] = {}

    def slot_of(name: str) -> int | None:
        for pat, offset in RES_PATTERNS:
            m = pat.match(name)
            if m:
                return DEFAULT_INDEX + offset + int(m.group(2)) - 1
        return None

    for d in sorted(lib_dir.iterdir()):
        if d.is_dir():
            slot = slot_of(d.name)
            if slot is not None and (any(d.glob("*.PNG")) or any(d.glob("*.png"))):
                libs[slot] = PngLibrary(str(d))
    if libs:
        return libs
    for wzl in sorted(lib_dir.glob("*.wzl")):
        slot = slot_of(wzl.stem)
        if slot is not None:
            libs[slot] = MLibrary(str(wzl.with_suffix("")))
    return libs


def export_map(map_path: str | Path, libs: dict[int, MLibrary], out_root: str | Path,
               progress=None) -> str:
    """导出单张地图,返回地图名。"""
    reader = MapReader(map_path)
    cfg = RenderConfig(out_root=Path(out_root))
    renderer = Renderer(reader, libs, cfg, progress)
    renderer.run()
    return reader.map_name


def export_maps(map_paths: list[str | Path], libs, out_root, verbose=False):
    for p in map_paths:
        if verbose:
            def progress(cur, total, msg, _p=p):
                if total:
                    print(f"\r  {_p.stem}: {msg}{cur}/{total}", end="", flush=True)
        else:
            progress = None
        try:
            name = export_map(p, libs, out_root, progress)
            if verbose:
                print(f"\r  {name}: 导出完成")
            else:
                print(f"导出完成: {name}")
        except (MapParseError, FileNotFoundError) as e:
            print(f"跳过 {Path(p).name}: {e}", file=sys.stderr)


def collect_maps(arg: str) -> list[Path]:
    p = Path(arg)
    if p.is_dir():
        return sorted(p.glob("*.map"))
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
        description="Mir2 地图二进制(.map + .wzl/.wzx 资源库)导出为大图 PNG")
    parser.add_argument("maps", nargs="*", help=".map 文件或目录(可多个)")
    parser.add_argument("--lib-dir", "-l", help="资源目录(含 Tiles/SmTiles/Objects 的 wzl/wzx)")
    parser.add_argument("--out", "-o", default="output", help="输出根目录(默认 output)")
    parser.add_argument("--gui", action="store_true", help="打开图形界面")
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
        print("警告:资源目录中未找到 Tiles/SmTiles/Objects 的 .wzl 文件", file=sys.stderr)

    maps = [m for arg in args.maps for m in collect_maps(arg)]
    if not maps:
        parser.error("未找到 .map 文件")
    export_maps(maps, libs, args.out, verbose=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
