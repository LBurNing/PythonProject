# PySide6 序列帧优化工具
# 功能: 播放序列帧(原图大小) / 缩放滑块实时显示缩放后尺寸与图集数量 /
#       TexturePacker Trim 模式计算 2048x2048 图集数量(帧间距4)
import os
import re
import sys

from PIL import Image
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QProgressDialog, QPushButton, QScrollArea, QSlider,
                               QVBoxLayout, QWidget)

ATLAS = 2048       # 图集边长
PADDING = 4        # TexturePacker 帧间距 (padding 语义: 每帧占 w+4)
PLAY_INTERVAL = 80 # 播放帧间隔 ms (12.5fps)

SUPPORTED = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')


def pil_to_qimage(im):
    """PIL Image -> QImage (保留 alpha 通道; QImage 可在线程创建, QPixmap 必须主线程)"""
    im = im.convert('RGBA')
    data = im.tobytes('raw', 'RGBA')
    return QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888).copy()


def natural_key(name):
    """自然排序 key: frame_2.png < frame_10.png"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


def trim_size(im):
    """TexturePacker Trim 模式: 裁掉全透明边, 返回非透明区域 (w, h);
    无 alpha 通道返回原尺寸; 全透明返回 (1, 1)"""
    if im.mode not in ('RGBA', 'LA', 'P'):
        return im.size
    bbox = im.convert('RGBA').getchannel('A').getbbox()
    if bbox is None:
        return (1, 1)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])


def even_size(w, h, scale):
    """按比例缩放并取偶 (最小 2px), 返回 (w', h')"""
    return (max(2, round(w * scale / 2) * 2), max(2, round(h * scale / 2) * 2))


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


# ---------------- MaxRects 装箱 (Best Short Side Fit, 模拟 TexturePacker 默认算法) ----------------
def _place_best(free, w, h):
    """在 free 矩形中按 Best Short Side Fit 选位置放置 (w, h), 就地分裂, 返回 (x, y) 或 None"""
    best_i = None
    best_ss = best_ls = None
    for i, (x, y, fw, fh) in enumerate(free):
        if w <= fw and h <= fh:
            ss = min(fw - w, fh - h)  # 短边剩余
            ls = max(fw - w, fh - h)  # 长边剩余
            if best_i is None or ss < best_ss or (ss == best_ss and ls < best_ls):
                best_i, best_ss, best_ls = i, ss, ls
    if best_i is None:
        return None
    x, y, fw, fh = free.pop(best_i)
    if fw - w > 0:
        free.append((x + w, y, fw - w, fh))  # 右侧 (高度为 fh, 标准 MaxRects 分裂)
    if fh - h > 0:
        free.append((x, y + h, fw, fh - h))  # 下方 (宽度为 fw)
    _prune(free)  # 移除被完全包含的空闲矩形, 避免重叠区域重复放置
    return (x, y)


def _prune(free):
    """移除被其他空闲矩形完全包含的矩形"""
    kept = []
    for i, (x, y, w, h) in enumerate(free):
        if any(j != i and x2 <= x and y2 <= y and x + w <= x2 + w2 and y + h <= y2 + h2
               for j, (x2, y2, w2, h2) in enumerate(free)):
            continue
        kept.append((x, y, w, h))
    free[:] = kept


def atlas_count(rects, scale=1.0):
    """MaxRects 装箱所需图集数。rects: [(w, h), ...] 帧尺寸(Trim 后或原尺寸)。
    scale: 全局缩放比例(缩放后取偶)。
    单帧(缩放后)放不进图集返回 None"""
    items = sorted(rects, key=lambda r: (r[0] + PADDING) * (r[1] + PADDING), reverse=True)
    bins = 0
    free = [(0, 0, ATLAS, ATLAS)]
    for w, h in items:
        if scale < 1.0:
            iw, ih = even_size(w, h, scale)  # 缩放后取偶
        else:
            iw, ih = w, h  # 原始尺寸
        iw += PADDING
        ih += PADDING
        if iw > ATLAS or ih > ATLAS:
            return None
        if _place_best(free, iw, ih) is None:
            bins += 1
            free = [(0, 0, ATLAS, ATLAS)]
            if _place_best(free, iw, ih) is None:
                return None
    return bins + 1


class LoadWorker(QThread):
    """后台加载线程: 解码全部帧为 QImage + 记录尺寸/Trim 尺寸/文件名
    (QImage 线程安全可在线程创建, 主线程再转 QPixmap)"""
    progress = Signal(int, int)  # 当前帧, 总帧数
    loaded = Signal(list, list, list, list)  # sizes, qimages(QImage), trims, names
    failed = Signal(str)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder

    def run(self):
        try:
            files = sorted((f for f in os.listdir(self.folder)
                            if os.path.splitext(f)[1].lower() in SUPPORTED), key=natural_key)
            total = len(files)
            sizes, qimages, trims, names = [], [], [], []
            for i, f in enumerate(files):
                path = os.path.join(self.folder, f)
                with Image.open(path) as im:
                    sizes.append(im.size)
                    trims.append(trim_size(im))
                    qimages.append(pil_to_qimage(im))
                names.append(f)
                if i % 5 == 0:
                    self.progress.emit(i, total)
            self.loaded.emit(sizes, qimages, trims, names)
        except Exception as e:
            self.failed.emit(str(e))


class ExportWorker(QThread):
    """后台缩小导出线程: 按缩放比例缩小全部帧 (取偶, LANCZOS 保品质, 保留透明)"""
    progress = Signal(int, int)  # 当前帧, 总帧数
    done = Signal(str)           # 输出目录
    failed = Signal(int, str)    # 帧号, 错误信息

    def __init__(self, folder, out_dir, scale, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.out_dir = out_dir
        self.scale = scale

    def run(self):
        try:
            files = sorted((f for f in os.listdir(self.folder)
                            if os.path.splitext(f)[1].lower() in SUPPORTED), key=natural_key)
            total = len(files)
            for i, f in enumerate(files):
                src = os.path.join(self.folder, f)
                with Image.open(src) as im:
                    if im.mode != 'RGBA':
                        im = im.convert('RGBA')
                    w, h = even_size(im.width, im.height, self.scale)
                    im = im.resize((w, h), Image.Resampling.LANCZOS)
                    if os.path.splitext(f)[1].lower() in ('.jpg', '.jpeg', '.bmp'):
                        im.convert('RGB').save(os.path.join(self.out_dir, f))
                    else:
                        im.save(os.path.join(self.out_dir, f))  # PNG/WebP 保留透明
                if i % 5 == 0:
                    self.progress.emit(i, total)
            self.done.emit(self.out_dir)
        except Exception as e:
            self.failed.emit(0, str(e))


class SectionCard(QFrame):
    """卡片式分组容器: 左侧彩色色条标题 + 内容区 (参考 Gif2PngUI.py)"""
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('序列帧优化')
        self.setMinimumSize(1280, 800)
        self.resize(1920, 1080)  # 默认窗口尺寸 (游戏编辑器标准分辨率)

        self.folder = None
        self.sizes = []       # [(w, h), ...]
        self.pixmaps = []     # [QPixmap, ...] 原图
        self.trims = []       # [(w, h), ...] Trim 后尺寸
        self.names = []       # [str, ...]
        self.idx = 0          # 当前帧号
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

        # --- 播放卡片 ---
        play_card = SectionCard('预览', '#ff8800')
        play_row = QHBoxLayout()
        self.btn_play = QPushButton('播放')
        self.btn_play.setObjectName('primaryButton')
        self.btn_play.clicked.connect(self._toggle_play)
        play_row.addWidget(self.btn_play)
        self.label_frame_count = QLabel('帧: 0/--')
        self.label_frame_count.setObjectName('secondaryLabel')
        play_row.addWidget(self.label_frame_count)
        play_row.addStretch(1)
        play_card.addLayout(play_row)
        # 原图大小播放: 滚动区域 1:1 显示, 透明区域显示棋盘格
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.label_preview = QLabel('载入文件夹后在此预览')
        self.label_preview.setObjectName('previewLabel')
        self.label_preview.setAlignment(Qt.AlignCenter)
        self.label_preview.setAutoFillBackground(True)
        pal = self.label_preview.palette()
        pal.setBrush(QPalette.Window, QBrush(make_checker()))
        self.label_preview.setPalette(pal)
        self.scroll.setWidget(self.label_preview)
        play_card.addWidget(self.scroll, 1)
        root.addWidget(play_card, 1)

        # --- 图集卡片 (Trim 模式 + 缩放滑块) ---
        atlas_card = SectionCard('图集计算 (Trim 模式)', '#00cc66')
        row = QHBoxLayout()
        row.addWidget(QLabel('缩放:'))
        self.slider_scale = QSlider(Qt.Horizontal)
        self.slider_scale.setRange(10, 100)
        self.slider_scale.setValue(100)
        self.slider_scale.setTickPosition(QSlider.TicksBelow)
        self.slider_scale.setTickInterval(10)
        self.slider_scale.valueChanged.connect(self._on_scale_changed)
        row.addWidget(self.slider_scale, 1)
        self.label_scale_pct = QLabel('100%')
        self.label_scale_pct.setMinimumWidth(48)
        row.addWidget(self.label_scale_pct)
        self.label_scaled_size = QLabel('缩放后: --')
        self.label_scaled_size.setObjectName('secondaryLabel')
        row.addWidget(self.label_scaled_size)
        atlas_card.addLayout(row)
        self.label_atlas = QLabel('载入文件夹后计算')
        self.label_atlas.setWordWrap(True)
        atlas_card.addWidget(self.label_atlas)
        row = QHBoxLayout()
        self.btn_export = QPushButton('缩小导出')
        self.btn_export.setObjectName('primaryButton')
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_shrink)
        row.addWidget(self.btn_export)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%v/%m  帧')
        self.progress_bar.hide()
        row.addWidget(self.progress_bar, 1)
        atlas_card.addLayout(row)
        root.addWidget(atlas_card)

        self.setCentralWidget(central)

    def _on_scale_changed(self):
        """滑块变化: 刷新图集计算 + 预览按新缩放显示"""
        self._refresh_atlas()
        if self.pixmaps:
            self._show_frame(self.idx)

    # ---------------- 缩小导出 ----------------
    def _export_shrink(self):
        s = self.slider_scale.value()
        if not self.pixmaps or s >= 100:
            return
        out_dir = os.path.join(os.path.dirname(self.folder),
                               os.path.basename(self.folder) + f'_{s}%')
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        else:
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
        self.btn_export.setEnabled(False)
        self.progress_bar.setRange(0, len(self.sizes))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.worker_export = ExportWorker(self.folder, out_dir, s / 100.0)
        self.worker_export.progress.connect(
            lambda cur, total: (self.progress_bar.setRange(0, total),
                                self.progress_bar.setValue(cur)))
        self.worker_export.done.connect(self._export_done)
        self.worker_export.failed.connect(self._export_failed)
        self.worker_export.start()

    def _export_failed(self, idx, msg):
        self.btn_export.setEnabled(True)
        QMessageBox.critical(self, '导出失败', f'帧 {idx}: {msg}')

    def _export_done(self, out_dir):
        self.btn_export.setEnabled(True)
        QMessageBox.information(self, '完成', f'缩小导出完成!\n目录: {out_dir}')

    # ---------------- 样式表 (暗色主题, 复刻 Gif2PngUI.py) ----------------
    def _build_stylesheet(self):
        return """
        QMainWindow, QWidget {
            background: #1e1e2e; color: #e0e0e0;
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 12px;
        }
        #sectionCard {
            background: #262638; border: 1px solid #323248; border-radius: 8px;
        }
        #previewLabel {
            border: 1px solid #323248; border-radius: 6px;
            color: #606070; background: transparent;
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
        QScrollArea {
            background: #161626; border: 1px solid #323248; border-radius: 6px;
        }
        QSlider::groove:horizontal {
            background: #2a2a3a; border: 1px solid #323248; height: 6px;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #ff6600; width: 16px; margin: -7px 0;
            border-radius: 4px; border: 1px solid #ff8833;
        }
        QSlider::handle:horizontal:hover { background: #ff8833; }
        QSlider::sub-page:horizontal {
            background: #ff6600; border-radius: 3px;
        }
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
        self.btn_play.setEnabled(False)
        self.timer.stop()
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

    def _on_loaded(self, sizes, qimages, trims, names):
        self.progress.setValue(len(sizes))
        self.progress.close()
        self.sizes, self.pixmaps, self.trims, self.names = \
            sizes, [QPixmap.fromImage(q) for q in qimages], trims, names
        # 信息行
        uniq = sorted(set(sizes))
        size_txt = f'{uniq[0][0]}x{uniq[0][1]}' if len(uniq) == 1 else \
            f'{uniq[0][0]}x{uniq[0][1]} ~ {uniq[-1][0]}x{uniq[-1][1]}'
        trim_max = (max(t[0] for t in trims), max(t[1] for t in trims))
        self.label_info.setText(
            f'帧数: {len(sizes)}    尺寸: {size_txt}    Trim 后最大: {trim_max[0]}x{trim_max[1]}'
            f'    播放间隔: {PLAY_INTERVAL}ms')
        # 播放到第一帧
        self.idx = 0
        self._show_frame(0)
        self._refresh_atlas()
        self.btn_play.setEnabled(True)

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
        pm = self.pixmaps[i]
        s = self.slider_scale.value()
        if s < 100:  # 按滑块缩放显示 (100% = 原图 1:1)
            pm = pm.scaled(max(1, pm.width() * s // 100), max(1, pm.height() * s // 100),
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # label 尺寸固定为原图尺寸, 缩放图居中 -> 滚动区域不跳动 (防滑块拖动抖动)
        self.label_preview.setFixedSize(self.pixmaps[i].size())
        self.label_preview.setPixmap(pm)
        self.label_frame_count.setText(f'帧: {i + 1}/{len(self.pixmaps)}')

    # ---------------- 图集计算 (Trim 模式) ----------------
    def _refresh_atlas(self):
        """完整刷新图集显示: Trim 前后图集数量 + 当前滑块缩放下的尺寸与数量"""
        s = self.slider_scale.value()
        self.label_scale_pct.setText(f'{s}%')
        self.btn_export.setText(f'缩小导出 {s}%' if s < 100 else '缩小导出')
        exporting = getattr(self, 'worker_export', None) and self.worker_export.isRunning()
        self.btn_export.setEnabled(bool(self.pixmaps) and s < 100 and not exporting)
        if not self.pixmaps:
            self.label_scaled_size.setText('缩放后: --')
            return
        # 缩放后尺寸
        if s >= 100:
            w, h = self.trims[0]  # 100% 时显示 Trim 原尺寸, 不取偶
            self.label_scaled_size.setText(f'缩放后: {w}x{h}')
        else:
            w, h = even_size(self.trims[0][0], self.trims[0][1], s / 100.0)
            self.label_scaled_size.setText(f'缩放后: {w}x{h}（偶数）')
        # 图集数量: Trim 前 / Trim 后 / 当前缩放
        lines = []
        n_orig = atlas_count(self.sizes)
        lines.append(f'Trim 前: 需要 {n_orig} 张 {ATLAS}x{ATLAS} 图集（帧间距 {PADDING}）'
                     if n_orig else f'⚠ Trim 前单帧超过 {ATLAS}x{ATLAS}（含间距）, 无法放入图集')
        n_trim = atlas_count(self.trims)
        lines.append(f'Trim 后: 需要 {n_trim} 张 {ATLAS}x{ATLAS} 图集（帧间距 {PADDING}）'
                     if n_trim else f'⚠ Trim 后仍有单帧超过 {ATLAS}x{ATLAS}, 需要缩放')
        if s < 100:
            n_s = atlas_count(self.trims, scale=s / 100.0)
            lines.append(f'缩放至 {s}%: 需要 {n_s} 张 {ATLAS}x{ATLAS} 图集'
                         if n_s else f'⚠ 缩放至 {s}% 仍有单帧超过 {ATLAS}x{ATLAS}')
        self.label_atlas.setText('\n'.join(lines))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)
        if getattr(self, 'worker_export', None) and self.worker_export.isRunning():
            self.worker_export.wait(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
