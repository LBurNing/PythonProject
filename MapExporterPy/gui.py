"""PySide6 图形界面(样式参考 D:/PythonProject/Gif2Png/Gif2PngUI.py)。

暗色主题 + SectionCard 卡片分组 + QThread 后台导出 + 进度条。
"""

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QSizePolicy, QSpinBox, QVBoxLayout,
                               QWidget)

from main import export_map, scan_libraries
from map_py.map_parser import MapParseError, MapReader
from map_py.renderer import RenderConfig, Renderer
from map_py.wil_library import PngLibrary


class SectionCard(QFrame):
    """卡片式分组容器:左侧彩色色条标题 + 内容区(Gif2PngUI 样式)。"""

    def __init__(self, title, accent="#4488ff", parent=None):
        super().__init__(parent)
        self.setObjectName("sectionCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)
        header = QLabel(title)
        header.setStyleSheet(
            f"QLabel {{ color: #c8c8dc; font-weight: bold; font-size: 11px; "
            f"border-left: 3px solid {accent}; padding-left: 8px; "
            f"padding-top: 1px; padding-bottom: 1px; }}"
        )
        outer.addWidget(header)
        self.content = QVBoxLayout()
        self.content.setSpacing(7)
        outer.addLayout(self.content)

    def addWidget(self, w):
        self.content.addWidget(w)

    def addLayout(self, l):
        self.content.addLayout(l)


class ExportWorker(QThread):
    """后台导出线程:资源扫描 + 全部地图导出,完成后再通知。"""

    progress = Signal(int, int, str)      # 当前, 总数, 消息
    done = Signal(str)                    # 导出的地图名(换行分隔)
    failed = Signal(str)                  # 错误信息

    def __init__(self, map_paths, data_dir, cfg, parent=None):
        super().__init__(parent)
        self.map_paths = list(map_paths)
        self.data_dir = data_dir
        self.cfg = cfg

    def run(self):
        try:
            self.progress.emit(0, 0, "扫描资源...")
            libs = scan_libraries(self.data_dir)
            if not libs:
                self.failed.emit("未找到资源库(图片目录或 WZL/WZX)")
                return
            names = []
            for p in self.map_paths:
                names.append(export_map(p, libs, self.cfg, self.progress.emit))
            self.done.emit("\n".join(names))
        except (MapParseError, FileNotFoundError) as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class PreviewWorker(QThread):
    """后台预览渲染线程:快速模式渲染地图并生成缩略图。"""

    done = Signal(str)                    # 预览图路径
    failed = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, data_dir, map_path, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self.map_path = map_path

    def run(self):
        try:
            from PIL import Image as PILImage
            libs = scan_libraries(self.data_dir)
            if not libs:
                self.failed.emit("未找到资源库(图片目录或 WZL/WZX)")
                return
            tmp = Path(tempfile.mkdtemp())
            cfg = RenderConfig(out_root=tmp, preview=True, img_format="png",
                               export_anim=False, map_name="preview")
            reader = MapReader(self.map_path)
            Renderer(reader, libs, cfg, self.progress.emit).run()
            png = tmp / "preview" / "preview.png"
            img = PILImage.open(png)
            img.thumbnail((640, 480))
            out = tmp / "preview_small.png"
            img.save(out)
            self.done.emit(str(out))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("地图导出工具")
        self.resize(1100, 780)
        self.setMinimumSize(900, 600)
        self.libs = {}
        self.worker = None
        self._preview_pix = None
        self._build_ui()
        self.setStyleSheet(self._build_stylesheet())

    # ---------------- 界面 ----------------

    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # --- 文件卡片 ---
        file_card = SectionCard("地图与资源", "#4488ff")
        row = QHBoxLayout()
        row.addWidget(QLabel("数据文件夹:"))
        self.edit_data = QLineEdit()
        self.edit_data.setPlaceholderText("包含 .map 与资源(Objects/SmTiles/Tiles 的 PNG 或 wzl)的文件夹")
        self.edit_data.textChanged.connect(
            lambda: QTimer.singleShot(500, self._update_info))
        row.addWidget(self.edit_data, 1)
        btn = QPushButton("浏览...")
        btn.clicked.connect(self._browse_data)
        row.addWidget(btn)
        file_card.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("输出目录:"))
        self.edit_out = QLineEdit()
        self.edit_out.setPlaceholderText("默认: 数据文件夹/导出结果")
        row.addWidget(self.edit_out, 1)
        btn = QPushButton("浏览...")
        btn.clicked.connect(self._browse_out)
        row.addWidget(btn)
        file_card.addLayout(row)
        root.addWidget(file_card)

        # --- 信息卡片 ---
        info_card = SectionCard("地图信息", "#ff8800")
        self.label_info = QLabel("未选择数据文件夹")
        self.label_info.setObjectName("secondaryLabel")
        self.label_info.setWordWrap(True)
        info_card.addWidget(self.label_info)

        row = QHBoxLayout()
        self.btn_preview = QPushButton("预览地图")
        self.btn_preview.clicked.connect(self._preview)
        row.addWidget(self.btn_preview)
        self.label_preview = QLabel("")
        self.label_preview.setAlignment(Qt.AlignCenter)
        self.label_preview.setMinimumHeight(280)
        self.label_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        row.addWidget(self.label_preview, 1)
        info_card.addLayout(row)
        root.addWidget(info_card)

        # --- 导出卡片 ---
        export_card = SectionCard("导出", "#00cc66")
        row = QHBoxLayout()
        row.addWidget(QLabel("导出地图名:"))
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("默认: .map 文件名")
        row.addWidget(self.edit_name, 1)
        export_card.addLayout(row)

        row = QHBoxLayout()
        self.check_anim = QCheckBox("导出动画(序列帧)")
        self.check_anim.setToolTip("导出动画序列帧到 anims/ 目录(默认不导出)")
        row.addWidget(self.check_anim)
        row.addSpacing(10)
        row.addWidget(QLabel("格式:"))
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["jpg", "png"])
        row.addWidget(self.combo_fmt)
        row.addSpacing(10)
        row.addWidget(QLabel("JPG品质:"))
        self.spin_quality = QSpinBox()
        self.spin_quality.setRange(1, 100)
        self.spin_quality.setValue(90)
        self.spin_quality.setToolTip("JPG 输出品质(1-100)")
        row.addWidget(self.spin_quality)
        row.addStretch(1)
        export_card.addLayout(row)

        row = QHBoxLayout()
        self.btn_export = QPushButton("导出大图")
        self.btn_export.setObjectName("primaryButton")
        self.btn_export.clicked.connect(self._export)
        row.addWidget(self.btn_export)
        self.progress = QProgressBar()
        row.addWidget(self.progress, 1)
        export_card.addLayout(row)
        root.addWidget(export_card)

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
        #primaryButton:disabled { background: #2a2a3a; color: #606070; border-color: #323248; }
        QLineEdit {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 4px;
            padding: 4px 8px; color: #e0e0e0; min-height: 22px;
        }
        QLineEdit:hover { border-color: #4e4e6e; }
        QProgressBar {
            background: #2a2a3a; border: 1px solid #323248; border-radius: 4px;
            text-align: center; color: #e0e0e0; min-height: 20px;
        }
        QProgressBar::chunk { background: #ff6600; border-radius: 3px; }
        QLabel { color: #e0e0e0; }
        #secondaryLabel { color: #9090a8; font-size: 11px; }
        QMessageBox { background: #262638; color: #e0e0e0; }
        """

    # ---------------- 浏览与信息 ----------------

    def _browse_data(self):
        path = QFileDialog.getExistingDirectory(self, "选择数据文件夹")
        if path:
            self.edit_data.setText(path)
            if not self.edit_out.text().strip():
                self.edit_out.setText(str(Path(path) / "导出结果"))
            self._update_info()

    def _browse_out(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.edit_out.setText(path)

    def _update_info(self):
        data_dir = self.edit_data.text().strip()
        if not data_dir or not Path(data_dir).is_dir():
            self.label_info.setText("未选择数据文件夹")
            return
        maps = sorted(Path(data_dir).glob("*.map"))
        lines = []
        if not maps:
            lines.append("文件夹中未找到 .map 文件")
        for mp in maps:
            try:
                reader = MapReader(mp)
                anim = reader.cells["front_anim_frame"]
                anim_count = int(((anim & 0x7F) > 0).sum())
                blend_count = int(((anim & 0x80) > 0).sum())
                anim_txt = (f"序列帧: {'有' if anim_count else '无'}"
                            f"({anim_count}格动画, 混合{blend_count}格)")
                lines.append(
                    f"地图: {reader.map_name} | 格式: Type{reader.format_type} "
                    f"({reader.cell_bytes}字节/格) | 格子: {reader.width}x{reader.height} | "
                    f"大图: {reader.pixel_width}x{reader.pixel_height} | {anim_txt}")
            except (MapParseError, FileNotFoundError) as e:
                lines.append(f"{mp.name}: 加载失败 - {e}")
        # 自动检测资源:图片目录(PNG/JPG/BMP)优先,wzl/wzx 兜底
        try:
            libs = scan_libraries(data_dir)
        except Exception as e:
            libs = {}
            lines.append(f"资源检测失败: {e}")
        if libs:
            for slot, lib in sorted(libs.items()):
                kind = "图片目录" if isinstance(lib, PngLibrary) else "WZL"
                lines.append(f"资源[{slot}]: {lib.name} ({kind})")
        else:
            lines.append("警告: 未找到资源库(图片目录或 WZL/WZX)")
        self.label_info.setText("\n".join(lines))

    # ---------------- 预览 ----------------

    def _preview(self):
        data_dir = self.edit_data.text().strip()
        if not data_dir or not Path(data_dir).is_dir():
            QMessageBox.warning(self, "提示", "请选择数据文件夹")
            return
        maps = sorted(Path(data_dir).glob("*.map"))
        if not maps:
            QMessageBox.warning(self, "提示", "未找到 .map 文件")
            return
        self.btn_preview.setEnabled(False)
        self.label_preview.setText("渲染预览中...\n(大图可能需等待)")
        self.preview_worker = PreviewWorker(data_dir, maps[0], self)
        self.preview_worker.progress.connect(self._on_progress)
        self.preview_worker.done.connect(self._preview_done)
        self.preview_worker.failed.connect(self._preview_failed)
        self.preview_worker.start()

    def _preview_done(self, path):
        self.btn_preview.setEnabled(True)
        self.label_preview.setText("")
        self._preview_pix = QPixmap(path)
        if not self._preview_pix.isNull():
            self._show_preview()
        else:
            self.label_preview.setText("预览图生成失败")

    def _show_preview(self):
        """按预览区当前大小缩放显示预览图(窗口/全屏自适应)。"""
        if self._preview_pix is None or self._preview_pix.isNull():
            return
        avail = self.label_preview.size()
        if avail.width() > 20 and avail.height() > 20:
            pix = self._preview_pix.scaled(avail, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
            self.label_preview.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_preview()

    def _preview_failed(self, msg):
        self.btn_preview.setEnabled(True)
        self.label_preview.setText("")
        QMessageBox.critical(self, "预览失败", msg)

    # ---------------- 导出 ----------------

    def _export(self):
        data_dir = self.edit_data.text().strip()
        out_root = self.edit_out.text().strip()
        if not data_dir or not Path(data_dir).is_dir():
            QMessageBox.warning(self, "提示", "请选择数据文件夹")
            return
        maps = sorted(Path(data_dir).glob("*.map"))
        if not maps:
            QMessageBox.warning(self, "提示", "文件夹中未找到 .map 文件")
            return
        if not out_root:
            out_root = str(Path(data_dir) / "导出结果")
            self.edit_out.setText(out_root)
        cfg = RenderConfig(
            out_root=Path(out_root),
            map_name=self.edit_name.text().strip() or None,
            export_anim=self.check_anim.isChecked(),
            img_format=self.combo_fmt.currentText(),
            jpg_quality=self.spin_quality.value(),
        )

        self.btn_export.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setFormat("准备导出...")
        self.worker = ExportWorker(maps, data_dir, cfg, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._export_done)
        self.worker.failed.connect(self._export_failed)
        self.worker.start()

    def _on_progress(self, cur, total, msg):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(min(cur, total))
            self.progress.setFormat(f"{msg} {cur}/{total}")
        else:
            self.progress.setRange(0, 0)         # busy 模式(扫描/准备)
            self.progress.setFormat(msg)

    def _export_done(self, names):
        self.btn_export.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.progress.setFormat("完成")
        out_root = self.edit_out.text().strip()
        fmt = self.combo_fmt.currentText()
        lines = ["导出完成!"]
        for name in names.splitlines():
            img = Path(out_root) / name / f"{name}.{fmt}"
            size_mb = img.stat().st_size / 1024 / 1024 if img.is_file() else 0
            lines.append(f"{name}.{fmt} ({size_mb:.1f} MB)")
        lines.append(f"目录: {Path(out_root)}")
        QMessageBox.information(self, "完成", "\n".join(lines))

    def _export_failed(self, msg):
        self.btn_export.setEnabled(True)
        QMessageBox.critical(self, "导出失败", msg)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)
        event.accept()


def run_gui() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
