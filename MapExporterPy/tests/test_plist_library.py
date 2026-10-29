"""plist_library 单元测试:合成 png+plist 图集验证解析、裁剪还原与资源扫描。"""

import plistlib

import numpy as np
from PIL import Image

from main import scan_libraries, slot_of
from map_py.plist_library import PlistLibrary, frame_index


def _frame(frame=(0, 0, 4, 4), offset=(0, 0), rotated=False,
           source_size=None, source_color=None):
    """构造一帧 plist 元信息(frame=(x,y,w,h))。"""
    fx, fy, fw, fh = frame
    sw, sh = source_size or (fw, fh)
    cx, cy, cw, ch = source_color or (0, 0, fw, fh)
    return {
        "frame": f"{{{{{fx},{fy}}},{{{fw},{fh}}}}}",
        "offset": f"{{{offset[0]},{offset[1]}}}",
        "rotated": rotated,
        "sourceColorRect": f"{{{{{cx},{cy}}},{{{cw},{ch}}}}}",
        "sourceSize": f"{{{sw},{sh}}}",
    }


def _write_atlas(directory, stem, frames, image, shard=0):
    """写 {stem}_{shard}.plist + .png,frames 为 dict(format 2)或 list(format 3)。"""
    name = f"{stem}_{shard}"
    image.save(directory / f"{name}.png")
    fmt = 2 if isinstance(frames, dict) else 3
    with open(directory / f"{name}.plist", "wb") as f:
        plistlib.dump({"frames": frames,
                       "metadata": {"format": fmt,
                                    "size": f"{{{image.width},{image.height}}}"}}, f)
    return directory / f"{name}.plist"


# ---------------- 索引 / 尺寸 ----------------

def test_frame_index():
    assert frame_index("obj84_000000.png") == 0
    assert frame_index("tiles84_000573.png") == 573
    assert frame_index("000012.png") == 12
    assert frame_index("no_number.png") is None


def test_index_gap_and_size(tmp_path):
    image = Image.fromarray(np.zeros((8, 8, 4), np.uint8))
    frames = {f"obj84_{i:06d}.png": _frame(source_size=(4, 6)) for i in (0, 5)}
    lib = PlistLibrary([_write_atlas(tmp_path, "obj84", frames, image)])

    assert lib.count == 6                    # max(索引)+1,允许空洞
    assert lib.get_size(0) == (4, 6)         # sourceSize
    assert lib.get_size(5) == (4, 6)
    assert lib.get_size(2) is None           # 空洞
    assert lib.get_size(6) is None           # 越界
    lib.close()


def test_multi_shard_single_index_space(tmp_path):
    image = Image.fromarray(np.zeros((8, 8, 4), np.uint8))
    p0 = _write_atlas(tmp_path, "obj84", {"obj84_000000.png": _frame()}, image, shard=0)
    p1 = _write_atlas(tmp_path, "obj84", {"obj84_000002.png": _frame()}, image, shard=1)
    lib = PlistLibrary([p1, p0])             # 乱序传入也按分片号合并

    assert lib.name == "obj84"
    assert lib.count == 3
    assert lib.get_size(0) is not None
    assert lib.get_size(2) is not None
    lib.close()


# ---------------- 裁剪还原 ----------------

def test_crop_and_restore_source_size(tmp_path):
    # frame {{2,3},{4,6}} 位于图集内,sourceSize 8x8 → 居中贴回 (2,1)
    atlas = np.zeros((16, 16, 4), np.uint8)
    atlas[3:9, 2:6] = (10, 20, 30, 255)
    lib = PlistLibrary([_write_atlas(
        tmp_path, "obj84",
        {"obj84_000000.png": _frame(frame=(2, 3, 4, 6), source_size=(8, 8))},
        Image.fromarray(atlas))])

    out = lib.get_image(0)
    assert out.shape == (8, 8, 4)
    np.testing.assert_array_equal(out[1:7, 2:6], atlas[3:9, 2:6])
    assert out[0].max() == 0 and out[7].max() == 0     # 画布其余透明
    lib.close()


def test_trim_offset(tmp_path):
    # 裁边:sourceColorRect 4x4 + offset(1,-2) → 贴在 (4,5)
    atlas = np.zeros((16, 16, 4), np.uint8)
    atlas[0:4, 0:4] = (255, 0, 0, 255)
    lib = PlistLibrary([_write_atlas(
        tmp_path, "obj84",
        {"obj84_000000.png": _frame(frame=(0, 0, 4, 4), source_size=(10, 10),
                                    offset=(1, -2))},
        Image.fromarray(atlas))])

    out = lib.get_image(0)
    assert out.shape == (10, 10, 4)
    np.testing.assert_array_equal(out[5:9, 4:8], atlas[0:4, 0:4])
    assert out[4, 4].max() == 0
    lib.close()


def test_rotated_frame(tmp_path):
    # 显示尺寸 4x2,图集中按 2x4 旋转存储;取出后按 PIL ROTATE_90 逆时针还原
    atlas = np.zeros((4, 2, 4), np.uint8)
    for y in range(4):
        for x in range(2):
            atlas[y, x] = (y * 2 + x + 1, 0, 0, 255)
    lib = PlistLibrary([_write_atlas(
        tmp_path, "obj84",
        {"obj84_000000.png": _frame(frame=(0, 0, 4, 2), rotated=True,
                                    source_size=(4, 2))},
        Image.fromarray(atlas))])

    out = lib.get_image(0)
    assert out.shape == (2, 4, 4)
    np.testing.assert_array_equal(out[0, :, 0], [2, 4, 6, 8])   # 原右列
    np.testing.assert_array_equal(out[1, :, 0], [1, 3, 5, 7])   # 原左列
    lib.close()


# ---------------- 缓存 / 越界 / 容错 ----------------

def test_cache_and_bounds(tmp_path):
    image = Image.fromarray(np.zeros((8, 8, 4), np.uint8))
    lib = PlistLibrary([_write_atlas(
        tmp_path, "obj84", {"obj84_000000.png": _frame()}, image)])

    first = lib.get_image(0)
    assert lib.get_image(0) is first          # 帧缓存
    lib.clear_cache()
    assert lib.get_image(0) is not first

    assert lib.get_image(-1) is None
    assert lib.get_image(9) is None
    assert lib.get_pxpy(0) == (0, 0)
    lib.close()


def test_bad_plist_and_missing_png(tmp_path):
    image = Image.fromarray(np.zeros((8, 8, 4), np.uint8))
    good = _write_atlas(tmp_path, "good", {"good_000007.png": _frame()}, image)
    bad = tmp_path / "bad_0.plist"
    bad.write_text("not a plist", "utf-8")
    Image.new("RGBA", (8, 8)).save(tmp_path / "bad_0.png")
    missing = _write_atlas(tmp_path, "missing", {"missing_000003.png": _frame()}, image)
    (tmp_path / "missing_0.png").unlink()

    lib = PlistLibrary([good, bad, missing])
    assert lib.count == 8                     # good 的索引 7 → count 8,其它分片跳过
    assert lib.get_size(7) is not None
    assert lib.get_image(0) is None
    lib.close()


# ---------------- format 3 ----------------

def test_format3_list_frames(tmp_path):
    image = Image.fromarray(np.zeros((8, 8, 4), np.uint8))
    frames = [{
        "filename": "obj84_000003.png",
        "frame": "{{0,0},{4,4}}",
        "rotated": False,
        "sourceColorRect": "{{0,0},{4,4}}",
        "sourceSize": "{4,4}",
        "offset": "{0,0}",
    }]
    lib = PlistLibrary([_write_atlas(tmp_path, "obj84", frames, image)])

    assert lib.count == 4                     # frames 为 list 时按 filename 取索引
    assert lib.get_size(3) == (4, 4)
    assert lib.get_image(3) is not None
    lib.close()


# ---------------- scan_libraries ----------------

def test_slot_mapping_obj_prefix():
    assert slot_of("obj84") == 203
    assert slot_of("objects84") == 203
    assert slot_of("Obj84") == 203
    assert slot_of("tiles84") == 183
    assert slot_of("smtiles84") == 193


def test_scan_plist_preferred_over_wzl(tmp_path):
    # obj84/ 下是 png+plist 图集,同目录还有同名 wzl/wzx:plist 优先且不被 PngLibrary 误占
    res = tmp_path / "obj84"
    res.mkdir()
    image = Image.new("RGBA", (8, 8), (1, 2, 3, 255))
    _write_atlas(res, "obj84", {"obj84_000000.png": _frame()}, image)
    (res / "obj84.wzl").write_bytes(b"\x00" * 64)
    (res / "obj84.wzx").write_bytes(b"\x00" * 48)

    libs = scan_libraries(tmp_path)
    assert 203 in libs
    assert isinstance(libs[203], PlistLibrary)
    assert libs[203].count == 1
    libs[203].close()
