# PySide6 序列帧透明化工具
# 功能: 选择序列帧文件夹自动播放预览 / 拖拽框选区域 /
#       「透明化」把每帧框内像素变透明, 其余不变, 输出保持原图尺寸 (保留原文件名)
import os
import re
import sys

from PIL import Image
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QProgressDialog, QPushButton, QVBoxLayout, QWidget)

from rect_edit import RectEdit

PLAY_INTERVAL = 80   # 播放帧间隔 ms (12.5fps)
SUPPORTED = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')

CURSORS = {'tl': Qt.SizeFDiagCursor, 'tr': Qt.SizeBDiagCursor,
           'bl': Qt.SizeBDiagCursor, 'br': Qt.SizeFDiagCursor,
           'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor,
           't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
           'move': Qt.SizeAllCursor}


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
    """后台透明化线程: 每帧把框内区域覆盖为全透明, 其余像素不变 (输出保持原尺寸)。
    jpg/bmp 输入无 alpha, 转存 PNG 保留透明。"""
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(int, str)

    def __init__(self, folder, out_dir, nx, ny, nw, nh, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.out_dir = out_dir
        self.nbox = (nx, ny, nw, nh)

    def run(self):
        try:
            os.makedirs(self.out_dir, exist_ok=True)  # 防御: 输出目录不存在则创建
            files = sorted((f for f in os.listdir(self.folder)
                            if os.path.splitext(f)[1].lower() in SUPPORTED), key=natural_key)
            total = len(files)
            nx, ny, nw, nh = self.nbox
            for i, f in enumerate(files):
                src = os.path.join(self.folder, f)
                with Image.open(src) as im:
                    if im.mode != 'RGBA':
                        im = im.convert('RGBA')
                    w, h = im.width, im.height
                    box = (round(nx * w), round(ny * h),
                           round((nx + nw) * w), round((ny + nh) * h))
                    box = (max(0, box[0]), max(0, box[1]),
                           min(w, box[2]), min(h, box[3]))
                    if box[2] > box[0] and box[3] > box[1]:
                        # 框内直接覆盖全透明图块 (无需逐像素)
                        overlay = Image.new('RGBA', (box[2] - box[0], box[3] - box[1]),
                                            (0, 0, 0, 0))
                        im.paste(overlay, (box[0], box[1]))
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
    """预览控件: 等比缩放居中显示当前帧 + 叠加可拖拽裁剪框 (画布=显示尺寸, 映射回原图)"""
    rect_changed = Signal()  # 裁剪框变化(拖动/重置/换帧)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = None            # 当前帧 QPixmap (原图)
        self.disp_pm = None       # 缩放后的显示用 QPixmap
        self.offset = (0, 0)      # 图像显示区域左上角(控件内)
        self.scale = 1.0          # 显示缩放比例
        self.edit = RectEdit()
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setBrush(QPalette.Window, QBrush(make_checker()))
        self.setPalette(pal)
        self.setMinimumSize(200, 200)
        self._relayout()

    # ---------- 帧与布局 ----------
    def set_frame(self, pm):
        self.pm = pm
        self._relayout()
        self.edit.reset()
        self.rect_changed.emit()
        self.update()

    def reset_rect(self):
        if self.pm:
            self.edit.reset()
            self.rect_changed.emit()
            self.update()

    def _relayout(self):
        """按控件尺寸计算显示区域/缩放比例, 裁剪框按比例换算"""
        w, h = self.width(), self.height()
        if not self.pm or w <= 1 or h <= 1:
            self.disp_pm = None
            return
        iw, ih = self.pm.width(), self.pm.height()
        s = min(w / iw, h / ih)
        dw, dh = max(1, round(iw * s)), max(1, round(ih * s))
        self.scale = s
        self.offset = ((w - dw) // 2, (h - dh) // 2)
        self.disp_pm = self.pm.scaled(dw, dh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.edit.resize_canvas(dw, dh)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    # ---------- 裁剪框交互 ----------
    def mousePressEvent(self, e):
        if not self.pm:
            return
        px, py = e.position().x() - self.offset[0], e.position().y() - self.offset[1]
        if self.edit.hit_test(px, py) is not None:
            self.edit.start_drag(px, py)
            self.update()

    def mouseMoveEvent(self, e):
        if not self.pm:
            return
        px, py = e.position().x() - self.offset[0], e.position().y() - self.offset[1]
        if self.edit._drag:
            r = self.edit.drag_to(px, py)
            if r:
                self.setCursor(CURSORS[r[0]])
                self.rect_changed.emit()
        else:
            self.setCursor(CURSORS.get(self.edit.hit_test(px, py), Qt.ArrowCursor))
        self.update()

    def mouseReleaseEvent(self, e):
        self.edit.end_drag()

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        super().paintEvent(e)  # 棋盘格背景
        if not self.pm or not self.disp_pm:
            return
        p = QPainter(self)
        p.drawPixmap(self.offset[0], self.offset[1], self.disp_pm)
        # 裁剪框: 橙色虚线边框 + 4 角 handle
        x, y, w, h = self.edit.rect
        rx, ry = self.offset[0] + x, self.offset[1] + y
        pen = QPen(QColor('#ff6600'), 2)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(rx, ry, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#ff6600'))
        for hx, hy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
            p.drawRect(rx + hx - x - 3, ry + hy - y - 3, 6, 6)
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
        play_card = SectionCard('预览 (拖拽框上下左右框选透明区域)', '#ff8800')
        play_row = QHBoxLayout()
        self.btn_play = QPushButton('播放')
        self.btn_play.setObjectName('primaryButton')
        self.btn_play.clicked.connect(self._toggle_play)
        play_row.addWidget(self.btn_play)
        self.label_frame_count = QLabel('帧: 0/--')
        self.label_frame_count.setObjectName('secondaryLabel')
        play_row.addWidget(self.label_frame_count)
        play_row.addStretch(1)
        btn_reset = QPushButton('重置裁剪框')
        btn_reset.clicked.connect(self._reset_rect)
        play_row.addWidget(btn_reset)
        play_card.addLayout(play_row)
        self.preview = PreviewLabel()
        self.preview.rect_changed.connect(self._on_rect_changed)
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
        self.label_crop = QLabel('框选区: --')
        self.label_crop.setObjectName('secondaryLabel')
        self.label_crop.setFixedHeight(20)
        clear_card.addWidget(self.label_crop)
        self.label_hint = QLabel('提示: 框内区域变透明, 其余像素不变, 输出保持原图尺寸')
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

    def _reset_rect(self):
        self.preview.reset_rect()

    def _on_rect_changed(self):
        if not self.pixmaps:
            self.label_crop.setText('框选区: --')
            return
        x, y, w, h = self.preview.edit.to_original(self.pixmaps[self.idx].width(),
                                                   self.pixmaps[self.idx].height())
        self.label_crop.setText(f'框选区: x={x}, y={y}, w={w}, h={h} (原图坐标)')

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
        # 归一化框选区 (各帧尺寸可能不同, 逐帧映射)
        cw, ch = self.preview.edit.cw, self.preview.edit.ch
        x, y, w, h = self.preview.edit.rect
        nbox = (x / cw, y / ch, w / cw, h / ch)
        self.btn_cut.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.timer.stop()
        self.btn_play.setText('播放')
        self.progress_bar.setRange(0, len(self.sizes))
        self.progress_bar.setValue(0)
        self.worker_cut = TransparentWorker(self.folder, out_dir, *nbox)
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
