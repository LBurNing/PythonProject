# -*- coding: utf-8 -*-
"""Unity WebGL External 符号表(json: 函数索引 -> 函数名)解析核心。

符号文件格式(Unity External 产物):
    {"0": "__cxa_find_matching_catch_3", "1": "getTempRet0", ...}

崩溃栈格式:
    at wasm-function[21820]:0x685fe8
"""
import json
import re
from pathlib import Path

FUNC_PATTERN = re.compile(r"wasm-function\[(\d+)\]")

DEFAULT_SYMBOL_DIR = Path(r"E:\huanpi\product\client\WebSymbols")


class SymbolTable:
    """加载一份符号表,提供 编号 -> 函数名 查询。"""

    def __init__(self, path):
        self.path = Path(path)
        self.table = {}
        self.loaded_at = None
        self._load()

    def _load(self):
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.table = {
            int(key): value
            for key, value in data.items()
            if isinstance(value, str)
        }

    def __len__(self):
        return len(self.table)

    def lookup(self, func_id):
        return self.table.get(func_id)

    @property
    def name(self):
        return self.path.name


def find_symbol_files(directory=None):
    """在目录中列出符号 json(命名形如 xxx_symbols.json 或 Unity 哈希 json)。"""
    directory = Path(directory) if directory else DEFAULT_SYMBOL_DIR
    if not directory.is_dir():
        return []
    files = []
    for p in sorted(directory.glob("*.json")):
        if p.stat().st_size < 1024:
            continue
        # 内容粗校验:符号表 json 开头是 { 且很快出现 "数字":
        try:
            with open(p, encoding="utf-8") as f:
                head = f.read(2048)
        except Exception:
            continue
        if head.lstrip().startswith("{") and re.search(r'"\d+"\s*:\s*"', head):
            files.append(p)
    return files


def extract_func_ids(text):
    """提取文本中所有 wasm-function[N] 的编号(保持出现顺序)。"""
    return [int(m) for m in FUNC_PATTERN.findall(text)]


def resolve_text(text, symbols):
    """把崩溃栈文本中的每个 wasm-function[N] 翻译成函数名。

    返回 (行列表, 命中数, 未命中数)。相同编号只翻译一次,结果按首次出现顺序排列。
    """
    ids = extract_func_ids(text)
    seen = set()
    lines = []
    miss = 0
    for fid in ids:
        if fid in seen:
            continue
        seen.add(fid)
        name = symbols.lookup(fid)
        if name is not None:
            lines.append(f"wasm-function[{fid}] -> {name}")
        else:
            miss += 1
            lines.append(f"wasm-function[{fid}] -> !!! 未命中(符号表 {symbols.name} 中不存在)")
    return lines, len(seen) - miss, miss
