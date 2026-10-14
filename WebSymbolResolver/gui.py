# -*- coding: utf-8 -*-
"""WebGL 崩溃栈符号解析工具(PySide6 界面,样式参考 MapExporterPy)。

暗色主题 + SectionCard 卡片分组:选择符号文件 -> 粘贴崩溃栈 -> 自动解析。
"""
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

import core
from batch_gui import BatchLogWindow


class SectionCard(QFrame):
    """卡片式分组容器:左侧彩色色条标题 + 内容区(与 MapExporterPy 一致)。"""

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WebGL 崩溃栈符号解析")
        self.resize(960, 720)
        self.setMinimumSize(760, 560)
        self.symbols = None
        self._build_ui()
        self.setStyleSheet(self._build_stylesheet())
        self._refresh_symbol_list()

    # ---------------- 界面 ----------------

    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # --- 符号文件卡片 ---
        file_card = SectionCard("符号文件", "#4488ff")
        row = QHBoxLayout()
        row.addWidget(QLabel("文件:"))
        self.combo_symbols = QComboBox()
        self.combo_symbols.currentIndexChanged.connect(self._load_selected)
        row.addWidget(self.combo_symbols, 1)
        btn_refresh = QPushButton("刷新")
        btn_refresh.setFixedWidth(64)
        btn_refresh.clicked.connect(self._refresh_symbol_list)
        row.addWidget(btn_refresh)
        btn_browse = QPushButton("浏览...")
        btn_browse.setFixedWidth(72)
        btn_browse.clicked.connect(self._browse_symbol)
        row.addWidget(btn_browse)
        file_card.addLayout(row)
        self.label_sym_info = QLabel()
        self.label_sym_info.setObjectName("secondaryLabel")
        file_card.addWidget(self.label_sym_info)
        row_batch = QHBoxLayout()
        self.btn_batch = QPushButton("批量解析玩家日志...")
        self.btn_batch.clicked.connect(self._open_batch)
        row_batch.addWidget(self.btn_batch)
        row_batch.addStretch(1)
        file_card.addLayout(row_batch)
        root.addWidget(file_card)

        # --- 崩溃栈输入卡片 ---
        input_card = SectionCard("崩溃栈(粘贴浏览器报错内容)", "#ff8800")
        self.edit_stack = QTextEdit()
        self.edit_stack.setPlaceholderText(
            "粘贴包含 wasm-function[N] 的报错栈,例如:\n\n"
            "RuntimeError: function signature mismatch\n"
            "    at wasm-function[21820]:0x685fe8\n"
            "    at wasm-function[3146]:0x11acdb\n"
            "    ...\n\n输入后自动解析。"
        )
        self.edit_stack.setMinimumHeight(220)
        self.edit_stack.textChanged.connect(
            lambda: QTimer.singleShot(250, self._resolve))
        input_card.addWidget(self.edit_stack)
        root.addWidget(input_card)

        # --- 解析结果卡片 ---
        result_card = SectionCard("解析结果", "#00cc66")
        self.label_result_info = QLabel()
        self.label_result_info.setObjectName("secondaryLabel")
        result_card.addWidget(self.label_result_info)
        self.edit_result = QTextEdit()
        self.edit_result.setReadOnly(True)
        self.edit_result.setMinimumHeight(220)
        result_card.addWidget(self.edit_result)

        row = QHBoxLayout()
        btn_copy = QPushButton("复制全部")
        btn_copy.setObjectName("primaryButton")
        btn_copy.clicked.connect(self._copy_result)
        row.addWidget(btn_copy)
        btn_open_dir = QPushButton("打开符号目录")
        btn_open_dir.clicked.connect(self._open_symbol_dir)
        row.addWidget(btn_open_dir)
        row.addStretch(1)
        result_card.addLayout(row)
        root.addWidget(result_card)

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
        QTextEdit {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 6px;
            padding: 6px 10px; color: #e0e0e0; font-family: Consolas, monospace;
            font-size: 12px; selection-background-color: #ff8833;
        }
        QTextEdit::placeholder { color: #5a5a72; }
        QTextEdit:focus { border-color: #ff8833; }
        QLabel { color: #e0e0e0; }
        #secondaryLabel { color: #a8a8c0; font-size: 12px; }
        QMessageBox { background: #262638; color: #e0e0e0; }
        """

    # ---------------- 符号文件 ----------------

    def _refresh_symbol_list(self):
        self.combo_symbols.blockSignals(True)
        self.combo_symbols.clear()
        files = core.find_symbol_files()
        if not files:
            self.combo_symbols.addItem("(未在默认目录找到符号文件)", "")
            self.label_sym_info.setText(
                f"默认目录 {core.DEFAULT_SYMBOL_DIR} 未找到符号 json,可用『浏览...』手动选择")
            self.symbols = None
        else:
            for p in files:
                self.combo_symbols.addItem(p.name, str(p))
            self.label_sym_info.setText(f"默认目录: {core.DEFAULT_SYMBOL_DIR}")
        self.combo_symbols.blockSignals(False)
        self._load_selected()

    def _browse_symbol(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择符号文件", str(core.DEFAULT_SYMBOL_DIR),
            "符号文件 (*_symbols.json *.json);;所有文件 (*)")
        if not path:
            return
        self.combo_symbols.blockSignals(True)
        self.combo_symbols.clear()
        self.combo_symbols.addItem(Path(path).name, path)
        self.combo_symbols.blockSignals(False)
        self.label_sym_info.setText(f"手动选择: {path}")
        self._load_selected()

    def _load_selected(self):
        path = self.combo_symbols.currentData()
        if not path:
            self.symbols = None
            self.label_result_info.setText("未加载符号文件")
            return
        try:
            self.symbols = core.SymbolTable(path)
            self.label_sym_info.setText(
                f"{Path(path).name}: {len(self.symbols):,} 个函数映射")
        except Exception as e:
            self.symbols = None
            self.label_sym_info.setText(f"加载失败: {e}")
        self._resolve()

    # ---------------- 解析 ----------------

    def _resolve(self):
        if self.symbols is None:
            self.edit_result.setPlainText("")
            self.label_result_info.setText("请先选择符号文件")
            return
        text = self.edit_stack.toPlainText()
        if not text.strip():
            self.edit_result.setPlainText("")
            self.label_result_info.setText("等待输入崩溃栈...")
            return
        lines, found, miss = core.resolve_text(text, self.symbols)
        self.edit_result.setPlainText("\n".join(lines) if lines else "(未在输入中找到 wasm-function[N])")
        self.label_result_info.setText(
            f"命中 {found} 个 / 未命中 {miss} 个 / 共 {len(lines)} 个唯一编号")

    def _copy_result(self):
        text = self.edit_result.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.label_result_info.setText(self.label_result_info.text() + " | 已复制 ✓")

    def _open_symbol_dir(self):
        os.startfile(str(core.DEFAULT_SYMBOL_DIR))

    def _open_batch(self):
        if getattr(self, "_batch_win", None) is None:
            self._batch_win = BatchLogWindow(
                symbol_provider=lambda: self.symbols, parent=self)
        self._batch_win.show()
        self._batch_win.raise_()
        self._batch_win.activateWindow()


def run_gui() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
