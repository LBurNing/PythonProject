"""笔刷涂抹工具。

打开图片 → 选择笔刷颜色(默认黑色)与大小 → 按住左键涂抹 → 保存 / 另存为。
支持滚轮缩放、适应窗口、拖入图片、还原原图。

运行:
  python BrushTool.py [图片路径]
"""

import os
import sys
from pathlib import Path

# Qt 图片解码默认限制 256MB,大地图 PNG 会超过;放宽到 4GB(可在外部覆盖)
os.environ.setdefault("QT_IMAGEIO_MAXALLOC", "4096")

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QImage, QKeySequence, QPainter, QPen,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QColorDialog, QFileDialog,
                               QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")

STYLE = """
QMainWindow, QWidget {
    background: #1e1e2e; color: #e0e0e0;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 12px;
}
QPushButton {
    background: #3a3a52; border: 1px solid #4a4a68; border-radius: 5px;
    padding: 6px 14px; color: #e0e0e0; font-size: 12px;
}
QPushButton:hover { background: #4a4a6a; border-color: #5a5a7a; }
QPushButton:pressed { background: #2e2e44; }
QPushButton:disabled { background: #2a2a3a; color: #606070; border-color: #323248; }
QSpinBox {
    background: #2e2e44; border: 1px solid #3e3e58; border-radius: 6px;
    padding: 4px 8px; color: #e0e0e0; min-height: 22px; min-width: 70px;
}
QSpinBox:focus { border-color: #ff8833; }
QLabel { color: #a8a8c0; }
QMessageBox { background: #262638; color: #e0e0e0; }
"""


class BrushCanvas(QWidget):
    """图片画布:等比缩放显示 + 笔刷连续涂抹(图像坐标绘制,与缩放无关)。"""

    viewChanged = Signal()          # 缩放/适应窗口变化
    modified = Signal()             # 涂抹修改了图像
    fileDropped = Signal(str)       # 拖入图片

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self._source_path: str | None = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._last: QPointF | None = None
        self._hover: QPointF | None = None
        self._fit = True
        self._panning = False
        self._pan_start = QPointF(0, 0)
        self._pan_offset = QPointF(0, 0)
        self.brush_color = QColor(0, 0, 0)
        self.brush_size = 20
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.setMinimumSize(320, 240)

    # ---------------- 图像 ----------------

    @property
    def image(self) -> QImage | None:
        return self._image

    @property
    def source_path(self) -> str | None:
        return self._source_path

    @property
    def zoom(self) -> float:
        return self._scale

    def load_image(self, path: str | Path) -> bool:
        img = QImage(str(path))
        if img.isNull():
            return False
        self._image = img.convertToFormat(QImage.Format.Format_ARGB32)
        self._source_path = str(path)
        self._last = None
        self._fit = True
        self.fit_to_window()
        return True

    def reload_source(self) -> bool:
        """丢弃涂抹,重新从原图加载。"""
        return bool(self._source_path) and self.load_image(self._source_path)

    def save_image(self, path: str | Path) -> bool:
        if self._image is None:
            return False
        img = self._image
        if str(path).lower().endswith((".jpg", ".jpeg")):
            img = img.convertToFormat(QImage.Format.Format_RGB32)   # JPEG 无 alpha
        return img.save(str(path))

    # ---------------- 视图 ----------------

    def fit_to_window(self) -> None:
        if self._image is None:
            return
        iw, ih = self._image.width(), self._image.height()
        aw, ah = max(1, self.width() - 24), max(1, self.height() - 24)
        self._scale = min(aw / iw, ah / ih, 4.0)
        self._offset = QPointF((self.width() - iw * self._scale) / 2,
                               (self.height() - ih * self._scale) / 2)
        self._fit = True
        self.viewChanged.emit()
        self.update()

    def _image_rect(self):
        return QRectF(self._offset.x(), self._offset.y(),
                      self._image.width() * self._scale,
                      self._image.height() * self._scale)

    def resizeEvent(self, event) -> None:
        if self._fit:
            self.fit_to_window()
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        if self._image is None:
            return
        factor = 1.2 ** (event.angleDelta().y() / 120.0)
        new_scale = max(0.02, min(self._scale * factor, 16.0))
        pos = event.position()
        self._offset = pos - (pos - self._offset) * (new_scale / self._scale)
        self._scale = new_scale
        self._fit = False
        self.viewChanged.emit()
        self.update()

    # ---------------- 鼠标涂抹 ----------------

    def _to_image(self, pos: QPointF) -> QPointF:
        return (pos - self._offset) / self._scale

    def stroke(self, a: QPointF, b: QPointF) -> None:
        """在图像坐标 a→b 之间画一段圆头笔刷线(单点则画圆点)。"""
        if self._image is None:
            return
        p = QPainter(self._image)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(self.brush_color, float(self.brush_size),
                      Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if a == b:
            p.drawPoint(b)
        else:
            p.drawLine(a, b)
        p.end()
        self.modified.emit()
        self.update()

    def mousePressEvent(self, event) -> None:
        if self._image is None:
            return
        if event.button() == Qt.MiddleButton:
            # 中键拖动平移视图
            self._panning = True
            self._pan_start = event.position()
            self._pan_offset = QPointF(self._offset)
            self._hover = None
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            return
        if event.button() != Qt.LeftButton:
            return
        point = self._to_image(event.position())
        self._last = point
        self.stroke(point, point)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            self._offset = self._pan_offset + (event.position() - self._pan_start)
            self._clamp_offset()
            self._fit = False
            self.update()
            return
        self._hover = event.position()
        if (self._image is not None and self._last is not None
                and event.buttons() & Qt.LeftButton):
            point = self._to_image(event.position())
            self.stroke(self._last, point)
            self._last = point
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            self.update()
            return
        self._last = None

    def _clamp_offset(self) -> None:
        """平移时保证图像至少有一部分留在视口内,避免拖丢。"""
        if self._image is None:
            return
        w = self._image.width() * self._scale
        h = self._image.height() * self._scale
        margin = 40
        x = min(max(self._offset.x(), margin - w), self.width() - margin)
        y = min(max(self._offset.y(), margin - h), self.height() - margin)
        self._offset = QPointF(x, y)

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()

    # ---------------- 拖放 ----------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(
                u.toLocalFile().lower().endswith(IMG_EXTS)
                for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(IMG_EXTS):
                self.fileDropped.emit(path)
                return

    # ---------------- 绘制 ----------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#181826"))
        if self._image is None:
            p.setPen(QColor("#6a6a85"))
            p.drawText(self.rect(), Qt.AlignCenter, "打开图片,或把图片拖到这里")
            return
        target = self._image_rect()
        # 缩小显示时平滑,放大时用最近邻便于看清像素
        p.setRenderHint(QPainter.SmoothPixmapTransform, self._scale < 1.0)
        p.drawImage(target, self._image)
        p.setPen(QColor("#4a4a68"))
        p.drawRect(target)
        if self._hover is not None:
            radius = max(2.0, self.brush_size * self._scale / 2)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1, Qt.DashLine))
            p.drawEllipse(self._hover, radius, radius)
            p.setPen(QPen(QColor(0, 0, 0, 180), 1))
            p.drawEllipse(self._hover, radius + 1, radius + 1)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("笔刷涂抹工具")
        self.resize(1200, 800)
        self.setMinimumSize(760, 520)
        self._save_path: str | None = None
        self._dirty = False
        self._build_ui()
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.canvas = BrushCanvas(self)

        bar = QHBoxLayout()
        self.btn_open = QPushButton("打开图片")
        self.btn_open.clicked.connect(self._open)
        bar.addWidget(self.btn_open)

        self.btn_save = QPushButton("保存")
        self.btn_save.clicked.connect(self._save)
        bar.addWidget(self.btn_save)

        self.btn_save_as = QPushButton("另存为...")
        self.btn_save_as.clicked.connect(self._save_as)
        bar.addWidget(self.btn_save_as)

        self.btn_reload = QPushButton("还原原图")
        self.btn_reload.setToolTip("丢弃涂抹,重新加载打开时的原图")
        self.btn_reload.clicked.connect(self._reload)
        bar.addWidget(self.btn_reload)

        bar.addSpacing(16)
        self.btn_color = QPushButton()
        self.btn_color.setToolTip("选择笔刷颜色(默认黑色)")
        self.btn_color.clicked.connect(self._choose_color)
        bar.addWidget(self.btn_color)
        self._update_color_button()

        bar.addSpacing(16)
        bar.addWidget(QLabel("笔刷大小:"))
        self.spin_size = QSpinBox()
        self.spin_size.setRange(1, 1000)
        self.spin_size.setValue(20)
        self.spin_size.setSuffix(" px")
        self.spin_size.valueChanged.connect(self._on_size_changed)
        bar.addWidget(self.spin_size)

        bar.addSpacing(16)
        self.btn_fit = QPushButton("适应窗口")
        self.btn_fit.clicked.connect(self._fit)
        bar.addWidget(self.btn_fit)
        bar.addStretch(1)
        root.addLayout(bar)

        self.canvas.viewChanged.connect(self._update_status)
        self.canvas.modified.connect(self._on_modified)
        self.canvas.fileDropped.connect(self.open_path)
        root.addWidget(self.canvas, 1)

        self.label_status = QLabel("未打开图片")
        root.addWidget(self.label_status)
        self.setCentralWidget(central)

    def _bind_shortcuts(self) -> None:
        for key, slot in (("Ctrl+O", self._open), ("Ctrl+S", self._save),
                          ("Ctrl+Shift+S", self._save_as), ("Ctrl+0", self._fit)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(slot)

    # ---------------- 状态 ----------------

    def _on_size_changed(self, value: int) -> None:
        self.canvas.brush_size = value
        self.canvas.update()
        self._update_status()

    def _on_modified(self) -> None:
        self._dirty = True
        self._update_status()

    def _update_color_button(self) -> None:
        color = self.canvas.brush_color
        fg = "#000000" if color.lightness() > 128 else "#ffffff"
        self.btn_color.setStyleSheet(
            f"QPushButton {{ background: {color.name()}; color: {fg}; "
            f"border: 1px solid #5a5a7a; border-radius: 5px; padding: 6px 14px; }}"
            f"QPushButton:hover {{ border-color: #8888aa; }}")
        self.btn_color.setText(f"笔刷颜色 {color.name().upper()}")

    def _update_status(self) -> None:
        canvas = self.canvas
        if canvas.image is None:
            self.label_status.setText("未打开图片")
            return
        name = Path(canvas.source_path).name if canvas.source_path else ""
        dirty = "  *未保存" if self._dirty else ""
        self.label_status.setText(
            f"{name}  {canvas.image.width()}x{canvas.image.height()}  "
            f"缩放 {canvas.zoom * 100:.0f}%  笔刷 {canvas.brush_size}px "
            f"{canvas.brush_color.name().upper()}{dirty}  "
            f"|  中键拖动  滚轮缩放")

    # ---------------- 打开 / 保存 ----------------

    def open_path(self, path: str) -> None:
        if not self._confirm_discard():
            return
        if not self.canvas.load_image(path):
            QMessageBox.critical(self, "打开失败", f"无法读取图片:\n{path}")
            return
        self._save_path = None
        self._dirty = False
        self.setWindowTitle(f"笔刷涂抹工具 - {Path(path).name}")
        self._update_status()

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        if path:
            self.open_path(path)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(self.canvas.brush_color, self, "选择笔刷颜色")
        if color.isValid():
            self.canvas.brush_color = color
            self._update_color_button()
            self._update_status()

    def _save(self) -> None:
        if not self._check_image():
            return
        if self._save_path:
            self._write(self._save_path)
        else:
            self._save_as()

    def _save_as(self) -> None:
        if not self._check_image():
            return
        src = self.canvas.source_path
        if src:
            default = str(Path(src).with_name(Path(src).stem + "_涂抹.png"))
        else:
            default = "涂抹.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", default,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;BMP 图片 (*.bmp);;所有文件 (*)")
        if path:
            self._write(path)

    def _write(self, path: str) -> None:
        if not self.canvas.save_image(path):
            QMessageBox.critical(self, "保存失败", f"无法保存到:\n{path}")
            return
        self._save_path = path
        self._dirty = False
        self.label_status.setText(f"已保存: {path}")

    def _reload(self) -> None:
        if self.canvas.image is None:
            return
        if not self._confirm_discard():
            return
        self.canvas.reload_source()
        self._save_path = None
        self._dirty = False
        self._update_status()

    def _fit(self) -> None:
        self.canvas.fit_to_window()

    def _check_image(self) -> bool:
        if self.canvas.image is None:
            QMessageBox.information(self, "提示", "请先打开一张图片")
            return False
        return True

    def _confirm_discard(self) -> bool:
        """有未保存涂抹时询问;返回是否继续当前操作。"""
        if not self._dirty:
            return True
        ret = QMessageBox.question(
            self, "未保存", "当前涂抹尚未保存,是否保存?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ret == QMessageBox.Cancel:
            return False
        if ret == QMessageBox.Save:
            self._save()
            return not self._dirty
        return True

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    if len(argv) > 1 and Path(argv[1]).is_file():
        win.open_path(argv[1])
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
