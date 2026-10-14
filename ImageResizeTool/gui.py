# -*- coding: utf-8 -*-
"""PySide6 图形界面（样式参考 D:/PythonProject/MapExporterPy/gui.py）。

暗色主题 + SectionCard 卡片分组 + QThread 后台处理 + 进度条（支持中断续跑）。

布局：
  Header   工具名 / 副标题 / 路径校验徽章
  卡片     目标与范围（路径 · 缩放系数 · 关键字过滤 · 字体试跑）
  分割区   QSplitter：扫描信息（预览文本 + 统计条）/ 运行日志
  卡片     执行（进度条 + 图片 / 字体 / 中断 三组按钮）
  状态栏   状态文字 · 已记录 N 项 · 打开记录所在目录
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from string import Template

from PySide6.QtCore import QPointF, Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QStatusBar, QVBoxLayout,
                               QWidget)

from main import (DEFAULT_ASSETS_REL, DEFAULT_SCALE, RECORD_NAME, base_dir,
                  build_scan_report, load_record, process_fonts, process_images,
                  resolve_assets, image_snap)


# ======================== 主题配色（唯一来源） ========================
# QSS 与运行时动态样式都从这里取值，避免十六进制字面量散落各处。
# 保持原有暗色 + 橙色主调，与 MapExporterPy/gui.py、PrefabScaleWindow 观感一致。
THEME = {
    # 背景层次
    "bg": "#1e1e2e",             # 窗口底
    "surface": "#262638",        # 卡片
    "surface_hi": "#2e2e44",     # 输入控件
    "surface_text": "#232332",   # 文本区（信息 / 日志）
    "surface_bar": "#2a2a3a",    # 进度条底 / 禁用按钮
    # 边框
    "border": "#323248",
    "border_hi": "#3e3e58",
    "border_hover": "#4e4e6e",
    "border_btn": "#4a4a68",
    "border_btn_hover": "#5a5a7a",
    # 按钮底色
    "btn_bg": "#3a3a52",
    "btn_bg_hover": "#4a4a6a",
    "btn_bg_pressed": "#2e2e44",
    # 文字
    "text": "#e0e0e0",
    "text_soft": "#c8c8dc",
    "text_edit": "#d0d0e0",
    "text_dim": "#a8a8c0",
    "text_mute": "#5a5a72",
    "text_disabled": "#606070",
    "white": "#ffffff",
    # 主色（橙色，沿用原主题）
    "accent": "#ff6600",
    "accent_hi": "#ff8833",
    "accent_lo": "#cc5500",
    # 语义色
    "danger": "#e04a4a",
    "danger_hi": "#f06060",
    "danger_lo": "#b83a3a",
    "ok": "#4ec97a",
    "warn": "#e0a24a",
    "info": "#5aa9ff",
    # 卡片色条
    "card_scope": "#4488ff",
    "card_info": "#ff8800",
    "card_run": "#00cc66",
    # 杂项
    "selection": "#4a4a6a",
    "scroll_bg": "#232332",
    "scroll_handle": "#3e3e58",
    "scroll_handle_hover": "#4e4e6e",
}



def _icon_dir() -> Path:
    """运行时图标目录（放在系统临时目录，不引入仓库资源文件）。"""
    d = Path(tempfile.gettempdir()) / "imageresize_ui"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _check_icon_path() -> str:
    """生成 14x14 白色勾号 PNG，返回可被 QSS ``image: url()`` 引用的路径。

    QSS 定制 ``QCheckBox::indicator`` 背景后 Qt 不再画默认勾号，选中态会
    退化成一块纯色；这里补画一枚，保证"已勾选"一眼可辨。
    """
    path = _icon_dir() / "check.png"
    if not path.is_file():
        pm = QPixmap(14, 14)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(THEME["white"]), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(QPointF(3.2, 7.2), QPointF(6.0, 10.0))
        painter.drawLine(QPointF(6.0, 10.0), QPointF(10.8, 4.2))
        painter.end()
        pm.save(str(path), "PNG")
    return path.as_posix()


# ======================== 样式表 ========================
# QSS 里 {} 极多，用 string.Template 的 $name 占位，避免 f-string 遍地双大括号。
_STYLE = Template("""
/* ---------- 基底 ---------- */
QMainWindow, QWidget {
    background: $bg; color: $text;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px;
}
QToolTip {
    background: $surface_hi; color: $text;
    border: 1px solid $border_btn; border-radius: 4px; padding: 4px 8px;
}

/* ---------- Header ---------- */
QFrame#appHeader { background: transparent; }
QLabel#appTitle { color: $text; font-size: 17px; font-weight: bold; }
QLabel#appSubtitle { color: $text_mute; font-size: 11px; }
QLabel#pathBadge {
    background: $surface; border: 1px solid $border_btn; border-radius: 11px;
    padding: 4px 12px; color: $text_dim; font-size: 11px;
}
QLabel#pathBadge[ok="true"] { color: $ok; border-color: $ok; }
QLabel#pathBadge[ok="false"] { color: $danger; border-color: $danger; }

/* ---------- 卡片 ---------- */
#sectionCard { background: $surface; border: 1px solid $border; border-radius: 8px; }
#sectionCard:hover { border-color: $border_hi; }

/* ---------- 统计条 ---------- */
QLabel#statChip {
    background: $surface_hi; border: 1px solid $border_hi; border-radius: 9px;
    padding: 3px 10px; color: $text_dim; font-size: 11px;
}
QLabel#statChip[kind="ok"] { color: $ok; border-color: $ok; }
QLabel#statChip[kind="warn"] { color: $warn; border-color: $warn; }

/* ---------- 按钮 ---------- */
QPushButton {
    background: $btn_bg; border: 1px solid $border_btn; border-radius: 5px;
    padding: 6px 14px; color: $text; font-size: 12px;
}
QPushButton:hover { background: $btn_bg_hover; border-color: $border_btn_hover; }
QPushButton:pressed { background: $btn_bg_pressed; }
QPushButton:disabled { background: $surface_bar; color: $text_disabled; border-color: $border; }
QPushButton:focus { border-color: $accent_hi; }

#primaryButton {
    background: $accent; border-color: $accent_hi; color: $white; font-weight: bold;
    padding: 7px 18px;
}
#primaryButton:hover { background: $accent_hi; }
#primaryButton:pressed { background: $accent_lo; }
#primaryButton:disabled { background: $surface_bar; color: $text_disabled; border-color: $border; }

#dangerButton {
    background: $danger; border-color: $danger_hi; color: $white; font-weight: bold;
    padding: 6px 16px;
}
#dangerButton:hover { background: $danger_hi; }
#dangerButton:pressed { background: $danger_lo; }
#dangerButton:disabled { background: $surface_bar; color: $text_disabled; border-color: $border; }

#successButton {
    background: $ok; border-color: $ok; color: $bg; font-weight: bold;
}
#successButton:hover { border-color: $white; }
#successButton:pressed { border-color: $border_btn; }
#successButton:disabled { background: $surface_bar; color: $text_disabled; border-color: $border; }

#ghostButton {
    background: transparent; border: 1px solid $border_btn; color: $text_dim;
    padding: 5px 12px;
}
#ghostButton:hover { background: $surface_hi; color: $text; border-color: $border_btn_hover; }
#ghostButton:pressed { background: $btn_bg_pressed; }
#ghostButton:disabled { background: transparent; color: $text_disabled; border-color: $border; }

/* ---------- 输入控件 ---------- */
QLineEdit {
    background: $surface_hi; border: 1px solid $border_hi; border-radius: 6px;
    padding: 5px 10px; color: $text; min-height: 24px; font-size: 12px;
    selection-background-color: $selection;
}
QLineEdit::placeholder { color: $text_mute; }
QLineEdit:hover { border-color: $border_hover; }
QLineEdit:focus { border-color: $accent_hi; }
QLineEdit:disabled { background: $surface_bar; color: $text_disabled; }

QComboBox, QDoubleSpinBox, QSpinBox {
    background: $surface_hi; border: 1px solid $border_hi; border-radius: 6px;
    padding: 4px 8px; color: $text; min-height: 22px;
    selection-background-color: $selection;
}
QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover { border-color: $border_hover; }
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border-color: $accent_hi; }
QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled {
    background: $surface_bar; color: $text_disabled; border-color: $border;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: none; width: 0; height: 0; margin-right: 7px;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid $text_dim;
}
QComboBox QAbstractItemView {
    background: $surface_hi; color: $text; border: 1px solid $border_btn;
    border-radius: 6px; padding: 4px; outline: none;
    selection-background-color: $selection;
}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {
    background: transparent; border: none; width: 16px;
}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover { background: $border_btn; }
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid $text_dim;
}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid $text_dim;
}
QDoubleSpinBox::up-arrow:disabled, QSpinBox::up-arrow:disabled {
    border-bottom-color: $border;
}
QDoubleSpinBox::down-arrow:disabled, QSpinBox::down-arrow:disabled {
    border-top-color: $border;
}

/* ---------- 勾选框 ---------- */
QCheckBox { color: $text; spacing: 7px; }
QCheckBox:hover { color: $white; }
QCheckBox::indicator {
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid $border_btn; background: $surface_hi;
}
QCheckBox::indicator:hover { border-color: $accent_hi; }
QCheckBox::indicator:checked {
    background: $accent; border-color: $accent_hi; image: url("$check_icon");
}
QCheckBox::indicator:checked:hover { background: $accent_hi; image: url("$check_icon"); }
QCheckBox::indicator:disabled { background: $surface_bar; border-color: $border; }

/* ---------- 文本区 ---------- */
QPlainTextEdit, QTextEdit {
    background: $surface_text; border: 1px solid $border; border-radius: 6px;
    padding: 6px; color: $text_edit; selection-background-color: $selection;
}

/* ---------- 进度条 ---------- */
QProgressBar {
    background: $surface_bar; border: 1px solid $border; border-radius: 5px;
    text-align: center; color: $text; min-height: 22px; font-size: 11px;
}
QProgressBar::chunk { background: $accent; border-radius: 4px; }

/* ---------- 文字 ---------- */
QLabel { color: $text; background: transparent; }
QLabel#secondaryLabel { color: $text_dim; font-size: 11px; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical { background: $scroll_bg; width: 10px; margin: 0; border: none; }
QScrollBar::handle:vertical {
    background: $scroll_handle; min-height: 28px; border-radius: 5px; margin: 1px;
}
QScrollBar::handle:vertical:hover { background: $scroll_handle_hover; }
QScrollBar:horizontal { background: $scroll_bg; height: 10px; margin: 0; border: none; }
QScrollBar::handle:horizontal {
    background: $scroll_handle; min-width: 28px; border-radius: 5px; margin: 1px;
}
QScrollBar::handle:horizontal:hover { background: $scroll_handle_hover; }
QScrollBar::add-line, QScrollBar::sub-line {
    height: 0; width: 0; border: none; background: none;
}
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* ---------- 分割条 / 状态栏 / 选项卡 ---------- */
QSplitter::handle { background: $border; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }
QSplitter::handle:hover { background: $accent; }

QStatusBar { background: $surface; color: $text_dim; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $text_dim; font-size: 11px; }

QTabWidget::pane {
    border: 1px solid $border; border-radius: 6px; background: $surface; top: -1px;
}
QTabBar::tab {
    background: $surface_hi; color: $text_dim; border: 1px solid $border;
    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
    padding: 6px 16px; margin-right: 2px;
}
QTabBar::tab:selected { background: $surface; color: $text; border-color: $border_btn; }
QTabBar::tab:hover { color: $text; }

/* ---------- 消息框 ---------- */
QMessageBox { background: $surface; }
QMessageBox QLabel { color: $text; }
QMessageBox QPushButton { min-width: 70px; }
""")


class SectionCard(QFrame):
    """卡片式分组容器：左侧彩色色条标题 + 内容区（MapExporterPy 样式）。

    额外提供 hover 描边与可选投影，让卡片层次更清楚。
    """

    def __init__(self, title, accent=None, parent=None, shadow=True):
        super().__init__(parent)
        self.setObjectName("sectionCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 8, 14, 11)
        outer.setSpacing(7)

        header = QLabel(title)
        header.setStyleSheet(
            "QLabel { color: %s; font-weight: bold; font-size: 10px; "
            "border-left: 3px solid %s; padding-left: 8px; }"
            % (THEME["text_soft"], accent or THEME["card_scope"])
        )
        header.setFixedHeight(20)
        outer.addWidget(header)

        self.content = QVBoxLayout()
        self.content.setSpacing(7)
        outer.addLayout(self.content)

        if shadow:
            self._apply_shadow()

    def _apply_shadow(self):
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(16)
        effect.setColor(QColor(0, 0, 0, 120))
        effect.setOffset(0, 3)
        self.setGraphicsEffect(effect)

    def addWidget(self, w):
        self.content.addWidget(w)

    def addLayout(self, l):
        self.content.addLayout(l)


class ScanWorker(QThread):
    """后台扫描：生成预览文本（dry-run，不写任何文件）。"""

    progress = Signal(int, int, str)
    done = Signal(str, dict)      # 预览文本, stats（含 fonts / 各项计数）
    failed = Signal(str)

    def __init__(self, assets: Path, scale: float, record_path: Path, folder: str, parent=None):
        super().__init__(parent)
        self.assets = assets
        self.scale = scale
        self.record_path = record_path
        self.folder = folder

    def run(self):
        try:
            text, stats = build_scan_report(self.assets, self.scale, self.record_path,
                                            self.folder, progress=self.progress.emit)
            self.done.emit(text, stats)
        except Exception as e:                                  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")


class ResizeWorker(QThread):
    """后台处理：mode='images' 或 'fonts'；可中断（已处理项记入记录，可续跑）。"""

    progress = Signal(int, int, str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, assets: Path, scale: float, record_path: Path, mode: str,
                 folder: str = "", font_name: str = "", force: bool = False, parent=None):
        super().__init__(parent)
        self.assets = assets
        self.scale = scale
        self.record_path = record_path
        self.mode = mode
        self.folder = folder
        self.font_name = font_name
        self.force = force
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        try:
            if self.mode == "images":
                summary, _ = process_images(self.assets, self.scale, self.record_path,
                                            self.folder, self.force, "box",
                                            progress=self.progress.emit,
                                            should_stop=lambda: self._stop)
            else:
                summary, _ = process_fonts(self.assets, self.scale, self.record_path,
                                           self.font_name, self.force,
                                           progress=self.progress.emit,
                                           should_stop=lambda: self._stop)
            self.done.emit(summary)
        except Exception as e:                                  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片缩放工具")
        self.resize(1180, 850)
        self.setMinimumSize(940, 690)
        self.record_path = base_dir() / RECORD_NAME
        self.worker = None
        self._busy_flag = False
        self._stoppable = False
        self._path_ok = False
        self._last_action = ""
        self._build_ui()
        self.setStyleSheet(_STYLE.substitute({**THEME, "check_icon": _check_icon_path()}))
        self._validate_path()
        self._refresh_record_count()

    # ---------------- 界面 ----------------

    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)   # 留白给卡片投影
        root.setSpacing(12)

        root.addWidget(self._build_header())

        # --- 目标与范围 ---
        scope_card = SectionCard("目标与范围", THEME["card_scope"])
        scope_card.addLayout(self._row_path())
        self.label_path = QLabel("→")
        self.label_path.setObjectName("secondaryLabel")
        scope_card.addWidget(self.label_path)
        scope_card.addLayout(self._row_scale())
        scope_card.addLayout(self._row_filter())
        scope_card.addLayout(self._row_font())
        root.addWidget(scope_card)

        # --- 扫描信息 / 运行日志（可拖动分配高度） ---
        self.info_card = SectionCard("扫描信息", THEME["card_info"])
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(6)
        self.info_card.addLayout(self._stats_row)

        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        self.info.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.info.setFont(QFont("Consolas", 9))
        self.info.setMinimumHeight(150)
        self.info.setPlainText("点击下方【扫描】生成预览（dry-run，不修改任何文件）")
        self.info_card.addWidget(self.info)

        self.log_card = SectionCard("运行日志", THEME["info"])
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setMinimumHeight(80)
        self.log.setPlaceholderText("运行日志…")
        self.log_card.addWidget(self.log)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.info_card)
        splitter.addWidget(self.log_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([470, 160])
        root.addWidget(splitter, 1)

        # --- 执行 ---
        run_card = SectionCard("执行", THEME["card_run"])
        run_card.addLayout(self._row_progress())
        run_card.addLayout(self._row_actions())
        root.addWidget(run_card)

        self.setCentralWidget(central)
        self._build_statusbar()
        self._update_scale_hint()

    def _build_header(self):
        header = QFrame()
        header.setObjectName("appHeader")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(1)
        title = QLabel("图片缩放工具")
        title.setObjectName("appTitle")
        subtitle = QLabel("美术库图片 + 字体美术字批量 ×Scale；扫描为 dry-run，处理前不写任何文件")
        subtitle.setObjectName("appSubtitle")
        col.addWidget(title)
        col.addWidget(subtitle)
        lay.addLayout(col)
        lay.addStretch(1)

        self.badge_path = QLabel("路径未校验")
        self.badge_path.setObjectName("pathBadge")
        self.badge_path.setProperty("ok", "none")
        lay.addWidget(self.badge_path)
        return header

    @staticmethod
    def _label(text, width=96):
        lab = QLabel(text)
        lab.setFixedWidth(width)
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lab

    def _row_path(self):
        row = QHBoxLayout()
        row.addWidget(self._label("美术库(Assets):"))
        self.edit_assets = QLineEdit(DEFAULT_ASSETS_REL)
        self.edit_assets.setPlaceholderText(
            "绝对/相对路径：美术库 Assets 或其任意子目录（相对路径相对工具目录）")
        self.edit_assets.textChanged.connect(
            lambda: QTimer.singleShot(300, self._validate_path))
        row.addWidget(self.edit_assets, 1)
        btn = QPushButton("浏览...")
        btn.setObjectName("ghostButton")
        btn.setFixedWidth(76)
        btn.setToolTip("选择美术库 Assets 目录")
        btn.clicked.connect(self._browse_assets)
        row.addWidget(btn)
        return row

    def _row_scale(self):
        row = QHBoxLayout()
        row.addWidget(self._label("缩放系数:"))
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.01, 4.0)
        self.spin_scale.setSingleStep(0.05)
        self.spin_scale.setDecimals(2)
        self.spin_scale.setValue(DEFAULT_SCALE)
        self.spin_scale.setFixedWidth(90)
        self.spin_scale.setToolTip("2560×1440 基准 × Scale；0.75 → 1920×1080")
        self.spin_scale.valueChanged.connect(self._update_scale_hint)
        row.addWidget(self.spin_scale)
        self.label_scale = QLabel("")
        self.label_scale.setObjectName("secondaryLabel")
        row.addSpacing(10)
        row.addWidget(self.label_scale)
        row.addStretch(1)
        return row

    def _row_filter(self):
        row = QHBoxLayout()
        self.check_fonts = QCheckBox("包含字体美术字(图集 + 度量成对 ×Scale)")
        self.check_fonts.setChecked(True)
        self.check_fonts.setToolTip("勾选后，扫描与处理都会带上字体美术字")
        row.addWidget(self.check_fonts)
        row.addSpacing(16)
        row.addWidget(self._label("关键字过滤:"))
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("只处理路径含该关键字的图(试跑模块用，如 Bag)")
        row.addWidget(self.edit_filter, 1)
        return row

    def _row_font(self):
        row = QHBoxLayout()
        row.addWidget(self._label("字体试跑:"))
        self.combo_font = QComboBox()
        self.combo_font.setMinimumWidth(240)
        self.combo_font.setEnabled(False)
        self.combo_font.setToolTip("扫描后可选；先试跑一个在 Unity 里验收")
        row.addWidget(self.combo_font)
        tip = QLabel("扫描后可选，先试跑一个在 Unity 里验收")
        tip.setObjectName("secondaryLabel")
        row.addSpacing(8)
        row.addWidget(tip)
        row.addStretch(1)
        return row

    def _row_progress(self):
        row = QHBoxLayout()
        row.addWidget(self._label("进度:"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        row.addWidget(self.progress, 1)
        return row

    def _row_actions(self):
        row = QHBoxLayout()
        row.addSpacing(96)                     # 与上方标签列对齐

        self.btn_scan = QPushButton("扫描")
        self.btn_scan.setToolTip("dry-run 预览：只生成报告，不改任何文件")
        self.btn_scan.clicked.connect(self._scan)
        row.addWidget(self.btn_scan)

        row.addSpacing(10)
        self.btn_process = QPushButton("处理未处理项（图片）")
        self.btn_process.setObjectName("primaryButton")
        self.btn_process.setToolTip("把未处理的图片按 ×Scale 就地缩小")
        self.btn_process.clicked.connect(self._process_images)
        row.addWidget(self.btn_process)

        row.addSpacing(22)
        self.btn_trial = QPushButton("试跑选中字体")
        self.btn_trial.setToolTip("只处理下拉里选中的那一个字体，便于在 Unity 里验收")
        self.btn_trial.clicked.connect(self._trial_font)
        row.addWidget(self.btn_trial)

        self.btn_all_fonts = QPushButton("处理全部字体")
        self.btn_all_fonts.setToolTip("处理全部未处理的字体（图集 + 度量）")
        self.btn_all_fonts.clicked.connect(self._process_all_fonts)
        row.addWidget(self.btn_all_fonts)

        row.addStretch(1)
        self.btn_stop = QPushButton("中断")
        self.btn_stop.setObjectName("dangerButton")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setToolTip("当前项完成后停止；已处理项已记入记录，可直接续跑")
        self.btn_stop.clicked.connect(self._stop_worker)
        row.addWidget(self.btn_stop)
        return row

    def _build_statusbar(self):
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.setStatusBar(bar)

        self.status_label = QLabel("就绪")
        bar.addWidget(self.status_label, 1)

        self.status_record = QLabel("已记录 0 项")
        bar.addPermanentWidget(self.status_record)

        self.btn_open_record = QPushButton("打开记录所在目录")
        self.btn_open_record.setObjectName("ghostButton")
        self.btn_open_record.setFixedHeight(22)
        self.btn_open_record.setToolTip(f"在资源管理器里打开 {self.record_path.parent}")
        self.btn_open_record.clicked.connect(self._open_record_dir)
        bar.addPermanentWidget(self.btn_open_record)

    # ---------------- 样式辅助 ----------------

    def _set_badge(self, ok: bool, text: str):
        self.badge_path.setText(("✓ " if ok else "✗ ") + text)
        self.badge_path.setProperty("ok", "true" if ok else "false")
        self.badge_path.style().unpolish(self.badge_path)
        self.badge_path.style().polish(self.badge_path)

    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _refresh_record_count(self):
        rec = load_record(self.record_path)
        n = len(rec.get("images", {})) + len(rec.get("fonts", {}))
        self.status_record.setText(f"已记录 {n} 项")

    def _update_stats(self, stats: dict):
        while self._stats_row.count():
            item = self._stats_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        fonts = stats.get("fonts", [])
        total = stats.get("images_total", 0)
        processed = stats.get("images_processed", 0)
        chips = [
            ("图片", total, None),
            ("已处理", processed, "ok"),
            ("未处理", total - processed, "warn"),
            ("小图退让偶数", stats.get("small", 0), None),
            ("多切片图集", stats.get("multiple", 0), None),
            ("字体", len(fonts), None),
            ("字体已处理", stats.get("fonts_processed", 0), "ok"),
        ]
        for name, value, kind in chips:
            chip = QLabel(f"{name} {value}")
            chip.setObjectName("statChip")
            if kind:
                chip.setProperty("kind", kind)
            self._stats_row.addWidget(chip)
        self._stats_row.addStretch(1)

    def _open_record_dir(self):
        try:
            os.startfile(str(self.record_path.parent))      # noqa: S606 (Windows)
        except Exception as e:                              # noqa: BLE001
            QMessageBox.warning(self, "提示", f"打开目录失败：{e}")

    # ---------------- 路径与参数 ----------------

    def _browse_assets(self):
        start = str(resolve_assets(self.edit_assets.text().strip() or DEFAULT_ASSETS_REL))
        path = QFileDialog.getExistingDirectory(self, "选择美术库 Assets 目录", start)
        if path:
            self.edit_assets.setText(path)

    def _validate_path(self):
        text = self.edit_assets.text().strip()
        resolved = resolve_assets(text) if text else None
        if resolved is not None and resolved.is_dir():
            self.label_path.setText(f"→ {resolved}")
            self.label_path.setStyleSheet(f"color:{THEME['ok']}; font-size:11px;")
            self._path_ok = True
            self._set_badge(True, "路径有效")
        else:
            shown = f"→ {resolved}" if resolved is not None else "未填写路径"
            self.label_path.setText(f"{shown}   ✗ 路径不存在")
            self.label_path.setStyleSheet(f"color:{THEME['danger']}; font-size:11px;")
            self._path_ok = False
            self._set_badge(False, "路径无效")
        self._update_buttons()

    def _scale(self) -> float:
        return self.spin_scale.value()

    def _update_scale_hint(self, *_):
        s = self.spin_scale.value()
        self.label_scale.setText(
            f"2560×1440 基准 → {image_snap(2560 * s)}×{image_snap(1440 * s)}")

    # ---------------- 忙碌状态 ----------------

    def _busy(self) -> bool:
        # 以显式标志为准：worker 刚 start 的瞬间 isRunning() 仍可能为 False，
        # 会让紧随其后的 _update_buttons() 把刚禁用的按钮又放开。
        return self._busy_flag

    def _set_busy(self, busy: bool, fmt: str = "", stoppable: bool = False):
        self._busy_flag = busy
        self._stoppable = stoppable if busy else False
        if busy:
            self.progress.setRange(0, 0)
            self.progress.setFormat(fmt or "处理中…")
            self._set_status(fmt or "处理中…")
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.progress.setFormat(fmt or "就绪")
            self._set_status(fmt or "就绪")
        self._update_buttons()

    def _update_buttons(self):
        # busy 时也要走完整分支：任务刚启动的瞬间 worker 尚未进入 isRunning，
        # 旧实现直接 return 会让按钮被重新启用（扫描进行中还能再点「扫描」）。
        busy = self._busy()
        ok = self._path_ok and not busy
        self.btn_scan.setEnabled(ok)
        self.btn_process.setEnabled(ok)
        fonts_ready = ok and self.combo_font.count() > 0
        self.btn_trial.setEnabled(fonts_ready)
        self.btn_all_fonts.setEnabled(fonts_ready)
        self.btn_stop.setEnabled(busy and self._stoppable)

    def _log(self, text: str, level: str = "info"):
        stamp = time.strftime("%H:%M:%S")
        colors = {"info": THEME["text_dim"], "ok": THEME["ok"],
                  "warn": THEME["warn"], "error": THEME["danger"]}
        marks = {"info": "·", "ok": "✓", "warn": "!", "error": "✗"}
        color = colors.get(level, THEME["text_dim"])
        mark = marks.get(level, "·")
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace("\n", "<br>"))
        self.log.appendHtml(
            f'<span style="color:{THEME["text_mute"]}">{stamp}</span>&nbsp;'
            f'<span style="color:{color}">{mark} {safe}</span>')

    # ---------------- 扫描 ----------------

    def _scan(self):
        if not self._path_ok:
            QMessageBox.warning(self, "提示", "美术库路径不存在，请先选择正确的 Assets 目录")
            return
        self._last_action = "scan"
        self._set_busy(True, "扫描中…", stoppable=False)   # build_scan_report 不支持中断
        self._log("开始扫描(dry-run，不修改文件)…")
        self.worker = ScanWorker(resolve_assets(self.edit_assets.text()),
                                 self._scale(), self.record_path,
                                 self.edit_filter.text().strip(), self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._scan_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _scan_done(self, text: str, stats: dict):
        self.info.setPlainText(text)
        fonts = stats.get("fonts", [])
        cur_key = self.combo_font.currentData()
        self.combo_font.clear()
        for display, key in fonts:
            self.combo_font.addItem(display, key)
        self.combo_font.setEnabled(bool(fonts))
        idx = self.combo_font.findData(cur_key) if cur_key else -1
        if idx < 0:
            for i in range(self.combo_font.count()):
                if "Charge_Gold" in self.combo_font.itemText(i):
                    idx = i
                    break
        if idx >= 0:
            self.combo_font.setCurrentIndex(idx)
        self._update_stats(stats)
        self._set_busy(False, "扫描完成")
        self._log(f"扫描完成（{len(fonts)} 个字体可选）", "ok")
        self._refresh_record_count()

    # ---------------- 处理: 图片 ----------------

    def _process_images(self):
        if not self._path_ok:
            QMessageBox.warning(self, "提示", "美术库路径不存在")
            return
        filt = self.edit_filter.text().strip()
        scope = f"关键字“{filt}”过滤后" if filt else "全部"
        if QMessageBox.question(
                self, "确认处理",
                f"将把{scope}【未处理】的图片按 ×{self._scale()} 缩小。\n\n"
                "直接覆盖源图文件（路径与文件名不变，Unity 引用不受影响）；\n"
                "工程在 SVN 工作副本中，改错可回退；已处理项自动跳过。\n\n是否开始？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._last_action = "images"
        self._set_busy(True, "处理图片中…", stoppable=True)
        self._log("开始处理图片…")
        self.worker = ResizeWorker(resolve_assets(self.edit_assets.text()), self._scale(),
                                   self.record_path, "images", folder=filt, parent=self)
        self._wire_worker()

    # ---------------- 处理: 字体 ----------------

    def _trial_font(self):
        key = self.combo_font.currentData()
        display = self.combo_font.currentText()
        if not key:
            return
        record = load_record(self.record_path)
        force = key in record.get("fonts", {})
        if force and QMessageBox.question(
                self, "重复处理确认",
                f"字体“{display}”已处理过，重复执行会再次缩小。\n是否强制重跑？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._last_action = "fonts-trial"
        self._set_busy(True, f"试跑字体 {display}…", stoppable=True)
        self._log(f"试跑字体: {display}（{key}）")
        self.worker = ResizeWorker(resolve_assets(self.edit_assets.text()), self._scale(),
                                   self.record_path, "fonts",
                                   font_name=key, force=force, parent=self)
        self._wire_worker()

    def _process_all_fonts(self):
        if self.combo_font.count() == 0:
            QMessageBox.warning(self, "提示", "请先扫描，确认字体列表")
            return
        if QMessageBox.question(
                self, "确认处理",
                f"将把全部【未处理】的字体（图集 + 度量成对 ×{self._scale()}）处理。\n\n"
                "建议先用【试跑选中字体】在 Unity 里验收大小与基线，再执行此步。\n是否开始？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._last_action = "fonts-all"
        self._set_busy(True, "处理字体中…", stoppable=True)
        self._log("开始处理全部字体…")
        self.worker = ResizeWorker(resolve_assets(self.edit_assets.text()), self._scale(),
                                   self.record_path, "fonts", parent=self)
        self._wire_worker()

    # ---------------- worker 通用 ----------------

    def _wire_worker(self):
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, cur: int, total: int, msg: str):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(min(cur, total))
            self.progress.setFormat(f"{msg} {cur}/{total}")
            self._set_status(f"{msg} {cur}/{total}")
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat(msg)
            self._set_status(msg)

    def _on_done(self, summary: str):
        self._set_busy(False, "完成")
        self._log(summary, "ok")
        title = "完成"
        tip = ""
        if self._last_action == "images":
            tip = "\n\n提醒: 运行态生效需重新打包 UI bundle 与图集。"
        elif self._last_action == "fonts-trial":
            tip = ("\n\n请打开 Unity 验收该字体: 大小是否与界面协调、基线是否跑偏。\n"
                   "满意后回到本工具点【处理全部字体】。")
        elif self._last_action == "fonts-all":
            tip = "\n\n提醒: 运行态生效需重新打包 UI bundle 与图集。"
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(summary + tip + f"\n\n记录文件: {self.record_path}")
        btn_open = box.addButton("打开记录所在目录", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is btn_open:
            self._open_record_dir()
        self._refresh_record_count()
        # 处理完后自动刷新一遍预览(不强制)
        if self._path_ok and self._last_action in ("images", "fonts-all"):
            self._scan()

    def _on_failed(self, msg: str):
        self._set_busy(False, "失败")
        self._log(f"[失败] {msg}", "error")
        QMessageBox.critical(self, "失败", msg)

    def _stop_worker(self):
        if self.worker is None or not self.worker.isRunning():
            return
        request_stop = getattr(self.worker, "request_stop", None)
        if request_stop is None:
            # ScanWorker 没有中断接口（扫描是只读预览）；按钮本应处于禁用态，这里兜底
            self._log("当前任务不支持中断，请等待完成", "warn")
            return
        request_stop()
        self._log("已请求中断（当前项完成后停止；已处理项已记入记录，可直接续跑）…", "warn")
        self.btn_stop.setEnabled(False)

    def closeEvent(self, event):
        if self._busy():
            if QMessageBox.question(
                    self, "退出确认",
                    "任务仍在进行中，确定退出？\n已处理项已记入记录，下次可继续。"
            ) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            request_stop = getattr(self.worker, "request_stop", None)
            if request_stop is not None:
                request_stop()
            if self.worker is not None:
                self.worker.wait(3000)
            self._busy_flag = False
        event.accept()


def run_gui() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
