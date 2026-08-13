# PySide6 序列帧优化工具
# 功能: 播放序列帧(大图预览+胶片条) / 计算 TexturePacker 图集数量(2048x2048, 帧间距4) /
#       超过10张上限时给出缩小(取偶保品质)或抽帧建议
import os
import re
import sys

from PIL import Image
from PySide6.QtCore import Qt, QSize, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QProgressDialog,
                               QPushButton, QVBoxLayout, QWidget)

ATLAS = 2048       # 图集边长
PADDING = 4        # TexturePacker 帧间距 (padding 语义: 每帧占 w+4)
MAX_ATLASES = 10   # 图集数量上限
PREVIEW_W = 640    # 预览缓存图最大宽
FILM_H = 80        # 胶片条缩略图高
PLAY_INTERVAL = 80 # 播放帧间隔 ms (12.5fps)

SUPPORTED = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')


def pil_to_pixmap(im):
    """PIL Image -> QPixmap"""
    im = im.convert('RGB')
    data = im.tobytes('raw', 'RGB')
    qimg = QImage(data, im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def natural_key(name):
    """自然排序 key: frame_2.png < frame_10.png"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


def even_size(w, h, scale):
    """按比例缩放并取偶 (最小 2px), 返回 (w', h')"""
    return (max(2, round(w * scale / 2) * 2), max(2, round(h * scale / 2) * 2))


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


def atlas_count(rects, scale=1.0, keep_every=1):
    """MaxRects 装箱所需图集数。rects: [(w, h), ...] 帧原始尺寸。
    scale: 全局缩放比例; keep_every: 抽帧间隔(每 N 帧取 1)。
    单帧(缩放后)放不进图集返回 None"""
    items = sorted(rects[::keep_every], key=lambda r: (r[0] + PADDING) * (r[1] + PADDING), reverse=True)
    bins = 0
    free = [(0, 0, ATLAS, ATLAS)]
    for w, h in items:
        if scale < 1.0:
            iw, ih = even_size(w, h, scale)  # 缩放后取偶 (用户要求)
        else:
            iw, ih = w, h  # 原始帧用真实尺寸
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


def calc_shrink(rects, limit=MAX_ATLASES):
    """求最大缩放百分比 (1% 精度, 取偶, 尽量少缩) 使图集数 <= limit, 返回 (percent, 图集数, 示例缩放后尺寸)"""
    base = atlas_count(rects)
    if base is not None and base <= limit:
        return None
    # 单帧超图集(未缩放为 None)或超上限: 二分求最大可行缩放 (fits 随 scale 单调)
    lo, hi = 1, 99
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        cnt = atlas_count(rects, scale=mid / 100.0)
        if cnt is not None and cnt <= limit:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return None
    cnt = atlas_count(rects, scale=best / 100.0)
    w, h = even_size(rects[0][0], rects[0][1], best / 100.0)
    return best, cnt, (w, h)


def calc_skip(rects, limit=MAX_ATLASES):
    """求最小抽帧间隔 N (每 N 帧取 1) 使图集数 <= limit, 返回 (N, 保留帧数, 抽掉帧数, 图集数)"""
    n = len(rects)
    for keep_every in range(2, 21):
        cnt = atlas_count(rects, keep_every=keep_every)
        if cnt is not None and cnt <= limit:
            return keep_every, (n + keep_every - 1) // keep_every, n - (n + keep_every - 1) // keep_every, cnt
    return None


class LoadWorker(QThread):
    """后台加载线程: 解码全部帧为预览缓存图 + 记录尺寸/文件名"""
    progress = Signal(int, int)  # 当前帧, 总帧数
    loaded = Signal(list, list, list)  # sizes, previews(QPixmap), names
    failed = Signal(str)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder

    def run(self):
        try:
            files = sorted((f for f in os.listdir(self.folder)
                            if os.path.splitext(f)[1].lower() in SUPPORTED), key=natural_key)
            total = len(files)
            sizes, previews, names = [], [], []
            for i, f in enumerate(files):
                path = os.path.join(self.folder, f)
                with Image.open(path) as im:
                    sizes.append(im.size)
                    prev = im.copy()
                    prev.thumbnail((PREVIEW_W, PREVIEW_W), Image.Resampling.LANCZOS)
                    previews.append(pil_to_pixmap(prev))
                names.append(f)
                if i % 5 == 0:
                    self.progress.emit(i, total)
            self.loaded.emit(sizes, previews, names)
        except Exception as e:
            self.failed.emit(str(e))


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
        self.setMinimumSize(960, 640)

        self.folder = None
        self.sizes = []       # [(w, h), ...]
        self.previews = []    # [QPixmap, ...] 预览缓存
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
        self.label_preview = QLabel('载入文件夹后在此预览')
        self.label_preview.setObjectName('previewLabel')
        self.label_preview.setMinimumSize(320, 280)
        self.label_preview.setAlignment(Qt.AlignCenter)
        play_card.addWidget(self.label_preview, 1)
        # 横向胶片条
        self.film = QListWidget()
        self.film.setViewMode(QListView.IconMode)
        self.film.setFlow(QListView.LeftToRight)
        self.film.setMovement(QListView.Static)
        self.film.setIconSize(QSize(FILM_H, FILM_H))
        self.film.setGridSize(QSize(FILM_H + 10, FILM_H + 10))
        self.film.setSpacing(2)
        self.film.setFixedHeight(FILM_H + 36)
        self.film.setSelectionMode(QAbstractItemView.SingleSelection)
        self.film.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.film.currentItemChanged.connect(self._on_film_select)
        play_card.addWidget(self.film)
        root.addWidget(play_card, 1)

        # --- 图集卡片 ---
        atlas_card = SectionCard('图集计算', '#00cc66')
        self.label_atlas = QLabel('载入文件夹后计算')
        self.label_atlas.setWordWrap(True)
        atlas_card.addWidget(self.label_atlas)
        root.addWidget(atlas_card)

        self.setCentralWidget(central)

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
            background: #161626; border: 1px solid #323248; border-radius: 6px;
            color: #606070;
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
        QListWidget {
            background: #161626; border: 1px solid #323248; border-radius: 6px;
            padding: 4px;
        }
        QListWidget::item { border-radius: 4px; padding: 1px; }
        QListWidget::item:hover { background: #2a2a3a; }
        QListWidget::item:selected { background: #ff6600; border: 1px solid #ff8833; }
        QLabel { color: #e0e0e0; }
        #secondaryLabel { color: #9090a8; font-size: 11px; }
        #atlasWarn { color: #ff8844; font-size: 12px; }
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

    def _on_loaded(self, sizes, previews, names):
        self.progress.setValue(len(sizes))
        self.progress.close()
        self.sizes, self.previews, self.names = sizes, previews, names
        # 信息行
        uniq = sorted(set(sizes))
        size_txt = f'{uniq[0][0]}x{uniq[0][1]}' if len(uniq) == 1 else \
            f'{uniq[0][0]}x{uniq[0][1]} ~ {uniq[-1][0]}x{uniq[-1][1]}'
        self.label_info.setText(f'帧数: {len(sizes)}    尺寸: {size_txt}    播放间隔: {PLAY_INTERVAL}ms')
        # 胶片条
        self.film.clear()
        for i, pm in enumerate(previews):
            item = QListWidgetItem(QIcon(pm), '')
            item.setData(Qt.UserRole, i)
            item.setToolTip(f'{names[i]}  ({sizes[i][0]}x{sizes[i][1]})')
            self.film.addItem(item)
        # 播放到第一帧
        self.idx = 0
        self._show_frame(0)
        self._update_atlas()
        self.btn_play.setEnabled(True)
        self.label_frame_count.setText(f'帧: 1/{len(sizes)}')

    # ---------------- 播放 ----------------
    def _toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText('播放')
        else:
            self.timer.start(PLAY_INTERVAL)
            self.btn_play.setText('暂停')

    def _tick(self):
        self.idx = (self.idx + 1) % len(self.previews)
        self._show_frame(self.idx)

    def _on_film_select(self, current, previous):
        if current is not None:  # 点击胶片条: 暂停并跳帧
            self.timer.stop()
            self.btn_play.setText('播放')
            self._show_frame(current.data(Qt.UserRole))

    def _show_frame(self, i):
        self.idx = i
        pm = self.previews[i]
        self.label_preview.setPixmap(pm.scaled(
            self.label_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.label_frame_count.setText(f'帧: {i + 1}/{len(self.previews)}')
        self.film.setCurrentRow(i)

    # ---------------- 图集计算 ----------------
    def _update_atlas(self):
        rects = self.sizes
        n = atlas_count(rects)
        if n is not None and n <= MAX_ATLASES:
            self.label_atlas.setText(
                f'需要 {n} 张 {ATLAS}x{ATLAS} 图集（帧间距 {PADDING}, MaxRects 装箱模拟 TexturePacker）')
            return
        # 超上限或单帧超图集: 给方案
        lines = [f'需要 {n} 张 {ATLAS}x{ATLAS}, 超过上限 {MAX_ATLASES} 张!' if n else
                 f'⚠ 存在单帧(含间距{PADDING})超过 {ATLAS}x{ATLAS}, 无法放入图集']
        shrink = calc_shrink(rects)
        if shrink:
            pct, cnt, (w, h) = shrink
            tip = '' if pct >= 50 else '  ⚠ 缩放 <50% 品质损失明显, 建议改用抽帧'
            lines.append(f'方案1 缩小: 缩放至 {pct}% → {cnt} 张（示例帧 → {w}x{h}, 尺寸取偶, 导出时用 LANCZOS 保品质）{tip}')
        skip = calc_skip(rects)
        if skip:
            k, kept, dropped, cnt = skip
            lines.append(f'方案2 抽帧: 每 {k} 帧取 1 帧 → 保留 {kept} 帧（抽掉 {dropped} 帧）, {cnt} 张')
        if not shrink and not skip:
            lines.append('⚠ 无法通过缩放或抽帧降到 10 张以内')
        self.label_atlas.setText('\n'.join(lines))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.previews:
            self._show_frame(self.idx)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
