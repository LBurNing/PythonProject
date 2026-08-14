# PySide6 序列帧透明化工具
# 功能: 选择序列帧文件夹自动播放预览 / 拖拽框选区域 /
#       「透明化」把每帧框内像素变透明, 其余不变, 输出保持原图尺寸 (保留原文件名)
import os
import re
import sys

from PIL import Image
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QProgressDialog, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

from eraser import erase_circles, map_circles

PLAY_INTERVAL = 80   # 播放帧间隔 ms (12.5fps)
SUPPORTED = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')


def pil_to_qimage(im):
    """PIL Image -> QImage (保留 alpha 通道; QImage 可在线程创建, QPixmap 必须主线程)"""
    im = im.convert('RGBA')
    data = im.tobytes('raw', 'RGBA')
    return QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888).copy()


def natural_key(name):
    """自然排序 key: frame_2.png < frame_10.png"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


def make_checker():
    """棋盘格背景 (显示透明区域用)"""
    pm = QPixmap(16, 16)
    p = QPainter(pm)
    p.fillRect(0, 0, 8, 8, QColor('#3a3a52'))
    p.fillRect(8, 8, 8, 8, QColor('#3a3a52'))
    p.fillRect(8, 0, 8, 8, QColor('#2a2a3a'))
    p.fillRect(0, 8, 8, 8, QColor('#2a2a3a'))
    p.end()
    return pm


class LoadWorker(QThread):
    """后台加载线程: 解码全部帧为 QImage + 记录尺寸/文件名"""
    progress = Signal(int, int)
    loaded = Signal(list, list, list)
    failed = Signal(str)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder

    def run(self):
        try:
            files = sorted((f for f in os.listdir(self.folder)
                            if os.path.splitext(f)[1].lower() in SUPPORTED), key=natural_key)
            total = len(files)
            sizes, qimages, names = [], [], []
            for i, f in enumerate(files):
                path = os.path.join(self.folder, f)
                with Image.open(path) as im:
                    sizes.append(im.size)
                    qimages.append(pil_to_qimage(im))
                names.append(f)
                if i % 5 == 0:
                    self.progress.emit(i, total)
            self.loaded.emit(sizes, qimages, names)
        except Exception as e:
            self.failed.emit(str(e))


class TransparentWorker(QThread):
    """后台透明化线程: 每帧把擦除圆区域画为全透明, 其余像素不变 (输出保持原尺寸)。
    circles: 归一化圆列表 [(nx, ny, nr), ...] (各帧尺寸不同也能正确映射)。
    jpg/bmp 输入无 alpha, 转存 PNG 保留透明。"""
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(int, str)

    def __init__(self, folder, out_dir, circles, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.out_dir = out_dir
        self.circles = circles

    def run(self):
        try:
            os.makedirs(self.out_dir, exist_ok=True)  # 防御: 输出目录不存在则创建
            files = sorted((f for f in os.listdir(self.folder)
                            if os.path.splitext(f)[1].lower() in SUPPORTED), key=natural_key)
            total = len(files)
            for i, f in enumerate(files):
                src = os.path.join(self.folder, f)
                with Image.open(src) as im:
                    if self.circles:
                        im = erase_circles(im, map_circles(self.circles,
                                                           im.width, im.height))
                    else:
                        im = im.convert('RGBA')
                    out_name = f
                    if os.path.splitext(f)[1].lower() in ('.jpg', '.jpeg', '.bmp'):
                        out_name = os.path.splitext(f)[0] + '.png'  # 透明只能存 PNG
                    im.save(os.path.join(self.out_dir, out_name))
                if i % 5 == 0 or i == total - 1:  # 最后一帧必发, 保证进度条走到头
                    self.progress.emit(i, total)
            self.done.emit(self.out_dir)
        except Exception as e:
            self.failed.emit(0, str(e))


class SectionCard(QFrame):
    """卡片式分组容器: 左侧彩色色条标题 + 内容区 (复刻 SeqFrameTool.py)"""
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

    def addWidget(self, w, stretch=0):
        self.content.addWidget(w, stretch)

    def addLayout(self, l):
        self.content.addLayout(l)


class PreviewLabel(QWidget):
    """预览控件: 等比缩放居中显示当前帧 + 涂抹擦除蒙版 (擦除区显示棋盘格)。
    按住鼠标拖动 = 笔刷擦除, 圆以归一化坐标存储 (跨帧一致, 导出逐帧映射)。"""
    erased = Signal()        # 擦除内容变化(新增一笔/撤销)
    erase_started = Signal()  # 开始涂抹 (主窗口暂停播放)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = None            # 当前帧 QPixmap (原图)
        self.disp_pm = None       # 缩放后的显示用 QPixmap
        self.offset = (0, 0)      # 图像显示区域左上角(控件内)
        self.scale = 1.0          # 显示缩放比例
        self.disp_size = (1, 1)   # 显示画布尺寸 (dw, dh)
        self.circles = []         # 归一化擦除圆 [(nx, ny, nr), ...]
        self.brush_size = 40      # 笔刷直径 (原图像素)
        self._last = None         # 拖动中上一位置 (显示坐标)
        self._checker = QBrush(make_checker())
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setBrush(QPalette.Window, self._checker)
        self.setPalette(pal)
        self.setMinimumSize(200, 200)
        self._relayout()

    # ---------- 帧与布局 ----------
    def set_frame(self, pm):
        self.pm = pm
        self._relayout()
        self.update()

    def undo(self):
        """撤销最后一笔 (可多次撤销)"""
        if self.circles:
            self.circles.pop()
            self.erased.emit()
            self.update()

    def _relayout(self):
        """按控件尺寸计算显示区域/缩放比例"""
        w, h = self.width(), self.height()
        if not self.pm or w <= 1 or h <= 1:
            self.disp_pm = None
            return
        iw, ih = self.pm.width(), self.pm.height()
        s = min(w / iw, h / ih)
        dw, dh = max(1, round(iw * s)), max(1, round(ih * s))
        self.scale = s
        self.offset = ((w - dw) // 2, (h - dh) // 2)
        self.disp_size = (dw, dh)
        self.disp_pm = self.pm.scaled(dw, dh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    # ---------- 涂抹擦除交互 ----------
    def mousePressEvent(self, e):
        if not self.pm or e.button() != Qt.LeftButton:
            return
        self.erase_started.emit()
        self._last = e.position()
        self._stroke(e.position())

    def mouseMoveEvent(self, e):
        if self._last is not None:
            self._stroke(e.position())

    def mouseReleaseEvent(self, e):
        self._last = None

    def _stroke(self, pos):
        """从上一位置到当前位置沿线插值画圆 (防快速拖动断点)"""
        dw, dh = self.disp_size
        if dw <= 0 or dh <= 0:
            return
        x = pos.x() - self.offset[0]
        y = pos.y() - self.offset[1]
        r_show = self.brush_size * self.scale / 2  # 笔刷半径 (显示坐标)
        x0, y0 = self._last.x() - self.offset[0], self._last.y() - self.offset[1]
        dist = ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
        steps = max(1, int(dist / max(1.0, r_show)))
        for i in range(1, steps + 1):
            self._add_circle(x0 + (x - x0) * i / steps,
                             y0 + (y - y0) * i / steps, r_show)
        self._last = pos

    def _add_circle(self, x, y, r_show):
        """显示坐标圆 -> 归一化存储 (钳制到图像区域, 拖出边缘时贴边擦除)"""
        dw, dh = self.disp_size
        nx = min(max(x / dw, 0.0), 1.0)
        ny = min(max(y / dh, 0.0), 1.0)
        self.circles.append((nx, ny, r_show / min(dw, dh)))
        self.erased.emit()
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        super().paintEvent(e)  # 棋盘格背景
        if not self.pm or not self.disp_pm:
            return
        p = QPainter(self)
        p.drawPixmap(self.offset[0], self.offset[1], self.disp_pm)
        # 擦除蒙版: 所有圆区域覆盖棋盘格 (显示为已透明)
        if self.circles:
            dw, dh = self.disp_size
            path = QPainterPath()
            for nx, ny, nr in self.circles:
                cx = self.offset[0] + nx * dw
                cy = self.offset[1] + ny * dh
                r = nr * min(dw, dh)
                path.addEllipse(cx - r, cy - r, r * 2, r * 2)
            p.save()
            p.setClipPath(path)
            p.fillRect(self.offset[0], self.offset[1], dw, dh, self._checker)
            p.restore()
        p.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('序列帧透明化')
        self.setMinimumSize(1280, 800)
        self.resize(1920, 1080)

        self.folder = None
        self.sizes = []       # [(w, h), ...]
        self.pixmaps = []     # [QPixmap, ...] 原图
        self.names = []       # [str, ...]
        self.idx = 0
        self.worker = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self._build_ui()
        self.setStyleSheet(self._build_stylesheet())

    # ---------------- 界面 ----------------
    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # --- 文件夹卡片 ---
        file_card = SectionCard('序列帧文件夹', '#4488ff')
        row = QHBoxLayout()
        row.addWidget(QLabel('文件夹:'))
        self.edit_dir = QLineEdit()
        self.edit_dir.setReadOnly(True)
        row.addWidget(self.edit_dir, 1)
        btn_browse = QPushButton('浏览...')
        btn_browse.clicked.connect(self._browse_folder)
        row.addWidget(btn_browse)
        file_card.addLayout(row)
        self.label_info = QLabel('未载入文件夹')
        self.label_info.setObjectName('secondaryLabel')
        file_card.addWidget(self.label_info)
        root.addWidget(file_card)

        # --- 预览卡片 ---
        play_card = SectionCard('预览 (按住鼠标拖动涂抹擦除)', '#ff8800')
        play_row = QHBoxLayout()
        self.btn_play = QPushButton('播放')
        self.btn_play.setObjectName('primaryButton')
        self.btn_play.clicked.connect(self._toggle_play)
        play_row.addWidget(self.btn_play)
        self.label_frame_count = QLabel('帧: 0/--')
        self.label_frame_count.setObjectName('secondaryLabel')
        play_row.addWidget(self.label_frame_count)
        play_row.addStretch(1)
        play_row.addWidget(QLabel('笔刷:'))
        self.spin_brush = QSpinBox()
        self.spin_brush.setRange(4, 500)
        self.spin_brush.setValue(40)
        self.spin_brush.setSuffix(' px')
        self.spin_brush.valueChanged.connect(self._on_brush_changed)
        play_row.addWidget(self.spin_brush)
        btn_undo = QPushButton('撤销')
        btn_undo.clicked.connect(self._undo_erase)
        play_row.addWidget(btn_undo)
        play_card.addLayout(play_row)
        self.preview = PreviewLabel()
        self.preview.erased.connect(self._on_erased)
        self.preview.erase_started.connect(self._on_erase_started)
        play_card.addWidget(self.preview, 1)
        root.addWidget(play_card, 1)

        # --- 透明化卡片 ---
        clear_card = SectionCard('透明化', '#00cc66')
        row = QHBoxLayout()
        row.addWidget(QLabel('输出:'))
        self.edit_out = QLineEdit()
        row.addWidget(self.edit_out, 1)
        btn_out = QPushButton('浏览...')
        btn_out.clicked.connect(self._browse_out)
        row.addWidget(btn_out)
        clear_card.addLayout(row)
        self.label_crop = QLabel('擦除: 0 笔')
        self.label_crop.setObjectName('secondaryLabel')
        self.label_crop.setFixedHeight(20)
        clear_card.addWidget(self.label_crop)
        self.label_hint = QLabel('提示: 涂抹区域变透明, 其余像素不变, 输出保持原图尺寸')
        self.label_hint.setObjectName('secondaryLabel')
        self.label_hint.setFixedHeight(20)
        clear_card.addWidget(self.label_hint)
        row = QHBoxLayout()
        self.btn_cut = QPushButton('透明化')
        self.btn_cut.setObjectName('primaryButton')
        self.btn_cut.setEnabled(False)
        self.btn_cut.clicked.connect(self._do_transparent)
        row.addWidget(self.btn_cut)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%v/%m  帧')
        row.addWidget(self.progress_bar, 1)
        clear_card.addLayout(row)
        root.addWidget(clear_card)

        self.setCentralWidget(central)

    # ---------------- 样式表 (复刻 SeqFrameTool.py) ----------------
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
        QPushButton:checked { background: #ff6600; border-color: #ff8833; color: #ffffff; }
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
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 4px;
            color: #e0e0e0; text-align: center; min-height: 22px;
        }
        QProgressBar::chunk { background: #ff6600; border-radius: 3px; }
        QLabel { color: #e0e0e0; }
        #secondaryLabel { color: #9090a8; font-size: 11px; }
        QMessageBox { background: #262638; color: #e0e0e0; }
        """

    # ---------------- 载入 ----------------
    def _browse_folder(self):
        start = self.edit_dir.text() or os.path.expanduser('~\\Desktop')
        path = QFileDialog.getExistingDirectory(self, '选择序列帧文件夹', start)
        if path:
            self._load_folder(path)

    def _load_folder(self, path):
        self.folder = path
        self.edit_dir.setText(path)
        files = [f for f in os.listdir(path) if os.path.splitext(f)[1].lower() in SUPPORTED]
        if not files:
            QMessageBox.warning(self, '提示', '该文件夹下没有图片文件')
            return
        self.timer.stop()
        self.btn_play.setEnabled(False)
        self.progress = QProgressDialog(f'正在加载 0/{len(files)} 帧...', None, 0, len(files), self)
        self.progress.setWindowTitle('加载进度')
        self.progress.setWindowModality(Qt.WindowModal)
        self.progress.setMinimumDuration(0)
        self.worker = LoadWorker(path)
        self.worker.progress.connect(
            lambda cur, total: (self.progress.setValue(cur),
                                self.progress.setLabelText(f'正在加载 {cur}/{total} 帧...')))
        self.worker.loaded.connect(self._on_loaded)
        self.worker.failed.connect(self._on_load_failed)
        self.worker.start()

    def _on_load_failed(self, msg):
        self.progress.close()
        self.btn_play.setEnabled(True)
        QMessageBox.critical(self, '加载失败', msg)

    def _on_loaded(self, sizes, qimages, names):
        self.progress.setValue(len(sizes))
        self.progress.close()
        self.sizes, self.pixmaps, self.names = \
            sizes, [QPixmap.fromImage(q) for q in qimages], names
        uniq = sorted(set(sizes))
        size_txt = f'{uniq[0][0]}x{uniq[0][1]}' if len(uniq) == 1 else \
            f'{uniq[0][0]}x{uniq[0][1]} ~ {uniq[-1][0]}x{uniq[-1][1]}'
        self.label_info.setText(f'帧数: {len(sizes)}    尺寸: {size_txt}')
        # 输出目录默认值: 同级下 输入文件夹名_透明
        if not self.edit_out.text().strip():
            self.edit_out.setText(os.path.join(os.path.dirname(self.folder),
                                               os.path.basename(self.folder) + '_透明'))
        # 默认自动播放
        self.idx = 0
        self._show_frame(0)
        self.btn_play.setEnabled(True)
        self.timer.start(PLAY_INTERVAL)
        self.btn_play.setText('暂停')
        self.btn_cut.setEnabled(True)

    # ---------------- 播放 ----------------
    def _toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText('播放')
        else:
            self.timer.start(PLAY_INTERVAL)
            self.btn_play.setText('暂停')

    def _tick(self):
        self.idx = (self.idx + 1) % len(self.pixmaps)
        self._show_frame(self.idx)

    def _show_frame(self, i):
        self.idx = i
        self.preview.set_frame(self.pixmaps[i])
        self.label_frame_count.setText(f'帧: {i + 1}/{len(self.pixmaps)}')

    def _on_brush_changed(self, v):
        self.preview.brush_size = v

    def _undo_erase(self):
        self.preview.undo()

    def _on_erase_started(self):
        """开始涂抹时暂停播放, 方便精细操作"""
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText('播放')

    def _on_erased(self):
        self.label_crop.setText(f'擦除: {len(self.preview.circles)} 笔')

    # ---------------- 透明化 ----------------
    def _browse_out(self):
        path = QFileDialog.getExistingDirectory(self, '选择输出文件夹',
                                                self.edit_out.text() or os.path.expanduser('~\\Desktop'))
        if path:
            self.edit_out.setText(path)

    def _do_transparent(self):
        if not self.pixmaps:
            return
        out_dir = self.edit_out.text().strip()
        if not out_dir:
            QMessageBox.warning(self, '提示', '请先设置输出目录')
            return
        if os.path.normpath(out_dir) == os.path.normpath(self.folder):
            QMessageBox.warning(self, '提示', '输出目录不能与输入文件夹相同')
            return
        if os.path.isdir(out_dir):
            old = [f for f in os.listdir(out_dir)
                   if os.path.splitext(f)[1].lower() in SUPPORTED]
            if old:
                ret = QMessageBox.question(
                    self, '确认', f'输出目录已有 {len(old)} 个文件, 清空后重新导出?',
                    QMessageBox.Yes | QMessageBox.No)
                if ret != QMessageBox.Yes:
                    return
                for f in old:
                    os.remove(os.path.join(out_dir, f))
        else:
            os.makedirs(out_dir, exist_ok=True)
        self.btn_cut.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.timer.stop()
        self.btn_play.setText('播放')
        self.progress_bar.setRange(0, len(self.sizes))
        self.progress_bar.setValue(0)
        self.worker_cut = TransparentWorker(self.folder, out_dir,
                                            list(self.preview.circles))
        self.worker_cut.progress.connect(
            lambda cur, total: (self.progress_bar.setRange(0, total),
                                self.progress_bar.setValue(cur)))
        self.worker_cut.done.connect(self._cut_done)
        self.worker_cut.failed.connect(self._cut_failed)
        self.worker_cut.start()

    def _cut_failed(self, idx, msg):
        self.btn_cut.setEnabled(True)
        self.btn_play.setEnabled(True)
        QMessageBox.critical(self, '透明化失败', f'帧 {idx}: {msg}')

    def _cut_done(self, out_dir):
        self.btn_cut.setEnabled(True)
        self.btn_play.setEnabled(True)
        self.progress_bar.setValue(self.progress_bar.maximum())  # 进度条走满
        QMessageBox.information(self, '完成', f'透明化完成!\n目录: {out_dir}')

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)
        if getattr(self, 'worker_cut', None) and self.worker_cut.isRunning():
            self.worker_cut.wait(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
