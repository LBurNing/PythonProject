# -*- coding: utf-8 -*-
"""玩家上报日志的批量符号解析核心(纯逻辑, 不依赖 Qt, 也不 import core)。

日志格式(KLogger, 每行):
    20260921-112538-E: [C#] 消息正文    at http://...:wasm-function[733]:0x82c4d
        at http://...:wasm-function[94973]:0x17e6fcd

- 消息行以 yyyyMMdd-HHmmss-X: 开头, X 为等级字符(U/E/W/I/D)
- 堆栈续行没有等级标记, 继承所属消息行的等级
- 日志里的 wasm 堆栈只有裸索引、没有函数名, 必须查符号表

符号表对象按鸭子类型使用: 需要 .lookup(int)->str|None / len() / .name / .table
(core.SymbolTable 天然满足, 本模块不 import 它)
"""
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

LOG_EXTENSIONS = (".log", ".txt")
MAX_FILE_BYTES = 8 * 1024 * 1024      # 单文件读取上限, 防御误选超大文件
MISS_RATIO_WARN = 0.20                # 未命中率告警阈值
DEFAULT_CONTEXT = 2                   # 上下文视图默认前后行数
REPLACEMENT_CHAR = chr(0xFFFD)        # 解码失败的字节会被 Python 换成此字符

FUNC_RE = re.compile(r"wasm-function\[(\d+)\]")
BUILD_RE = re.compile(r"([0-9a-fA-F]{32})\.wasm\.br")
TS_RE = re.compile(r"^(\d{8})-(\d{6})-([UEWID]):\s?")

LEVEL_NAMES = {"U": "Silence", "E": "Error", "W": "Warning", "I": "Info", "D": "Debug"}
LEVEL_ORDER = ("U", "E", "W", "I", "D")   # 越靠后越啰嗦

VIEW_STACK = "stack"      # 仅含 wasm-function 的行
VIEW_CONTEXT = "context"  # 栈行 ± N 行
VIEW_FULL = "full"        # 完整原文


@dataclass
class FileReport:
    """单个日志文件的解析结果。所有行号一律 1-based。"""

    path: Path = None
    text: str = ""
    lines: list = field(default_factory=list)              # splitlines() 结果
    annotated: list = field(default_factory=list)          # 逐行标注后的行, 与 lines 等长
    line_levels: list = field(default_factory=list)        # 每行等级字符, 无法判定为 None
    stack_line_numbers: list = field(default_factory=list)  # 含栈帧的行号
    id_counter: Counter = field(default_factory=Counter)
    miss_counter: Counter = field(default_factory=Counter)
    level_counter: Counter = field(default_factory=Counter)  # 等级 -> 含栈帧的行数
    build_hashes: Counter = field(default_factory=Counter)
    hits: int = 0
    misses: int = 0
    max_index: int = 0
    truncated: bool = False
    replaced_chars: int = 0
    warnings: list = field(default_factory=list)
    error: str = None

    @property
    def name(self):
        return self.path.name if self.path else "<text>"

    @property
    def unique_ids(self):
        return len(self.id_counter)


@dataclass
class BatchReport:
    """整批日志的聚合结果。"""

    files: list = field(default_factory=list)
    symbol_name: str = ""
    symbol_count: int = 0
    symbol_max_index: int = None
    total_hits: int = 0
    total_misses: int = 0
    total_stack_lines: int = 0
    unique_ids: int = 0
    max_index_in_logs: int = 0
    miss_counter: Counter = field(default_factory=Counter)
    build_hashes: Counter = field(default_factory=Counter)
    warnings: list = field(default_factory=list)
    elapsed: float = 0.0
    cancelled: bool = False

    @property
    def file_count(self):
        return len(self.files)


# ---------------------------------------------------------------- 收集 / 读取

def collect_log_files(paths):
    """把「目录 / 文件 / 路径列表」统一展开成日志文件列表(去重, 按文件名排序)。

    目录只扫一层(非递归)并按扩展名白名单过滤; 显式传入的文件不过滤扩展名。
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]

    found = []
    seen = set()
    for item in paths:
        p = Path(item)
        try:
            if p.is_dir():
                for child in p.iterdir():
                    if child.is_file() and child.suffix.lower() in LOG_EXTENSIONS:
                        key = str(child.resolve()).lower()
                        if key not in seen:
                            seen.add(key)
                            found.append(child)
            elif p.is_file():
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    found.append(p)
        except OSError:
            continue

    found.sort(key=lambda x: x.name)
    return found


def read_log_text(path):
    """读取并解码日志, 返回 (text, truncated, replaced_chars, warnings)。绝不抛解码异常。"""
    raw = Path(path).read_bytes()

    truncated = bool(raw) and not raw.endswith(b"\n")
    warnings = []

    if len(raw) > MAX_FILE_BYTES:
        limit_mb = MAX_FILE_BYTES // 1024 // 1024
        warnings.append(f"文件超过 {limit_mb}MB, 仅解析前 {limit_mb}MB")
        raw = raw[:MAX_FILE_BYTES]

    text = raw.decode("utf-8-sig", errors="replace")

    replaced = text.count(REPLACEMENT_CHAR)
    if replaced:
        warnings.append(f"存在 {replaced} 个无法解码的字节, 已用 U+FFFD 替换")
    if truncated:
        warnings.append("末行疑似被上传截断, 最后一行可能不完整")

    return text, truncated, replaced, warnings


# ---------------------------------------------------------------- 解析

def probe_symbol_range(symbols):
    """探测 (符号表最大索引, 条目数); 取不到最大索引时返回 (None, 条目数)。"""
    if symbols is None:
        return None, 0
    table = getattr(symbols, "table", None)
    if isinstance(table, dict) and table:
        try:
            return max(table), len(table)
        except (TypeError, ValueError):
            pass
    try:
        return None, len(symbols)
    except TypeError:
        return None, 0


def parse_log_text(text, symbols, path=None, truncated=False,
                   replaced_chars=0, warnings=None):
    """纯函数: 解析日志文本, 产出 FileReport(不碰文件系统)。"""
    sym_name = getattr(symbols, "name", "<符号表>")
    sym_max, _ = probe_symbol_range(symbols)
    sym_max_txt = "未知" if sym_max is None else str(sym_max)

    lines = text.splitlines()
    annotated = []
    line_levels = []
    stack_line_numbers = []
    id_counter = Counter()
    miss_counter = Counter()
    level_counter = Counter()
    build_hashes = Counter()

    hits = 0
    misses = 0
    max_index = 0
    cur_level = None          # 当前段等级, 由最近一条消息行决定, 续行继承

    for lineno, line in enumerate(lines, 1):
        m = TS_RE.match(line)
        if m:
            cur_level = m.group(3)
        line_levels.append(cur_level)

        ids = FUNC_RE.findall(line)
        if ids:
            parts = []
            for sid in ids:
                fid = int(sid)
                id_counter[fid] += 1
                if fid > max_index:
                    max_index = fid

                name = symbols.lookup(fid)
                if name is None:
                    misses += 1
                    miss_counter[fid] += 1
                    parts.append(
                        f"[{fid}] !!! 未命中(符号表 {sym_name} 中不存在, 最大索引 {sym_max_txt})")
                else:
                    hits += 1
                    parts.append(f"[{fid}] {name}")

            annotated.append(line + "  <= " + " | ".join(parts))
            stack_line_numbers.append(lineno)
            level_counter[cur_level] += 1
        else:
            annotated.append(line)

        for h in BUILD_RE.findall(line):
            build_hashes[h] += 1

    return FileReport(
        path=Path(path) if path else None,
        text=text,
        lines=lines,
        annotated=annotated,
        line_levels=line_levels,
        stack_line_numbers=stack_line_numbers,
        id_counter=id_counter,
        miss_counter=miss_counter,
        level_counter=level_counter,
        build_hashes=build_hashes,
        hits=hits,
        misses=misses,
        max_index=max_index,
        truncated=truncated,
        replaced_chars=replaced_chars,
        warnings=list(warnings or []),
    )


def parse_log_file(path, symbols):
    """解析单个文件。读取失败不抛异常, 而是返回带 error 的空报告(不中断整批)。"""
    path = Path(path)
    try:
        text, truncated, replaced, warns = read_log_text(path)
    except OSError as e:
        return FileReport(path=path, error=str(e))
    return parse_log_text(text, symbols, path=path, truncated=truncated,
                          replaced_chars=replaced, warnings=warns)


def parse_paths(paths, symbols, progress_cb=None, cancel_cb=None):
    """批量解析入口, 返回 BatchReport。progress_cb(已完成, 总数, 文件名), cancel_cb()->bool。"""
    start = time.perf_counter()

    files = collect_log_files(paths)
    reports = []
    total = len(files)
    cancelled = False

    for idx, f in enumerate(files, 1):
        if cancel_cb is not None and cancel_cb():
            cancelled = True
            break
        reports.append(parse_log_file(f, symbols))
        if progress_cb is not None:
            progress_cb(idx, total, f.name)

    batch = BatchReport(files=reports, cancelled=cancelled)
    batch.symbol_name = getattr(symbols, "name", "") if symbols is not None else ""
    batch.symbol_count = len(symbols) if symbols is not None else 0
    batch.symbol_max_index = probe_symbol_range(symbols)[0]

    all_ids = Counter()
    for r in reports:
        if r.error:
            continue
        batch.total_hits += r.hits
        batch.total_misses += r.misses
        batch.total_stack_lines += len(r.stack_line_numbers)
        if r.max_index > batch.max_index_in_logs:
            batch.max_index_in_logs = r.max_index
        batch.miss_counter.update(r.miss_counter)
        batch.build_hashes.update(r.build_hashes)
        all_ids.update(r.id_counter)

    batch.unique_ids = len(all_ids)
    batch.elapsed = time.perf_counter() - start
    batch.warnings = version_mismatch_hints(batch)
    return batch


def version_mismatch_hints(batch):
    """符号表/构建不匹配的三条诊断规则, 返回提示字符串列表。"""
    hints = []

    # A(强): 日志里的索引越过了符号表上界
    if batch.symbol_max_index is not None and batch.max_index_in_logs > batch.symbol_max_index:
        hints.append(
            f"日志出现索引 {batch.max_index_in_logs}, 超出符号表最大索引 "
            f"{batch.symbol_max_index}, 符号表版本过旧或与构建不匹配")

    # B(弱): 索引没越界但未命中率偏高, 可能是另一个构建(索引相同但函数顺序不同)
    elif batch.total_stack_lines and \
            batch.total_misses / batch.total_stack_lines >= MISS_RATIO_WARN:
        ratio = batch.total_misses * 100.0 / batch.total_stack_lines
        hints.append(
            f"未命中率 {ratio:.1f}%(索引未越界), 可能解析的是另一个构建的日志, "
            f"请核对下方的 wasm 构建哈希")

    # C: 目录里混了多个构建
    if len(batch.build_hashes) > 1:
        items = ", ".join(f"{h}({c} 处)" for h, c in batch.build_hashes.most_common())
        hints.append(f"目录内混有 {len(batch.build_hashes)} 个构建: {items}; "
                     f"单份符号表只能对应其中一个")

    return hints


# ---------------------------------------------------------------- 筛选 / 渲染

def filter_lines(report, level_filter, keyword=None):
    """按等级与关键词筛出保留的行号集合(1-based); 两者都为空时返回 None(表示不过滤)。

    - 等级为 None 的行(无法判定, 如文件开头)始终保留, 避免丢内容
    - keyword 是大小写不敏感的子串匹配
    """
    kw = keyword.lower() if keyword else None
    if not level_filter and not kw:
        return None

    keep = set()
    for i, lv in enumerate(report.line_levels, 1):
        if level_filter and lv is not None and lv not in level_filter:
            continue
        if kw and kw not in report.lines[i - 1].lower():
            continue
        keep.add(i)
    return keep


def _select_lines(report, keep, view, context):
    """在 keep 约束下按视图模式选出要渲染的行号(升序)。"""
    total = len(report.lines)

    if view == VIEW_FULL:
        return list(range(1, total + 1)) if keep is None else sorted(keep)

    stack = report.stack_line_numbers
    if keep is not None:
        stack = [ln for ln in stack if ln in keep]
    if not stack:
        return []

    if view == VIEW_STACK:
        return stack

    # 上下文视图: 栈行 ± context(仍受 keep 约束)
    picked = set()
    for ln in stack:
        for j in range(max(1, ln - context), min(total, ln + context) + 1):
            if keep is None or j in keep:
                picked.add(j)
    return sorted(picked)


def format_file_report(report, index=0, total=0, level_filter=None, keyword=None,
                       view=VIEW_CONTEXT, context=DEFAULT_CONTEXT, show_lineno=True):
    """渲染单个文件(带文件头)。"""
    keep = filter_lines(report, level_filter, keyword)
    selected = _select_lines(report, keep, view, context)

    head = "=" * 20 + " "
    if index and total:
        head += f"[{index}/{total}] "
    head += (f"{report.name} | 栈帧 {len(report.stack_line_numbers)} 处 / "
             f"唯一 {report.unique_ids} / 未命中 {report.misses} ")
    head += "=" * 20

    out = [head]
    if report.error:
        out.append(f"!!! 读取失败: {report.error}")
        return "\n".join(out)

    # 本来就没有堆栈的文件压缩成一行(上传目录里这类小文件很多), 避免大段空白占满视野
    if not report.stack_line_numbers:
        for w in report.warnings:
            out.append(f"!!! {w}")
        return "\n".join(out)

    for w in report.warnings:
        out.append(f"!!! {w}")

    if not selected:
        out.append("(当前筛选条件下无内容)")
        return "\n".join(out)

    for ln in selected:
        prefix = f"L{ln}: " if show_lineno else ""
        out.append(prefix + report.annotated[ln - 1])
    return "\n".join(out)


def format_batch_report(batch, level_filter=None, keyword=None, view=VIEW_CONTEXT,
                        context=DEFAULT_CONTEXT, show_lineno=True):
    """渲染整批(每个文件一段 + 末尾汇总)。

    本来就没有堆栈的文件不占正文(每次上传都会产生一批这种小文件, 否则首屏全是空白),
    只在末尾折成一行列出; 单独选中该文件时仍可正常查看。
    """
    total = len(batch.files)
    chunks = []
    empty_names = []

    for idx, fr in enumerate(batch.files, 1):
        if not fr.stack_line_numbers and not fr.error:
            empty_names.append(fr.name)
            continue
        chunks.append(format_file_report(fr, index=idx, total=total,
                                         level_filter=level_filter, keyword=keyword,
                                         view=view, context=context,
                                         show_lineno=show_lineno))

    if empty_names:
        chunks.append(f"[无堆栈文件 {len(empty_names)} 个: " + ", ".join(empty_names) + "]")

    chunks.append(format_summary_block(batch))
    return "\n\n".join(chunks)


def format_summary_block(batch):
    """汇总块: 统计 + 符号表范围 + 构建哈希 + 未命中清单 + 警告。"""
    out = ["=" * 20 + " 汇总 " + "=" * 20]
    out.append(summarize(batch))

    if batch.symbol_max_index is not None:
        out.append(f"符号表: {batch.symbol_name} ({batch.symbol_count:,} 项, "
                   f"索引 0-{batch.symbol_max_index:,})")
    else:
        out.append(f"符号表: {batch.symbol_name} ({batch.symbol_count:,} 项)")

    if batch.build_hashes:
        items = ", ".join(f"{h} ({c} 处)" for h, c in batch.build_hashes.most_common())
        out.append(f"构建哈希: {items}")

    if batch.miss_counter:
        items = ", ".join(f"{k} x{v}" for k, v in batch.miss_counter.most_common(20))
        out.append(f"未命中编号: {items}")

    if batch.cancelled:
        out.append("(已取消, 结果不完整)")

    for w in batch.warnings:
        out.append(f"警告: {w}")

    return "\n".join(out)


def summarize(batch):
    """一行统计, 供 GUI 标签使用。"""
    return (f"共 {batch.file_count} 个文件 / {batch.total_stack_lines} 处栈帧 / "
            f"唯一编号 {batch.unique_ids} / 命中 {batch.total_hits} / "
            f"未命中 {batch.total_misses} / 耗时 {batch.elapsed:.2f} s")
