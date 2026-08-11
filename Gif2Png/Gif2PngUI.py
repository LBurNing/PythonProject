# PySide6 可视化 GIF 序列帧导出工具
# 功能: 播放原gif / 播放导出序列帧 / 显示原图尺寸 / 自定义导出宽(高自动适配取偶数) / 导出序列帧
import math
import os
import sys

from PIL import Image, ImageSequence
from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QMovie, QPainter, QPixmap, QImage
from PySide6.QtWidgets import (QStyle, QStyleOptionSlider)
from PySide6.QtWidgets import (QApplication, QDoubleSpinBox, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QProgressDialog, QPushButton, QSlider,
                               QSpinBox, QStackedLayout, QVBoxLayout, QWidget)

START_INDEX = 50000   # 帧号起始
EXPORT_QUALITY = 90   # JPEG 质量
PREVIEW_W = 420       # 预览区宽度
PREVIEW_H = 320       # 预览区高度


def pil_to_pixmap(im):
    """PIL Image -> QPixmap"""
    im = im.convert('RGB')
    data = im.tobytes('raw', 'RGB')
    qimg = QImage(data, im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def even_height(width, frame_w, frame_h):
    """宽 -> 按比例的高, 且取偶数"""
    return round(width * frame_h / frame_w / 2) * 2


def export_plan(durs, target_fps, start=0, end=None):
    """导出计划: 返回 (是否抽帧, 导出帧数)
    只在 [start, end] 帧范围内选择; 目标帧率不低于原平均帧率时 不抽帧(全量),
    只有降低帧率才按时间轴抽帧。加 2.5% 相对容差覆盖 1 位小数的舍入误差"""
    if end is None:
        end = len(durs) - 1
    seg = durs[start:end + 1]
    avg_ms = sum(seg) / len(seg)
    target_ms = 1000.0 / target_fps
    if target_ms <= avg_ms * 1.025:  # 目标帧间隔不大于平均帧间隔(含舍入容差) = 帧率不低于原帧率
        return False, len(seg)
    acc = 0.0
    last_out = -target_ms  # 保证首帧导出
    n = 0
    for d in seg:
        acc += d
        if acc - last_out >= target_ms - 1 or n == 0:
            last_out = acc
            n += 1
    return True, n


def build_frame_mask(durs, target_fps, start=0, end=None):
    """帧选择掩码: 每帧是否导出/预览 (与导出逻辑一致, 预览与导出帧数同步)
    范围 [start, end] 外的帧标记为 False"""
    if end is None:
        end = len(durs) - 1
    mask = [False] * len(durs)
    drop, _ = export_plan(durs, target_fps, start, end)
    seg = durs[start:end + 1]
    if not drop:
        for i in range(start, end + 1):
            mask[i] = True
        return mask
    target_ms = 1000.0 / target_fps
    acc = 0.0
    last_out = -target_ms
    n = 0
    for j, d in enumerate(seg):
        acc += d
        if acc - last_out >= target_ms - 1 or n == 0:
            last_out = acc
            n += 1
            mask[start + j] = True
    return mask


class RangeSlider(QWidget):
    """双滑块范围选择条: 起始/结束均可拖动
    两个 QSlider 手动重叠, 鼠标事件按最近 handle 转发 (QStackedLayout 只能交互当前层)"""
    rangeChanged = Signal(int, int)  # (start, end)
    dragChanged = Signal(int)        # 拖动中的当前帧号
    dragFinished = Signal()          # 松手

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(24)
        self._s1 = QSlider(Qt.Horizontal)
        self._s2 = QSlider(Qt.Horizontal)
        for s in (self._s1, self._s2):
            s.setObjectName('rangeStart' if s is self._s1 else 'rangeEnd')
            s.setRange(0, 1)
            s.setParent(self)
            s.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 事件穿透到容器统一转发
            s.show()
        self._s1.valueChanged.connect(self._on_start)
        self._s2.valueChanged.connect(self._on_end)
        self._start = 0
        self._end = 1
        self._active = None  # 当前拖动的 slider

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._s1.setGeometry(0, 0, self.width(), self.height())
        self._s2.setGeometry(0, 0, self.width(), self.height())

    def paintEvent(self, event):
        """绘制轨道线 (groove 设为透明, 避免上层滑块盖住开始 handle)"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        y = self.height() // 2
        groove = QRectF(7, y - 3, self.width() - 14, 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#2a2a3a'))
        painter.drawRoundedRect(groove, 3, 3)
        painter.end()

    # ---- 鼠标事件转发 ----
    def _handle_center_x(self, s):
        opt = QStyleOptionSlider()
        opt.initFrom(s)
        opt.minimum = s.minimum()
        opt.maximum = s.maximum()
        opt.sliderPosition = s.value()
        opt.sliderValue = s.value()
        opt.orientation = Qt.Horizontal
        rect = s.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, s)
        return rect.center().x()

    def _pick_slider(self, pt):
        d1 = abs(self._handle_center_x(self._s1) - pt.x())
        d2 = abs(self._handle_center_x(self._s2) - pt.x())
        return self._s1 if d1 <= d2 else self._s2

    def _forward(self, e, s):
        pos = s.mapFrom(self, e.position().toPoint())
        s.event(QMouseEvent(e.type(), pos, e.button(), e.buttons(), e.modifiers()))

    def mousePressEvent(self, e):
        self._active = self._pick_slider(e.position().toPoint())
        self._forward(e, self._active)
        e.accept()

    def mouseMoveEvent(self, e):
        if self._active:
            self._forward(e, self._active)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._active:
            self._forward(e, self._active)
            self._active = None
            self.dragFinished.emit()
            e.accept()

    # ---- 范围设置 ----
    def setRange(self, lo, hi):
        """设置可拖动范围并重置到全区间"""
        self._s1.blockSignals(True)
        self._s2.blockSignals(True)
        self._s1.setRange(lo, hi)
        self._s2.setRange(lo, hi)
        self._s1.setValue(lo)
        self._s2.setValue(hi)
        self._s1.blockSignals(False)
        self._s2.blockSignals(False)
        self._start, self._end = lo, hi
        self.rangeChanged.emit(lo, hi)

    def setRangeValues(self, start, end):
        self._s1.blockSignals(True)
        self._s2.blockSignals(True)
        self._s1.setValue(start)
        self._s2.setValue(end)
        self._s1.blockSignals(False)
        self._s2.blockSignals(False)
        self._start, self._end = start, end
        self.rangeChanged.emit(start, end)  # 手动通知 UI 刷新

    def values(self):
        return self._start, self._end

    def _on_start(self, v):
        if v >= self._end:
            v = self._end - 1
            self._s1.blockSignals(True)
            self._s1.setValue(v)
            self._s1.blockSignals(False)
        self._start = v
        self.rangeChanged.emit(v, self._end)
        self.dragChanged.emit(v)

    def _on_end(self, v):
        if v <= self._start:
            v = self._start + 1
            self._s2.blockSignals(True)
            self._s2.setValue(v)
            self._s2.blockSignals(False)
        self._end = v
        self.rangeChanged.emit(self._start, v)
        self.dragChanged.emit(v)


class SectionCard(QFrame):
    """卡片式分组容器: 左侧彩色色条标题 + 内容区 (参考 obstacle_editor.py)"""
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
    """后台导出线程"""
    progress = Signal(int, int)     # 当前帧, 总帧数
    failed = Signal(int, str)       # 帧号(-1=整体失败), 错误信息
    done = Signal(str)              # 输出目录

    def __init__(self, gif_path, out_dir, width, target_fps, durs, start=0, end=None, parent=None):
        super().__init__(parent)
        self.gif_path = gif_path
        self.out_dir = out_dir
        self.width = width
        self.target_fps = target_fps
        self.durs = durs
        self.start_frame = start
        self.end_frame = end if end is not None else len(durs) - 1

    def run(self):
        try:
            im = Image.open(self.gif_path)
            total = im.n_frames
            drop_frames, _ = export_plan(self.durs, self.target_fps, self.start_frame, self.end_frame)
            target_ms = 1000.0 / self.target_fps
            # 迭代器推进到范围起点
            it = ImageSequence.Iterator(im)
            for _ in range(self.start_frame):
                next(it)
            acc = 0.0
            last_out = -target_ms
            exported = 0
            for i in range(self.start_frame, self.end_frame + 1):
                try:
                    frame = next(it)
                    dur = frame.info.get('duration', 0) or 0
                    acc += dur if dur > 0 else 80  # 帧延迟为0(无效)时用默认80ms
                    if not drop_frames or acc - last_out >= target_ms - 1 or exported == 0:
                        h = even_height(self.width, frame.width, frame.height)
                        out_path = os.path.join(self.out_dir, f'{START_INDEX + exported}.png')
                        frame.convert('RGB').resize((self.width, h)).save(out_path, 'JPEG', quality=EXPORT_QUALITY)
                        last_out = acc
                        exported += 1
                    self.progress.emit(i + 1, total)
                except Exception as e:
                    self.failed.emit(i, str(e))
            self.done.emit(self.out_dir)
        except Exception as e:
            self.failed.emit(-1, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('GIF 序列帧导出工具')
        self.setMinimumSize(960, 560)

        self.gif_path = None
        self.im = None              # PIL Image, 序列帧预览用
        self.frame_iter = None      # 序列帧迭代器
        self.movie = None           # 原 gif 播放器
        self.worker = None          # 导出线程
        self._drag_tracking = False  # 范围条拖动中
        self._pre_drag_paused = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._seq_tick)

        self._build_ui()
        self.setStyleSheet(self._build_stylesheet())

    # ---------------- 界面 ----------------
    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # --- 文件卡片 ---
        file_card = SectionCard('GIF 文件', '#4488ff')
        row = QHBoxLayout()
        row.addWidget(QLabel('GIF 文件:'))
        self.edit_gif = QLineEdit()
        self.edit_gif.setReadOnly(True)
        row.addWidget(self.edit_gif, 1)
        btn_browse = QPushButton('浏览...')
        btn_browse.clicked.connect(self._browse_gif)
        row.addWidget(btn_browse)
        file_card.addLayout(row)
        self.label_info = QLabel('未载入 GIF')
        self.label_info.setObjectName('secondaryLabel')
        file_card.addWidget(self.label_info)
        root.addWidget(file_card)

        # --- 预览卡片 ---
        preview_card = SectionCard('预览', '#ff8800')
        replay_row = QHBoxLayout()
        replay_row.addStretch(1)
        btn_replay = QPushButton('全部重新播放')
        btn_replay.clicked.connect(self._replay_all)
        replay_row.addWidget(btn_replay)
        preview_card.addLayout(replay_row)
        preview_row = QHBoxLayout()
        for tag in ('gif', 'seq'):
            box = QVBoxLayout()
            title = '原 GIF' if tag == 'gif' else '导出序列帧'
            lbl = QLabel(title)
            lbl.setObjectName('secondaryLabel')
            box.addWidget(lbl)
            label = QLabel()
            label.setObjectName('previewLabel')
            label.setMinimumSize(320, 240)  # 可随窗口/全屏自适应拉伸
            label.setAlignment(Qt.AlignCenter)
            label.setText('载入 GIF 后在此预览')
            if tag == 'gif':
                self.label_gif = label
            else:
                self.label_seq = label
            box.addWidget(label, 1)
            play_btn = QPushButton('播放/暂停')
            if tag == 'gif':
                play_btn.clicked.connect(self._toggle_gif_play)
                self.btn_gif_play = play_btn
            else:
                play_btn.clicked.connect(self._toggle_seq_play)
                self.btn_seq_play = play_btn
            btn_row = QHBoxLayout()
            btn_row.addWidget(play_btn)
            if tag == 'seq':
                self.label_frame_count = QLabel('帧: 0/--')
                self.label_frame_count.setObjectName('secondaryLabel')
                btn_row.addWidget(self.label_frame_count)
            btn_row.addStretch(1)
            box.addLayout(btn_row)
            preview_row.addLayout(box, 1)
        preview_card.addLayout(preview_row)
        root.addWidget(preview_card, 1)

        # --- 导出卡片 ---
        export_card = SectionCard('导出设置', '#00cc66')
        row = QHBoxLayout()
        row.addWidget(QLabel('导出宽度:'))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(16, 8192)
        self.spin_width.setValue(1020)
        self.spin_width.setSuffix(' px')
        self.spin_width.valueChanged.connect(self._on_param_changed)
        row.addWidget(self.spin_width)
        self.label_height = QLabel('自动高度: --')
        self.label_height.setObjectName('secondaryLabel')
        row.addWidget(self.label_height)
        self.label_scale = QLabel('缩放率: --')
        self.label_scale.setObjectName('secondaryLabel')
        row.addWidget(self.label_scale)
        row.addStretch(1)
        btn_outdir = QPushButton('选择输出目录...')
        btn_outdir.clicked.connect(self._browse_outdir)
        row.addWidget(btn_outdir)
        export_card.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel('目标帧率:'))
        self.spin_fps = QDoubleSpinBox()
        self.spin_fps.setRange(0.5, 120.0)
        self.spin_fps.setDecimals(1)
        self.spin_fps.setSuffix(' FPS')
        self.spin_fps.valueChanged.connect(self._update_fps_hint)
        row.addWidget(self.spin_fps)
        self.label_fps_hint = QLabel('预估导出: --')
        self.label_fps_hint.setObjectName('secondaryLabel')
        row.addWidget(self.label_fps_hint)
        row.addStretch(1)
        export_card.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel('导出范围:'))
        self.range_slider = RangeSlider()
        self.range_slider.rangeChanged.connect(self._on_range_changed)
        self.range_slider.dragChanged.connect(self._on_range_drag)
        self.range_slider.dragFinished.connect(self._on_range_drag_finished)
        row.addWidget(self.range_slider, 1)
        self.label_range = QLabel('--')
        self.label_range.setObjectName('secondaryLabel')
        row.addWidget(self.label_range)
        export_card.addLayout(row)

        self.label_atlas = QLabel('图集: --')
        self.label_atlas.setObjectName('secondaryLabel')
        export_card.addWidget(self.label_atlas)

        row = QHBoxLayout()
        row.addWidget(QLabel('输出目录:'))
        self.edit_outdir = QLineEdit()
        self.edit_outdir.setPlaceholderText('默认: gif 所在目录下的同名文件夹')
        row.addWidget(self.edit_outdir, 1)
        export_card.addLayout(row)

        row = QHBoxLayout()
        self.btn_export = QPushButton('导出序列帧')
        self.btn_export.setObjectName('primaryButton')
        self.btn_export.clicked.connect(self._export)
        row.addWidget(self.btn_export)
        self.progress = QProgressBar()
        self.progress.setFormat('%v/%m  帧')
        row.addWidget(self.progress, 1)
        export_card.addLayout(row)
        root.addWidget(export_card)

        self.setCentralWidget(central)

    # ---------------- 样式表 (暗色主题, 参考 obstacle_editor.py) ----------------
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
        QSpinBox, QLineEdit {
            background: #2e2e44; border: 1px solid #3e3e58; border-radius: 4px;
            padding: 4px 8px; color: #e0e0e0; min-height: 22px;
        }
        QSpinBox:hover, QLineEdit:hover { border-color: #4e4e6e; }
        QSpinBox::up-button, QSpinBox::down-button {
            background: #3a3a52; border: none; width: 16px;
        }
        QSpinBox::up-arrow {
            border-left: 4px solid transparent; border-right: 4px solid transparent;
            border-bottom: 5px solid #9090a8;
        }
        QSpinBox::down-arrow {
            border-left: 4px solid transparent; border-right: 4px solid transparent;
            border-top: 5px solid #9090a8;
        }
        QProgressBar {
            background: #2a2a3a; border: 1px solid #323248; border-radius: 4px;
            text-align: center; color: #e0e0e0; min-height: 20px;
        }
        QProgressBar::chunk { background: #ff6600; border-radius: 3px; }

        /* === 范围选择双滑块 (起始橙 / 结束蓝) === */
        QSlider#rangeStart, QSlider#rangeEnd { background: transparent; }
        QSlider#rangeStart::groove, QSlider#rangeEnd::groove {
            background: transparent; height: 6px; border-radius: 3px;
        }
        QSlider#rangeStart::handle {
            background: #ff6600; width: 14px; height: 20px; margin: -7px 0;
            border-radius: 4px; border: 1px solid #ff8833;
        }
        QSlider#rangeEnd::handle {
            background: #4488ff; width: 14px; height: 20px; margin: -7px 0;
            border-radius: 4px; border: 1px solid #66aaff;
        }
        QSlider#rangeStart::handle:hover { background: #ff8833; }
        QSlider#rangeEnd::handle:hover { background: #66aaff; }
        QLabel { color: #e0e0e0; }
        #secondaryLabel { color: #9090a8; font-size: 11px; }
        QMessageBox { background: #262638; color: #e0e0e0; }
        """

    # ---------------- 载入 ----------------
    def _browse_gif(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 GIF', '', 'GIF 文件 (*.gif)')
        if path:
            self._load_gif(path)

    def _load_gif(self, path):
        try:
            self.im = Image.open(path)
        except Exception as e:
            QMessageBox.critical(self, '错误', f'无法打开 GIF: {e}')
            return
        self.gif_path = path
        self.edit_gif.setText(path)
        w, h = self.im.size
        # 统计各帧延迟, 计算平均帧率 (大 gif 遍历较慢, 显示进度条)
        n_frames = self.im.n_frames
        progress = QProgressDialog(f'正在分析 GIF ({0}/{n_frames})...', None, 0, n_frames, self)
        progress.setWindowTitle('加载进度')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        durs = []
        # 顺带预解码拖动预览缩略图 (QMovie 无法快速跳帧, 拖动时直接从缓存取图)
        target = self.label_gif.size()
        self._scrub_frames = []
        for i in range(n_frames):
            self.im.seek(i)
            dur = self.im.info.get('duration', 0) or 0
            durs.append(dur if dur > 0 else 80)  # 帧延迟为0(无效)时用默认80ms
            thumb = self.im.convert('RGB')
            thumb.thumbnail((target.width(), target.height()), Image.Resampling.LANCZOS)
            self._scrub_frames.append(pil_to_pixmap(thumb))
            if i % 5 == 0:
                progress.setValue(i)
                progress.setLabelText(f'正在分析 GIF ({i}/{n_frames})...')
                QApplication.processEvents()
        progress.setValue(n_frames)
        progress.close()
        self.im.seek(0)
        self._durs = durs
        self._total_ms = sum(durs)
        # 帧率用平均帧延迟计算
        avg_dur = self._total_ms / len(durs)
        fps = 1000.0 / avg_dur if avg_dur > 0 else 0
        self.label_info.setText(
            f'原 GIF 尺寸: {w} x {h}    帧数: {self.im.n_frames}    帧率: {fps:.1f} FPS')
        self.spin_fps.setValue(fps)  # 全精度存值(显示2位小数), 避免取整导致误判抽帧
        self.range_slider.setRange(0, self.im.n_frames - 1)
        self._update_fps_hint()
        # 默认输出目录: gif 同名文件夹
        base = os.path.splitext(path)[0]
        if not os.path.exists(base) or os.path.isdir(base):
            self.edit_outdir.setText(base)
        # 原 gif 播放器 (逐帧取图, 等比缩放显示, 避免拉伸)
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
        self.movie = QMovie(path)
        self.movie.frameChanged.connect(self._gif_frame_changed)
        self.movie.start()
        # 序列帧预览
        self._reset_seq_iter()
        self._update_height_hint()

    def _gif_frame_changed(self, frame):
        pm = self.movie.currentPixmap()
        if not pm.isNull():
            self.label_gif.setPixmap(pm.scaled(
                self.label_gif.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_param_changed(self):
        """导出参数(宽度等)变化时联动刷新提示"""
        self._update_height_hint()
        self._update_fps_hint()

    def _update_height_hint(self):
        if self.im:
            w = self.spin_width.value()
            h = even_height(w, self.im.width, self.im.height)
            self.label_height.setText(f'自动高度: {h}（偶数）')
            self.label_scale.setText(f'缩放率: {w / self.im.width * 100:.1f}%')
        else:
            self.label_height.setText('自动高度: --')
            self.label_scale.setText('缩放率: --')

    def _update_fps_hint(self):
        """按目标帧率+导出范围预估导出帧数 (复用导出计划, 与导出结果一致)"""
        if self.im and getattr(self, '_durs', None):
            start, end = self.range_slider.values()
            _, n = export_plan(self._durs, self.spin_fps.value(), start, end)
            self._frame_mask = build_frame_mask(self._durs, self.spin_fps.value(), start, end)
            self._preview_total = n
            self.label_fps_hint.setText(f'预估导出: {n} 帧')
            self._update_atlas_hint(n)
            if hasattr(self, 'label_frame_count'):
                self.label_frame_count.setText(f'帧: 0/{n}')
        else:
            self.label_fps_hint.setText('预估导出: --')
            self.label_atlas.setText('图集: --')

    def _on_range_changed(self, start, end):
        """范围条拖动时更新显示与预估"""
        self.label_range.setText(f'起始 {start} / 结束 {end}')
        self._update_fps_hint()

    def _on_range_drag(self, idx):
        """拖动范围条时, GIF 预览跟随显示对应帧 (用预解码缩略图, 实时无卡顿)"""
        frames = getattr(self, '_scrub_frames', None)
        if frames and idx < len(frames):
            if not self._drag_tracking:
                self._drag_tracking = True
                if self.movie:
                    self._pre_drag_paused = (self.movie.state() == QMovie.Paused)
                    self.movie.setPaused(True)
            self.label_gif.setPixmap(frames[idx])
        elif self.movie and self.movie.state() != QMovie.NotRunning:
            # 无缓存时回退 QMovie 跳帧 (慢, 兜底)
            if not self._drag_tracking:
                self._drag_tracking = True
                self._pre_drag_paused = (self.movie.state() == QMovie.Paused)
                self.movie.setPaused(True)
            self.movie.jumpToFrame(idx)

    def _on_range_drag_finished(self):
        """拖动结束, 恢复播放"""
        if self._drag_tracking:
            self._drag_tracking = False
            if not self._pre_drag_paused:
                self.movie.setPaused(False)

    def _update_atlas_hint(self, frame_count):
        """计算 2048x2048 图集数量 (所有帧同尺寸, 按格子摆放精确计算, 含帧间距)"""
        ATLAS = 2048
        PADDING = 4  # TexturePacker 帧间距
        w = self.spin_width.value()
        h = even_height(w, self.im.width, self.im.height)
        per_atlas = (ATLAS // (w + PADDING)) * (ATLAS // (h + PADDING))
        if per_atlas <= 0:  # 单帧大于图集
            self.label_atlas.setText(f'图集: 帧过大, 每帧需 1 张 2048x2048')
            return
        n_atlas = math.ceil(frame_count / per_atlas)
        self.label_atlas.setText(
            f'图集: 需要 {n_atlas} 张 2048x2048（每张 {per_atlas} 帧, 帧 {w}x{h} 间距{PADDING}）')

    # ---------------- 原 gif 播放 ----------------
    def _toggle_gif_play(self):
        if not self.movie:
            return
        if self.movie.state() == QMovie.Running:
            self.movie.setPaused(True)
        else:
            self.movie.setPaused(False)

    def _replay_all(self):
        """全部重新播放: GIF 和序列帧都从头开始"""
        if self.movie:
            self.movie.stop()
            self.movie.start()
        if self.im:
            self.timer.stop()
            self._reset_seq_iter()
            self._seq_tick()
            self.timer.start(80)

    # ---------------- 序列帧预览 ----------------
    def _reset_seq_iter(self):
        if self.im:
            self.im.seek(0)
            self.frame_iter = ImageSequence.Iterator(self.im)
            self._seq_idx = 0   # 原帧号计数
            self._export_idx = 0  # 导出帧计数(按抽帧掩码)
            if hasattr(self, 'label_frame_count'):
                total = getattr(self, '_preview_total', self.im.n_frames)
                self.label_frame_count.setText(f'帧: 0/{total}')

    def _toggle_seq_play(self):
        if not self.im:
            return
        if self.timer.isActive():
            self.timer.stop()
        else:
            self._reset_seq_iter()
            self._seq_tick()
            self.timer.start(80)
        self.btn_seq_play.setText('暂停' if self.timer.isActive() else '播放')

    def _seq_tick(self):
        # 按抽帧掩码跳过不导出的帧, 预览与导出的帧序列一致
        while True:
            try:
                frame = next(self.frame_iter)
            except StopIteration:
                self._reset_seq_iter()
                try:
                    frame = next(self.frame_iter)
                except StopIteration:
                    return
            self._seq_idx += 1
            if self._frame_mask[self._seq_idx - 1]:
                break
        self._export_idx += 1
        self.label_frame_count.setText(f'帧: {self._export_idx}/{self._preview_total}')
        w = self.spin_width.value()
        h = even_height(w, frame.width, frame.height)
        px = pil_to_pixmap(frame.convert('RGB').resize((w, h)))
        self._seq_raw_pixmap = px  # 存原始图, 窗口拉伸时重缩放
        self.label_seq.setPixmap(px.scaled(
            self.label_seq.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        dur = frame.info.get('duration', 0) or 0
        self.timer.setInterval(dur if dur > 0 else 80)  # 帧延迟为0(无效)时用默认80ms

    # ---------------- 导出 ----------------
    def _browse_outdir(self):
        start = self.edit_outdir.text() or os.path.dirname(self.gif_path or '')
        path = QFileDialog.getExistingDirectory(self, '选择输出目录', start)
        if path:
            self.edit_outdir.setText(path)

    def _export(self):
        if not self.im:
            QMessageBox.warning(self, '提示', '请先选择 GIF 文件')
            return
        out_dir = self.edit_outdir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, '提示', '请设置输出目录')
            return
        out_dir = os.path.join(out_dir, '待机')  # 多加一层状态目录
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        # 目录里已有帧文件时确认清空
        old = [f for f in os.listdir(out_dir) if f.endswith('.png')]
        if old:
            ret = QMessageBox.question(
                self, '确认', f'输出目录中已有 {len(old)} 个 png 文件, 清空后重新导出?',
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
            for f in old:
                os.remove(os.path.join(out_dir, f))

        self.btn_export.setEnabled(False)
        self.progress.setValue(0)
        start, end = self.range_slider.values()
        self.worker = ExportWorker(self.gif_path, out_dir, self.spin_width.value(),
                                   self.spin_fps.value(), self._durs, start, end)
        self.worker.progress.connect(lambda cur, total: self.progress.setRange(0, total) or self.progress.setValue(cur))
        self.worker.failed.connect(self._export_failed)
        self.worker.done.connect(self._export_done)
        self.worker.start()

    def _export_failed(self, idx, msg):
        self.btn_export.setEnabled(True)
        QMessageBox.critical(self, '导出失败', f'帧 {idx}: {msg}')

    def _export_done(self, out_dir):
        self.btn_export.setEnabled(True)
        files = [f for f in os.listdir(out_dir) if f.endswith('.png')]
        total_size = sum(os.path.getsize(os.path.join(out_dir, f)) for f in files) / 1024 / 1024
        QMessageBox.information(
            self, '完成', f'导出完成!\n{len(files)} 帧, 共 {total_size:.1f} MB\n目录: {out_dir}')

    def resizeEvent(self, event):
        """窗口拉伸/全屏时, 当前预览帧立即重适配(等比缩放)"""
        super().resizeEvent(event)
        if self.movie and self.movie.state() == QMovie.Running:
            self._gif_frame_changed(0)
        if getattr(self, '_seq_raw_pixmap', None) and not self._seq_raw_pixmap.isNull():
            self.label_seq.setPixmap(self._seq_raw_pixmap.scaled(
                self.label_seq.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

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
