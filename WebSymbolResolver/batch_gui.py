# -*- coding: utf-8 -*-
"""玩家上报日志的批量符号解析窗口。

独立窗口(主窗口纵向已被三张卡片占满), 样式沿用 gui.py 的暗色主题。
解析结果整体缓存在 self.report, 等级筛选与搜索都是纯视图重渲染, 不重跑解析。
"""
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QTextEdit, QVBoxLayout,
                               QWidget)

import logbatch as L

MAX_EXTRA_SELECTIONS = 2000     # 高亮数量上限, 防止大文本卡顿


class SectionCard(QFrame):
    """卡片式分组容器:左侧彩色色条标题 + 内容区(与 gui.py 一致)。"""

    def __init__(self, title, accent="#4488ff", parent=None):
        super().__init__(parent)
        self.setObjectName("sectionCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 5, 12, 8)
        outer.setSpacing(5)
        header = QLabel(title)
        header.setStyleSheet(
            f"QLabel {{ color: #c8c8dc; font-weight: bold; font-size: 10px; "
            f"border-left: 3px solid {accent}; padding-left: 8px; "
            f"padding-top: 0px; padding-bottom: 0px; }}"
        )
        header.setFixedHeight(20)
        outer.addWidget(header)
        self.content = QVBoxLayout()
        self.content.setSpacing(6)
        outer.addLayout(self.content)

    def addWidget(self, w):
        self.content.addWidget(w)

    def addLayout(self, l):
        self.content.addLayout(l)


class BatchWorker(QThread):
    """后台解析线程。run() 必须整体 try/except —— onefile + console=False 下
    线程内未捕获异常只会让 UI 永久卡在"解析中"。"""

    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, files, symbols, parent=None):
        super().__init__(parent)
        self._files = files
        self._symbols = symbols
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        try:
            report = L.parse_paths(
                self._files, self._symbols,
                progress_cb=lambda d, t, n: self.progress.emit(d, t, n),
                cancel_cb=lambda: self._cancel)
            self.done.emit(report)
        except Exception as e:                      # noqa: BLE001 - 兜底, 不吞给用户看
            self.failed.emit(f"{type(e).__name__}: {e}")


class BatchLogWindow(QMainWindow):
    def __init__(self, symbol_provider=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("玩家上报日志 - 批量符号解析")
        self.resize(1180, 820)
        self.setMinimumSize(820, 600)

        self._symbol_provider = symbol_provider or (lambda: None)
        self.report = None            # logbatch.BatchReport | None
        self.worker = None
        self._current_index = -1      # -1 表示"全部文件"

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_search)

        self._build_ui()
        self.setStyleSheet(self._build_stylesheet())
        self._refresh_symbol_label()
        self._preview_input()

    # ---------------- 界面 ----------------

    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- 输入卡片 ---
        in_card = SectionCard("输入", "#4488ff")
        row = QHBoxLayout()
        row.addWidget(QLabel("路径:"))
        self.edit_path = QLineEdit()
        self.edit_path.setPlaceholderText("日志文件或目录, 可留空后点右侧按钮选择")
        self.edit_path.textChanged.connect(self._preview_input)
        row.addWidget(self.edit_path, 1)

        self.btn_dir = QPushButton("选择目录...")
        self.btn_dir.clicked.connect(self._pick_dir)
        row.addWidget(self.btn_dir)

        self.btn_files = QPushButton("选择文件...")
        self.btn_files.clicked.connect(self._pick_files)
        row.addWidget(self.btn_files)

        self.btn_start = QPushButton("开始解析")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.clicked.connect(self._start)
        row.addWidget(self.btn_start)
        in_card.addLayout(row)

        self.label_symbol = QLabel()
        self.label_symbol.setObjectName("secondaryLabel")
        in_card.addWidget(self.label_symbol)

        self.label_input = QLabel()
        self.label_input.setObjectName("secondaryLabel")
        in_card.addWidget(self.label_input)

        prow = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        prow.addWidget(self.progress, 1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedWidth(64)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel)
        prow.addWidget(self.btn_cancel)
        in_card.addLayout(prow)
        root.addWidget(in_card)

        # --- 结果总览卡片 ---
        sum_card = SectionCard("结果总览", "#00cc66")
        self.label_summary = QLabel("尚未解析")
        sum_card.addWidget(self.label_summary)
        self.label_warn = QLabel()
        self.label_warn.setObjectName("warningLabel")
        self.label_warn.setWordWrap(True)
        sum_card.addWidget(self.label_warn)
        root.addWidget(sum_card)

        # --- 筛选 / 搜索工具栏 ---
        bar = QHBoxLayout()
        bar.addWidget(QLabel("等级:"))
        self.level_boxes = {}
        for ch in L.LEVEL_ORDER:
            cb = QCheckBox(ch)
            cb.setToolTip(f"{ch} = {L.LEVEL_NAMES[ch]}")
            cb.setChecked(ch in ("E", "W"))
            cb.stateChanged.connect(self._on_filter_changed)
            bar.addWidget(cb)
            self.level_boxes[ch] = cb

        self.btn_ew = QPushButton("仅 E/W")
        self.btn_ew.setFixedWidth(76)
        self.btn_ew.clicked.connect(self._only_ew)
        bar.addWidget(self.btn_ew)

        bar.addSpacing(12)
        bar.addWidget(QLabel("搜索:"))
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索日志内容 / 函数名")
        self.edit_search.setFixedWidth(210)
        self.edit_search.textChanged.connect(lambda: self._search_timer.start(250))
        self.edit_search.returnPressed.connect(self._find_next)
        bar.addWidget(self.edit_search)

        self.label_match = QLabel("-")
        self.label_match.setObjectName("secondaryLabel")
        self.label_match.setFixedWidth(72)
        bar.addWidget(self.label_match)

        self.btn_prev = QPushButton("上一个")
        self.btn_prev.setFixedWidth(64)
        self.btn_prev.clicked.connect(self._find_prev)
        bar.addWidget(self.btn_prev)

        self.btn_next = QPushButton("下一个")
        self.btn_next.setFixedWidth(64)
        self.btn_next.clicked.connect(self._find_next)
        bar.addWidget(self.btn_next)

        self.chk_only_match = QCheckBox("仅显示匹配行")
        self.chk_only_match.stateChanged.connect(self._on_filter_changed)
        bar.addWidget(self.chk_only_match)

        bar.addStretch(1)
        root.addLayout(bar)

        # --- 文件列表 + 结果 ---
        splitter = QSplitter(Qt.Horizontal)
        self.list_files = QListWidget()
        self.list_files.setMinimumWidth(190)
        self.list_files.currentRowChanged.connect(self._on_file_selected)
        splitter.addWidget(self.list_files)

        self.text_result = QPlainTextEdit()
        self.text_result.setReadOnly(True)
        self.text_result.setLineWrapMode(QPlainTextEdit.NoWrap)
        splitter.addWidget(self.text_result)
        splitter.setSizes([320, 860])
        root.addWidget(splitter, 1)

        # --- 底部操作栏 ---
        brow = QHBoxLayout()
        btn_copy_cur = QPushButton("复制当前视图")
        btn_copy_cur.clicked.connect(self._copy_current)
        brow.addWidget(btn_copy_cur)

        btn_copy_all = QPushButton("复制全部")
        btn_copy_all.clicked.connect(self._copy_all)
        brow.addWidget(btn_copy_all)

        btn_export = QPushButton("导出 txt...")
        btn_export.clicked.connect(self._export_txt)
        brow.addWidget(btn_export)

        brow.addSpacing(12)
        brow.addWidget(QLabel("视图:"))
        self.combo_view = QComboBox()
        self.combo_view.addItem("上下文 ±2 行", L.VIEW_CONTEXT)
        self.combo_view.addItem("仅堆栈行", L.VIEW_STACK)
        self.combo_view.addItem("完整原文", L.VIEW_FULL)
        self.combo_view.currentIndexChanged.connect(self._on_filter_changed)
        brow.addWidget(self.combo_view)

        self.chk_lineno = QCheckBox("显示行号")
        self.chk_lineno.setChecked(True)
        self.chk_lineno.stateChanged.connect(self._on_filter_changed)
        brow.addWidget(self.chk_lineno)

        brow.addStretch(1)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        brow.addWidget(btn_close)
        root.addLayout(brow)

        self.setCentralWidget(central)

    def _build_stylesheet(self):
        return """
        QMainWindow, QWidget {
            background: #1e1e2e; color: #e0e0e0;
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 12px;
        }
        #sectionCard {
            background: #262638; border: 1px solid #323248; border-radius: 8px;
        }
        QPushButton {
            background: #3a3a52; border: 1px solid #4a4a68; border-radius: 5px;
            padding: 6px 14px; color: #e0e0e0; font-size: 12px;
        }
        QPushButton:hover { background: #4a4a6a; border-color: #5a5a7a; }
        QPushButton:pressed { background: #2e2e44; }
        QPushButton:disabled { background: #2a2a3a; color: #606070; border-color: #323248; }
        #primaryButton {
            background: #ff6600; border-color: #ff8833; color: #ffffff; font-weight: bold;
            padding: 7px 18px;
        }
        #primaryButton:hover { background: #ff8833; }
        #primaryButton:pressed { background: #cc5500; }
        QComboBox {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 6px;
            padding: 5px 10px; color: #e0e0e0; min-height: 24px;
        }
        QComboBox:hover { border-color: #4e4e6e; }
        QComboBox QAbstractItemView {
            background: #2e2e44; color: #e0e0e0; selection-background-color: #4a4a6a;
            border: 1px solid #3e3e58;
        }
        QLineEdit {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 6px;
            padding: 5px 10px; color: #e0e0e0; selection-background-color: #ff8833;
        }
        QLineEdit:focus { border-color: #ff8833; }
        QLineEdit:read-only { color: #9090a8; }
        QPlainTextEdit, QTextEdit {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 6px;
            padding: 6px 10px; color: #e0e0e0; font-family: Consolas, monospace;
            font-size: 12px; selection-background-color: #ff8833;
        }
        QPlainTextEdit:focus { border-color: #ff8833; }
        QListWidget {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 6px;
            color: #e0e0e0; font-size: 12px; outline: none;
        }
        QListWidget::item { padding: 4px 6px; border-radius: 3px; }
        QListWidget::item:selected { background: #4a4a6a; }
        QListWidget::item:hover { background: #3a3a52; }
        QCheckBox { color: #e0e0e0; spacing: 4px; }
        QCheckBox::indicator { width: 14px; height: 14px; }
        QCheckBox::indicator:unchecked {
            background: #2e2e44; border: 1px solid #4a4a68; border-radius: 3px;
        }
        QCheckBox::indicator:checked {
            background: #ff6600; border: 1px solid #ff8833; border-radius: 3px;
        }
        QProgressBar {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 5px;
            height: 16px; text-align: center; color: #e0e0e0; font-size: 11px;
        }
        QProgressBar::chunk { background: #ff6600; border-radius: 4px; }
        QSplitter::handle { background: #323248; width: 3px; }
        QLabel { color: #e0e0e0; }
        #secondaryLabel { color: #a8a8c0; font-size: 12px; }
        #warningLabel { color: #ff8866; font-size: 12px; }
        QMessageBox { background: #262638; color: #e0e0e0; }
        QScrollBar:vertical { background: #262638; width: 10px; }
        QScrollBar::handle:vertical {
            background: #4a4a68; border-radius: 5px; min-height: 24px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar:horizontal { background: #262638; height: 10px; }
        QScrollBar::handle:horizontal {
            background: #4a4a68; border-radius: 5px; min-width: 24px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        """

    # ---------------- 输入 ----------------

    def _refresh_symbol_label(self):
        symbols = self._symbol_provider()
        if symbols is None:
            self.label_symbol.setText("符号表: 未加载(请先在主窗口『符号文件』卡片选择)")
            return
        max_index, count = L.probe_symbol_range(symbols)
        if max_index is None:
            self.label_symbol.setText(f"符号表: {symbols.name} | {count:,} 项")
        else:
            self.label_symbol.setText(
                f"符号表: {symbols.name} | {count:,} 项 | 索引 0-{max_index:,}")

    def _pick_dir(self):
        start = self.edit_path.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择日志目录", start)
        if path:
            self.edit_path.setText(path)

    def _pick_files(self):
        start = self.edit_path.text().strip() or str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择日志文件", start, "日志文件 (*.log *.txt);;所有文件 (*)")
        if paths:
            self.edit_path.setText(";".join(paths))

    def _input_paths(self):
        raw = self.edit_path.text().strip()
        if not raw:
            return []
        return [p for p in (s.strip() for s in raw.split(";")) if p]

    def _preview_input(self):
        files = L.collect_log_files(self._input_paths())
        if not files:
            self.label_input.setText("未找到 .log/.txt 文件")
            return
        total = 0
        for f in files:
            try:
                total += f.stat().st_size
            except OSError:
                pass
        self.label_input.setText(
            f"已选: {len(files)} 个文件 ({total / 1048576:.1f} MB)")

    def _set_inputs_enabled(self, enabled):
        self.btn_dir.setEnabled(enabled)
        self.btn_files.setEnabled(enabled)
        self.btn_start.setEnabled(enabled)
        self.edit_path.setReadOnly(not enabled)

    # ---------------- 解析 ----------------

    def _start(self):
        if self.worker is not None and self.worker.isRunning():
            return

        symbols = self._symbol_provider()
        if symbols is None:
            QMessageBox.warning(self, "提示", "请先在主窗口『符号文件』卡片选择符号表")
            return

        files = L.collect_log_files(self._input_paths())
        if not files:
            QMessageBox.warning(self, "提示", "未找到 .log/.txt 文件, 请先选择日志目录或文件")
            return

        self.report = None
        self.list_files.clear()
        self.text_result.setPlainText("")
        self.label_summary.setText("解析中...")
        self.label_warn.setText("")
        self.progress.setRange(0, len(files))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.btn_cancel.setVisible(True)
        self._set_inputs_enabled(False)

        self.worker = BatchWorker(files, symbols, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _cancel(self):
        if self.worker is not None:
            self.worker.request_cancel()

    def _on_progress(self, done, total, name):
        self.progress.setValue(done)
        self.progress.setFormat(f"正在解析 {done}/{total}  {name}")

    def _on_done(self, report):
        self.report = report
        self.label_summary.setText(L.summarize(report))

        warns = list(report.warnings)
        for fr in report.files:
            if fr.error:
                warns.append(f"{fr.name}: 读取失败 {fr.error}")
        self.label_warn.setText("\n".join("⚠ " + w for w in warns))

        self._fill_file_list()
        self._render()

    def _on_failed(self, message):
        self.report = None
        self.label_summary.setText("解析失败")
        QMessageBox.warning(self, "解析失败", message)

    def _on_worker_finished(self):
        self.progress.setVisible(False)
        self.btn_cancel.setVisible(False)
        self._set_inputs_enabled(True)
        if self.worker is not None:
            self.worker.wait()
            self.worker = None

    def _fill_file_list(self):
        self.list_files.blockSignals(True)
        self.list_files.clear()
        if self.report is not None:
            self.list_files.addItem(QListWidgetItem("全部文件"))
            for fr in self.report.files:
                item = QListWidgetItem(
                    f"{fr.name}   {len(fr.stack_line_numbers)} 处 / 未命中 {fr.misses}")
                if fr.misses:
                    item.setForeground(QColor("#ff6060"))
                self.list_files.addItem(item)
            self.list_files.setCurrentRow(0)
        self.list_files.blockSignals(False)
        self._current_index = -1

    # ---------------- 渲染 ----------------

    def _current_levels(self):
        checked = {ch for ch, cb in self.level_boxes.items() if cb.isChecked()}
        return None if len(checked) == len(L.LEVEL_ORDER) else checked

    def _current_keyword(self):
        if not self.chk_only_match.isChecked():
            return None
        return self.edit_search.text().strip() or None

    def _render(self):
        if self.report is None:
            return
        level_filter = self._current_levels()
        keyword = self._current_keyword()
        view = self.combo_view.currentData()
        show_lineno = self.chk_lineno.isChecked()

        if self._current_index < 0:
            text = L.format_batch_report(self.report, level_filter=level_filter,
                                         keyword=keyword, view=view,
                                         show_lineno=show_lineno)
        else:
            fr = self.report.files[self._current_index]
            text = L.format_file_report(fr, index=self._current_index + 1,
                                        total=len(self.report.files),
                                        level_filter=level_filter, keyword=keyword,
                                        view=view, show_lineno=show_lineno)

        self.text_result.setPlainText(text)
        self._apply_highlights()

    def _on_file_selected(self, row):
        self._current_index = row - 1 if row > 0 else -1
        self._render()

    def _on_filter_changed(self):
        self._render()

    def _only_ew(self):
        for ch, cb in self.level_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(ch in ("E", "W"))
            cb.blockSignals(False)
        self._render()

    # ---------------- 搜索 ----------------

    def _apply_search(self):
        """搜索框内容稳定后: 过滤模式重渲染, 否则只更新高亮。"""
        if self.chk_only_match.isChecked():
            self._render()
        else:
            self._apply_highlights()

    def _collect_selections(self, needle, fmt):
        out = []
        doc = self.text_result.document()
        cursor = QTextCursor(doc)
        while len(out) < MAX_EXTRA_SELECTIONS:
            cursor = doc.find(needle, cursor)
            if cursor.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            out.append(sel)
        return out

    def _apply_highlights(self):
        """未命中高亮与搜索高亮必须合并成一次 setExtraSelections ——
        该方法每次调用都整体替换选区集合, 分两次调用后者会盖掉前者。"""
        selections = []

        miss_fmt = QTextCharFormat()
        miss_fmt.setBackground(QColor("#5a1e1e"))
        miss_fmt.setForeground(QColor("#ff9090"))
        selections.extend(self._collect_selections("!!! 未命中", miss_fmt))

        keyword = self.edit_search.text().strip()
        if keyword:
            hit_fmt = QTextCharFormat()
            hit_fmt.setBackground(QColor("#6a5a10"))
            hit_fmt.setForeground(QColor("#ffe080"))
            selections.extend(self._collect_selections(keyword, hit_fmt))

        self.text_result.setExtraSelections(selections[:MAX_EXTRA_SELECTIONS])
        self._update_match_label(keyword)

    def _update_match_label(self, keyword):
        if not keyword:
            self.label_match.setText("-")
            return
        count = self.text_result.toPlainText().lower().count(keyword.lower())
        self.label_match.setText(f"{count} 处")

    def _find_next(self):
        keyword = self.edit_search.text().strip()
        if not keyword:
            return
        if not self.text_result.find(keyword):
            cursor = self.text_result.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.text_result.setTextCursor(cursor)
            if not self.text_result.find(keyword):
                self.label_match.setText("无匹配")

    def _find_prev(self):
        keyword = self.edit_search.text().strip()
        if not keyword:
            return
        flags = QTextDocument.FindBackward
        if not self.text_result.find(keyword, flags):
            cursor = self.text_result.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.text_result.setTextCursor(cursor)
            self.text_result.find(keyword, flags)

    # ---------------- 复制 / 导出 ----------------

    def _full_text(self):
        """完整原文视图(不受 UI 渲染上限与当前筛选影响)。"""
        return L.format_batch_report(self.report, view=L.VIEW_FULL, show_lineno=True)

    def _copy_current(self):
        text = self.text_result.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.label_summary.setText(self.label_summary.text() + " | 已复制当前视图 ✓")

    def _copy_all(self):
        if self.report is None:
            return
        QApplication.clipboard().setText(self._full_text())
        self.label_summary.setText(self.label_summary.text() + " | 已复制全部 ✓")

    def _export_txt(self):
        if self.report is None:
            QMessageBox.information(self, "提示", "还没有解析结果")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出解析结果", "logs_resolved.txt", "文本文件 (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(self._full_text())
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self.label_summary.setText(
            self.label_summary.text() + f" | 已导出 {Path(path).name} ✓")

    # ---------------- 窗口 ----------------

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_symbol_label()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            QMessageBox.information(self, "提示", "正在解析, 请先点击『取消』")
            return
        super().closeEvent(event)
