"""PySide6 图形界面(样式参考 D:/PythonProject/Gif2Png/Gif2PngUI.py)。

暗色主题 + SectionCard 卡片分组 + QThread 后台导出 + 进度条。
"""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from main import export_map, scan_libraries
from map_py.map_parser import MapParseError, MapReader
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
    """后台导出线程。"""

    progress = Signal(int, int, str)      # 当前, 总数, 消息
    done = Signal(str)                    # 地图名
    failed = Signal(str)                  # 错误信息

    def __init__(self, map_paths, libs, out_root, parent=None):
        super().__init__(parent)
        self.map_paths = list(map_paths)
        self.libs = libs
        self.out_root = out_root

    def run(self):
        try:
            for p in self.map_paths:
                name = export_map(p, self.libs, self.out_root, self.progress.emit)
                self.done.emit(name)
        except (MapParseError, FileNotFoundError) as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("地图导出工具")
        self.setMinimumSize(760, 480)
        self.libs = {}
        self.worker = None
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
        self.label_info = QLabel("未加载地图")
        self.label_info.setObjectName("secondaryLabel")
        info_card.addWidget(self.label_info)
        root.addWidget(info_card)

        # --- 导出卡片 ---
        export_card = SectionCard("导出", "#00cc66")
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
        if not maps:
            self.label_info.setText("文件夹中未找到 .map 文件")
            return
        # 自动检测资源:PNG 目录优先,wzl/wzx 兜底
        try:
            libs = scan_libraries(data_dir)
        except Exception as e:
            libs = {}
            self.label_info.setText(f"资源检测失败: {e}")
            return
        pngs = sum(1 for l in libs.values() if isinstance(l, PngLibrary))
        wzls = len(libs) - pngs
        try:
            reader = MapReader(maps[0])
            info = (f"地图: {reader.map_name}    格式: Type{reader.format_type}    "
                    f"格子: {reader.width} x {reader.height}    "
                    f"大图: {reader.pixel_width} x {reader.pixel_height} 像素")
        except (MapParseError, FileNotFoundError) as e:
            info = f"地图加载失败: {e}"
        if libs:
            info += f"\n共 {len(maps)} 个 .map | 资源库: {len(libs)} 个(PNG {pngs} / WZL {wzls})"
        else:
            info += f"\n共 {len(maps)} 个 .map | 警告: 未找到资源库(PNG 或 wzl)"
        self.label_info.setText(info)

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
        try:
            self.libs = scan_libraries(data_dir)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载资源失败: {e}")
            return
        if not self.libs:
            QMessageBox.warning(self, "提示", "文件夹中未找到资源库(PNG 或 wzl),导出结果将为空图")

        self.btn_export.setEnabled(False)
        self.progress.setValue(0)
        self.worker = ExportWorker(maps, self.libs, out_root, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._export_done)
        self.worker.failed.connect(self._export_failed)
        self.worker.start()

    def _on_progress(self, cur, total, msg):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(min(cur, total))
            self.progress.setFormat(f"{msg}{cur}/{total}")

    def _export_done(self, name):
        self.btn_export.setEnabled(True)
        out_root = self.edit_out.text().strip()
        png = Path(out_root) / name / f"{name}.png"
        size_mb = png.stat().st_size / 1024 / 1024 if png.is_file() else 0
        QMessageBox.information(self, "完成", f"导出完成!\n{name}.png ({size_mb:.1f} MB)\n目录: {png.parent}")

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
