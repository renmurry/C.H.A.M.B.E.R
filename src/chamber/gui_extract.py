"""The Extract screen: open a sheet or image, click features, keep what's right.

Tools (keys in brackets)
  Area click [A]  click a roof, tree or pond: its outline appears.
                  Shift+click adds a point, Ctrl+click cuts a part away,
                  Tab shows another size, Enter keeps it, Esc drops it.
                  Clicking somewhere new keeps the last one and starts the next.
  Box [B]         drag a box around one feature.
  Snap line [L]   click along a road or stream; Enter (or double-click) to finish,
                  Backspace takes back the last click.
  Point [P]       drop a point (landmarks, poles, wells).
  Pick [V]        select a feature (Delete removes it) or click a line drawn in
                  the PDF to take every line drawn the same way.
  Find similar [F]  look for more features like the ones you kept.
  Read text [T]   map text as points.
Wheel zooms, middle- or right-drag pans, [0] fits the map.

Two layouts: "cols" (panels at the sides) and "focus" (panels float over the
map). The look can change while you work; the layout waits until nothing is
waiting for Keep / Drop, so a switch never costs you a feature.
"""
from __future__ import annotations
import os, threading, time, traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QRectF, QPointF, QSize
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QBrush, QImage, QPixmap, QKeySequence,
                           QShortcut, QFont)
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QToolButton, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                               QGraphicsPathItem, QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsItem,
                               QListWidget, QListWidgetItem, QFileDialog, QCheckBox, QSlider, QComboBox,
                               QLineEdit, QDialog, QDialogButtonBox, QSizePolicy, QButtonGroup, QMessageBox,
                               QInputDialog, QScrollArea)

from . import themes as TM
from .gui_icons import icon
from .extract import source as SRC
from .extract import shapes as SH
from .extract.session import Session, Feature

TOOLS = [("area", "Area click", "A"), ("box", "Box", "B"), ("line", "Snap line", "L"),
         ("brush", "Road Brush", "R"), ("red", "Paint the Map Red (not road)", "X"),
         ("point", "Point", "P"), ("pick", "Pick / take drawn lines", "V")]
PAINT_TOOLS = ("brush", "red")


def TH():
    return TM.current()


# ------------------------------------------------------------------ helpers
def to_qimage(a):
    h, w = a.shape[:2]
    return QImage(np.ascontiguousarray(a).data, w, h, 3 * w, QImage.Format_RGB888).copy()


def geom_path(g):
    """shapely geometry (image px) -> QPainterPath."""
    path = QPainterPath()
    def ring(coords, close):
        c = np.asarray(coords)
        if len(c) == 0:
            return
        path.moveTo(QPointF(*c[0]))
        for x, y in c[1:]:
            path.lineTo(QPointF(x, y))
        if close:
            path.closeSubpath()
    parts = getattr(g, "geoms", [g])
    for p in parts:
        if p.geom_type == "Polygon":
            ring(p.exterior.coords, True)
            for i in p.interiors:
                ring(i.coords, True)
        elif p.geom_type == "LineString":
            ring(p.coords, False)
    return path


def pen(color, width, style=Qt.SolidLine, alpha=255):
    c = QColor(color); c.setAlpha(alpha)
    p = QPen(c, width, style, Qt.RoundCap, Qt.RoundJoin); p.setCosmetic(True)
    return p


class Bridge(QObject):
    done = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(int, int)


# ------------------------------------------------------------------ the map
class MapView(QGraphicsView):
    clicked = Signal(float, float, object, object)        # x, y, modifiers, button
    double = Signal(float, float)
    boxed = Signal(float, float, float, float)
    moved = Signal(float, float)
    dropped = Signal(list)
    resized = Signal()
    painted = Signal(list)                 # stroke points (scene/image px)
    brushSize = Signal(int)                # +1 / -1 from Ctrl+wheel

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.pix = None
        self.tool = "area"
        self._pan = None; self._press = None; self._box = None
        self.brush_px = 40.0
        self._stroke = None; self._stroke_item = None; self._ring = None

    def set_image(self, qimg):
        self.scene().clear(); self._ring = None; self._stroke_item = None
        self.pix = QGraphicsPixmapItem(QPixmap.fromImage(qimg))
        self.pix.setTransformationMode(Qt.SmoothTransformation)
        self.scene().addItem(self.pix)
        self.setSceneRect(QRectF(qimg.rect()).adjusted(-400, -400, 400, 400))
        self.fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.resized.emit()

    def fit(self):
        if self.pix:
            self.fitInView(self.pix, Qt.KeepAspectRatio)

    def zoom_to(self, rect, pad=2.5):
        r = QRectF(rect)
        c = r.center(); w, h = max(r.width(), 40) * pad, max(r.height(), 40) * pad
        self.fitInView(QRectF(c.x() - w / 2, c.y() - h / 2, w, h), Qt.KeepAspectRatio)

    # zoom / pan
    def wheelEvent(self, e):
        if self.tool in PAINT_TOOLS and e.modifiers() & Qt.ControlModifier:
            self.brushSize.emit(1 if e.angleDelta().y() > 0 else -1)
            return
        f = 1.0015 ** e.angleDelta().y()
        cur = self.transform().m11()
        if 0.02 < cur * f < 40:
            self.scale(f, f)

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan = (pos, e.button(), False)
            return
        if e.button() == Qt.LeftButton and self.tool in PAINT_TOOLS and self.pix is not None:
            s = self.mapToScene(pos)
            self._stroke = [(s.x(), s.y())]
            c = QColor("#38bdf8" if self.tool == "brush" else "#ef4444"); c.setAlpha(110)
            pn = QPen(c, 2 * self.brush_px, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            self._stroke_item = QGraphicsPathItem(); self._stroke_item.setPen(pn); self._stroke_item.setZValue(48)
            path = QPainterPath(s); path.lineTo(s + QPointF(0.01, 0.01)); self._stroke_item.setPath(path)
            self.scene().addItem(self._stroke_item)
            return
        if e.button() == Qt.LeftButton:
            self._press = pos
            if self.tool == "box":
                s = self.mapToScene(pos)
                self._box = QGraphicsRectItem(QRectF(s, s))
                self._box.setPen(pen(TH().accent, 2, Qt.DashLine)); self._box.setZValue(50)
                self.scene().addItem(self._box)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        s = self.mapToScene(pos)
        self.moved.emit(s.x(), s.y())
        if self._pan:
            p0, b, _ = self._pan
            d = pos - p0
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            self._pan = (pos, b, True)
            return
        if self._box is not None:
            a = self.mapToScene(self._press)
            self._box.setRect(QRectF(a, s).normalized())
        if self.tool in PAINT_TOOLS:
            self._show_ring(s)
            if self._stroke is not None:
                last = self._stroke[-1]
                if np.hypot(s.x() - last[0], s.y() - last[1]) > max(self.brush_px / 4, 1.5):
                    self._stroke.append((s.x(), s.y()))
                    path = QPainterPath(QPointF(*self._stroke[0]))
                    for x, y in self._stroke[1:]:
                        path.lineTo(QPointF(x, y))
                    self._stroke_item.setPath(path)
                return
        super().mouseMoveEvent(e)

    def _show_ring(self, s):
        if self._ring is None or self._ring.scene() is not self.scene():
            self._ring = QGraphicsEllipseItem(); self._ring.setZValue(70); self.scene().addItem(self._ring)
        col = "#38bdf8" if self.tool == "brush" else "#ef4444"
        self._ring.setPen(pen(col, 1.8)); self._ring.setBrush(Qt.NoBrush)
        r = self.brush_px
        self._ring.setRect(QRectF(s.x() - r, s.y() - r, 2 * r, 2 * r)); self._ring.show()

    def hide_ring(self):
        if self._ring is not None and self._ring.scene() is self.scene():
            self._ring.hide()

    def leaveEvent(self, e):
        self.hide_ring(); super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        pos = e.position().toPoint()
        if self._stroke is not None and e.button() == Qt.LeftButton:
            pts, self._stroke = self._stroke, None
            if self._stroke_item is not None and self._stroke_item.scene() is self.scene():
                self.scene().removeItem(self._stroke_item)
            self._stroke_item = None
            self.painted.emit(pts)
            return
        if self._pan:
            moved = self._pan[2]; b = self._pan[1]; self._pan = None
            if not moved and b == Qt.RightButton:
                s = self.mapToScene(pos); self.clicked.emit(s.x(), s.y(), e.modifiers(), Qt.RightButton)
            return
        if e.button() == Qt.LeftButton and self._press is not None:
            s = self.mapToScene(pos)
            if self._box is not None:
                r = self._box.rect(); self.scene().removeItem(self._box); self._box = None
                if r.width() > 4 and r.height() > 4:
                    self.boxed.emit(r.left(), r.top(), r.right(), r.bottom())
            elif (pos - self._press).manhattanLength() < 6:
                self.clicked.emit(s.x(), s.y(), e.modifiers(), Qt.LeftButton)
            self._press = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        s = self.mapToScene(e.position().toPoint())
        self.double.emit(s.x(), s.y())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        self.dropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def drawBackground(self, p, rect):
        p.fillRect(rect, QColor(TH().map_bg))


# ------------------------------------------------------------------ welcome screen
class Welcome(QWidget):
    """Shown before anything is open: slow-drifting contour lines (like a topo
    map breathing), a pulsing drop target, and how to start."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.t = 0.0
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick)
        rng = np.random.default_rng(7)
        self.hills = [(rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85), rng.uniform(0.25, 0.5),
                       rng.integers(2, 5), rng.uniform(0, 6.28)) for _ in range(3)]

    def showEvent(self, e):
        self.timer.start(66)

    def hideEvent(self, e):
        self.timer.stop()

    def _tick(self):
        self.t += 0.066; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        t = TH(); W, H = self.width(), self.height(); R = min(W, H)
        col = QColor(t.accent)
        th = np.linspace(0, 2 * np.pi, 140)
        for (hx, hy, size, lobes, ph) in self.hills:
            for k in range(1, 11):
                r0 = R * size * k / 10
                wob = 1 + 0.07 * np.sin(lobes * th + ph + self.t * 0.25 + k * 0.4) + 0.03 * np.sin(5 * th - self.t * 0.4)
                xs = W * hx + r0 * wob * np.cos(th); ys = H * hy + r0 * wob * 0.8 * np.sin(th)
                path = QPainterPath(QPointF(xs[0], ys[0]))
                for x, y in zip(xs[1:], ys[1:]):
                    path.lineTo(QPointF(x, y))
                path.closeSubpath()
                c = QColor(col); c.setAlpha(70 if k % 5 == 0 else 30)
                p.setPen(QPen(c, 1.6 if k % 5 == 0 else 1.0)); p.setBrush(Qt.NoBrush); p.drawPath(path)
        # pulsing drop ring
        cx, cy = W / 2, H / 2 - 30
        pulse = (self.t % 2.0) / 2.0
        for i, ph in enumerate((pulse, (pulse + 0.5) % 1.0)):
            c = QColor(col); c.setAlpha(int(160 * (1 - ph)))
            p.setPen(QPen(c, 2)); r = 34 + 46 * ph
            p.drawEllipse(QPointF(cx, cy), r, r)
        pin = QPainterPath(); pin.moveTo(cx, cy + 18)
        pin.cubicTo(cx - 22, cy - 4, cx - 14, cy - 26, cx, cy - 26); pin.cubicTo(cx + 14, cy - 26, cx + 22, cy - 4, cx, cy + 18)
        p.setPen(QPen(col, 2.4)); p.setBrush(QColor(t.backdrop[0])); p.drawPath(pin)
        p.setBrush(col); p.drawEllipse(QPointF(cx, cy - 8), 5, 5)
        f = QFont(); f.setPointSizeF(15); f.setBold(True); p.setFont(f); p.setPen(QColor(t.text))
        p.drawText(QRectF(0, cy + 70, W, 30), Qt.AlignCenter, "Drop a map, sheet or photo here")
        f.setPointSizeF(10); f.setBold(False); p.setFont(f); p.setPen(QColor(t.muted))
        p.drawText(QRectF(0, cy + 102, W, 24), Qt.AlignCenter, "PDF · GeoPDF · GeoTIFF · JPG · PNG      or press Open (Ctrl+O)")
        p.end()


# ------------------------------------------------------------------ state per open file
class FileState:
    def __init__(self, src):
        self.src = src
        self.session = Session(src)
        self.session.layers["Buildings"].square = True
        self.seg = None
        self.styles = None
        self.qimg = to_qimage(src.image)
        self.view_rect = None
        self.strokes = []            # Road Brush / Paint the Map Red strokes
        self.roads = None            # RoadLearner, made on the first stroke


class Pending:
    """What's on screen waiting for Keep / Drop."""
    def __init__(self, layer, polys, scores, method, prompts=None, result=None, surface=None, attrs=None):
        self.layer, self.polys, self.scores, self.method = layer, polys, scores, method
        self.idx = 0
        self.prompts = prompts or {"points": [], "labels": [], "box": None}
        self.result = result
        self.surface = surface       # road segments: the road surface polygon that goes with the centreline
        self.attrs = attrs or {}

    @property
    def geom(self):
        return self.polys[self.idx]


# ------------------------------------------------------------------ the page
class ExtractPage(QWidget):
    toast = Signal(str)
    sound = Signal(str)
    stat = Signal(str, float)            # badge counters: (key, amount)
    pendingChanged = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.files: list[FileState] = []
        self.cur: FileState | None = None
        self.pending: Pending | None = None
        self.review = []                      # find-similar candidates waiting
        self.line_clicks = []; self.line_preview = None
        self.selected = None                  # (layer name, Feature)
        self.active_layer = "Buildings"
        self.picked_style = None
        self.layout_mode = "cols"
        self.bridge = Bridge()
        self.bridge.done.connect(self._job_done); self.bridge.failed.connect(self._job_failed)
        self.bridge.progress.connect(self._job_progress)
        self._job = None; self._queued = None
        self._ants = 0
        self._ant_timer = QTimer(self); self._ant_timer.timeout.connect(self._march); self._ant_timer.start(90)
        self._scan = None; self._scan_t = QTimer(self); self._scan_t.timeout.connect(self._scan_step)
        self._build()
        self._shortcuts()
        self.set_layout("cols")
        self.restyle()
        self._waiting(False)
        for w in self._road_widgets:
            w.hide()
        self._refresh_all()

    # ============================================================ build
    def _card(self, title=None, name="card"):
        f = QFrame(); f.setObjectName(name)
        lay = QVBoxLayout(f); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(8)
        if title:
            t = QLabel(title.upper()); t.setObjectName("cardTitle"); lay.addWidget(t)
        return f, lay

    def _build(self):
        self.map = MapView()
        self.map.clicked.connect(self._on_click); self.map.double.connect(self._on_double)
        self.map.boxed.connect(self._on_box); self.map.moved.connect(self._on_move)
        self.map.dropped.connect(self.open_files)
        self.map.resized.connect(self._map_resized)
        self.map.painted.connect(self._on_painted)
        self.map.brushSize.connect(self._brush_step)
        self.brush_m = float(self.settings.value("brush_m", 4.0, type=float))
        self._heat = None
        self.empty = Welcome(self.map)
        self.combo = 0; self._combo_t = 0.0
        self.combo_chip = QLabel(self.map); self.combo_chip.hide()
        self.combo_chip.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._fx = []                                     # live map effects: [kind, item, t0, data]
        self._fx_timer = QTimer(self); self._fx_timer.timeout.connect(self._fx_step)
        self._think = None
        self._flash = (None, 0.0)

        # --- tools
        self.tools = QFrame(); self.tools.setObjectName("card")
        self.tools_lay = QBoxLayout(QBoxLayout.LeftToRight, self.tools)
        self.tools_lay.setContentsMargins(8, 8, 8, 8); self.tools_lay.setSpacing(6)
        self.tool_group = QButtonGroup(self); self.tool_group.setExclusive(True)
        self.tool_btn = {}
        for key, name, k in TOOLS:
            b = QToolButton(); b.setObjectName("tool"); b.setCheckable(True); b.setToolTip(f"{name}  [{k}]")
            b.setAccessibleName(name); b.setIconSize(QSize(20, 20)); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, t=key: self.set_tool(t))
            self.tool_group.addButton(b); self.tools_lay.addWidget(b); self.tool_btn[key] = b
        self.sep1 = QFrame(); self.sep1.setFixedSize(1, 28); self.tools_lay.addWidget(self.sep1)
        self.act_btn = {}
        for key, name, k, fn in (("similar", "Find similar", "F", self.find_similar), ("text", "Read map text", "T", self.read_text),
                                 ("undo", "Undo", "Ctrl+Z", self.undo), ("redo", "Redo", "Ctrl+Y", self.redo),
                                 ("fit", "Fit map", "0", lambda: self.map.fit()),
                                 ("files", "Files and drawn lines", "", self._toggle_files)):
            b = QToolButton(); b.setObjectName("tool"); b.setToolTip(f"{name}  [{k}]"); b.setAccessibleName(name)
            b.setIconSize(QSize(20, 20)); b.setCursor(Qt.PointingHandCursor); b.clicked.connect(fn)
            self.tools_lay.addWidget(b); self.act_btn[key] = b
        self.tool_btn["area"].setChecked(True)

        # --- files card
        self.files_card, fl = self._card("Files")
        self.file_list = QListWidget(); self.file_list.setMinimumHeight(70)
        self.file_list.currentRowChanged.connect(self._switch_file)
        fl.addWidget(self.file_list)
        row = QHBoxLayout()
        self.open_btn = QPushButton(" Open…"); self.open_btn.clicked.connect(self._pick_files)
        self.close_btn = QPushButton(" Remove"); self.close_btn.clicked.connect(self.close_current)
        self.close_btn.setToolTip("Remove the selected file from the list  [Ctrl+W]\nRight-click the list to remove all\n(the file on disk is not touched)")
        row.addWidget(self.open_btn); row.addStretch(1); row.addWidget(self.close_btn); fl.addLayout(row)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_menu)
        self.place_lbl = QLabel("—"); self.place_lbl.setWordWrap(True); self.place_lbl.setObjectName("muted")
        fl.addWidget(self.place_lbl)
        self.crs_row = QWidget(); cr = QHBoxLayout(self.crs_row); cr.setContentsMargins(0, 0, 0, 0)
        cr.addWidget(QLabel("EPSG")); self.crs_edit = QLineEdit(); self.crs_edit.setPlaceholderText("e.g. 32633")
        self.crs_edit.editingFinished.connect(self._set_epsg); cr.addWidget(self.crs_edit)
        fl.addWidget(self.crs_row); self.crs_row.hide()
        t = QLabel("DRAWN IN THIS PDF"); t.setObjectName("cardTitle"); fl.addWidget(t)
        self.style_list = QListWidget(); self.style_list.setMinimumHeight(90)
        self.style_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.style_list.setTextElideMode(Qt.ElideRight)
        self.style_list.currentRowChanged.connect(self._style_selected)
        fl.addWidget(self.style_list, 1)
        self.take_btn = QPushButton("Take into layer"); self.take_btn.clicked.connect(self._take_style)
        fl.addWidget(self.take_btn)

        # --- layers card
        self.layers_card, ll = self._card("Layers")
        self.layer_list = QListWidget(); self.layer_list.setMinimumHeight(150)
        self.layer_list.itemClicked.connect(self._layer_clicked)
        ll.addWidget(self.layer_list)
        row = QHBoxLayout()
        self.new_layer_btn = QPushButton("+ Layer"); self.new_layer_btn.clicked.connect(self._new_layer)
        self.export_btn = QPushButton(" Export"); self.export_btn.setObjectName("primary"); self.export_btn.clicked.connect(self.export)
        row.addWidget(self.new_layer_btn); row.addStretch(1); row.addWidget(self.export_btn); ll.addLayout(row)

        # --- pending / selected card
        self.pend_card, pl = self._card("Selected")
        self.pend_title = QLabel("Nothing yet"); self.pend_title.setObjectName("big")
        self.pend_info = QLabel("Pick a tool and click the map."); self.pend_info.setObjectName("muted"); self.pend_info.setWordWrap(True)
        pl.addWidget(self.pend_title); pl.addWidget(self.pend_info)
        row = QHBoxLayout(); row.setSpacing(6)
        self.keep_btn = QPushButton(" Keep"); self.keep_btn.setObjectName("primary"); self.keep_btn.clicked.connect(self.accept)
        self.keep_btn.setToolTip("Keep it  [Enter]")
        self.drop_btn = QPushButton(" Drop"); self.drop_btn.clicked.connect(self.reject); self.drop_btn.setToolTip("Drop it  [Esc]")
        self.cycle_btn = QToolButton(); self.cycle_btn.setObjectName("tool"); self.cycle_btn.setToolTip("Another size  [Tab]")
        self.cycle_btn.setAccessibleName("Another size"); self.cycle_btn.clicked.connect(self.cycle)
        for b in (self.keep_btn, self.drop_btn):
            b.setMinimumWidth(96); row.addWidget(b, 1)
        row.addWidget(self.cycle_btn)
        pl.addLayout(row)
        self.all_btn = QPushButton("Keep all the rest"); self.all_btn.clicked.connect(self.accept_all)
        self.all_btn.setVisible(False); pl.addWidget(self.all_btn)
        self.opts = QWidget(); og = QGridLayout(self.opts); og.setContentsMargins(0, 4, 0, 0); og.setVerticalSpacing(6)
        self.square_cb = QCheckBox("Square up outlines"); self.square_cb.toggled.connect(self._square_toggled)
        self.snap_cb = QCheckBox("Snap lines to the road"); self.snap_cb.setChecked(True)
        og.addWidget(self.square_cb, 0, 0, 1, 3); og.addWidget(self.snap_cb, 1, 0, 1, 3)
        l1 = QLabel("Find similar"); l1.setObjectName("muted"); og.addWidget(l1, 2, 0)
        self.scope = QComboBox(); self.scope.addItems(["Whole image", "This area", "All open files"]); og.addWidget(self.scope, 2, 1, 1, 2)
        lr = QLabel("Roads"); lr.setObjectName("muted"); og.addWidget(lr, 4, 0)
        self.road_scope = QComboBox(); self.road_scope.addItems(["From my strokes", "Whole image"])
        self.road_scope.setToolTip("Trace roads joined to what you painted, or every road on the image"); og.addWidget(self.road_scope, 4, 1, 1, 2)
        lw = QLabel("Width"); lw.setObjectName("muted"); og.addWidget(lw, 5, 0)
        self.width_mode = QComboBox(); self.width_mode.addItems(["Measured", "Brush width"])
        self.width_mode.setToolTip("Road width: measured from the image along each road, or the brush width")
        self.width_mode.currentIndexChanged.connect(self._width_mode_changed); og.addWidget(self.width_mode, 5, 1, 1, 2)
        self.heat_cb = QCheckBox("Show what it learned"); self.heat_cb.setChecked(True); self.heat_cb.toggled.connect(lambda _: self._draw_heat())
        og.addWidget(self.heat_cb, 6, 0, 1, 3)
        self.find_roads_btn = QPushButton(" Find roads"); self.find_roads_btn.setObjectName("primary")
        self.find_roads_btn.setToolTip("Learn from your strokes and trace the roads  [Enter]"); self.find_roads_btn.clicked.connect(self.find_roads)
        self.clear_paint_btn = QPushButton("Clear"); self.clear_paint_btn.setToolTip("Clear all paint strokes on this map")
        self.clear_paint_btn.clicked.connect(self.clear_paint)
        og.addWidget(self.find_roads_btn, 7, 0, 1, 2); og.addWidget(self.clear_paint_btn, 7, 2)
        self._road_widgets = (lr, self.road_scope, lw, self.width_mode, self.heat_cb, self.find_roads_btn, self.clear_paint_btn)
        l2 = QLabel("Looser"); l2.setObjectName("muted"); og.addWidget(l2, 3, 0)
        self.strict = QSlider(Qt.Horizontal); self.strict.setRange(70, 95); self.strict.setValue(86); og.addWidget(self.strict, 3, 1)
        l3 = QLabel("Stricter"); l3.setObjectName("muted"); og.addWidget(l3, 3, 2)
        pl.addWidget(self.opts)

        # --- status strip
        self.status = QFrame(); self.status.setObjectName("card")
        sl = QHBoxLayout(self.status); sl.setContentsMargins(12, 4, 12, 4); sl.setSpacing(18)
        self.st_coord = QLabel("—"); self.st_model = QLabel("Model: idle"); self.st_hint = QLabel("")
        for w in (self.st_coord, self.st_hint, self.st_model):
            w.setObjectName("muted")
        sl.addWidget(self.st_coord); sl.addWidget(self.st_hint, 1); sl.addWidget(self.st_model)

        self.root = QVBoxLayout(self); self.root.setContentsMargins(0, 0, 0, 0); self.root.setSpacing(10)

    def _shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self); s.setContext(Qt.WidgetWithChildrenShortcut); s.activated.connect(fn)
        for key, _n, k in TOOLS:
            sc(k, lambda t=key: self.set_tool(t))
        sc("F", self.find_similar); sc("T", self.read_text); sc("0", self.map.fit)
        sc("Return", self._enter); sc("Enter", self._enter); sc("Escape", self.reject)
        sc("Tab", self.cycle); sc("Backspace", self._backspace); sc("Delete", self._delete_selected)
        sc(QKeySequence.Undo, self.undo); sc(QKeySequence.Redo, self.redo); sc("Ctrl+Y", self.redo)
        sc("Ctrl+O", self._pick_files); sc("Ctrl+E", self.export); sc("Ctrl+W", self.close_current)
        sc("]", lambda: self._brush_step(1)); sc("[", lambda: self._brush_step(-1))

    # ============================================================ layouts & looks
    def _clear_root(self):
        for w in (self.files_card, self.layers_card, self.pend_card, self.tools, self.status, self.map):
            w.setParent(None)
        while self.root.count():
            it = self.root.takeAt(0)
            if it.layout():
                it.layout().setParent(None)

    def set_layout(self, mode):
        """'cols' or 'focus'. Rebuilds where the panels sit; nothing is lost."""
        self.layout_mode = mode
        self._clear_root()
        for w in (self.files_card, self.layers_card, self.pend_card, self.tools, self.status):
            w.setObjectName("card" if mode == "cols" else "float")
        if mode == "cols":
            self.tools_lay.setDirection(QBoxLayout.LeftToRight); self.sep1.setFixedSize(1, 28)
            body = QHBoxLayout(); body.setSpacing(10)
            self.files_card.setFixedWidth(250); body.addWidget(self.files_card)
            mid = QVBoxLayout(); mid.setSpacing(10)
            mid.addWidget(self.tools, 0, Qt.AlignLeft); mid.addWidget(self.map, 1)
            body.addLayout(mid, 1)
            right = QVBoxLayout(); right.setSpacing(10)
            self.layers_card.setFixedWidth(300); self.pend_card.setFixedWidth(300)
            right.addWidget(self.layers_card, 1); right.addWidget(self.pend_card, 0)
            body.addLayout(right)
            self.root.addLayout(body, 1)
            self.root.addWidget(self.status)
            for w in (self.files_card, self.layers_card, self.pend_card, self.tools, self.status, self.map):
                w.show()
            self.opts.show(); self.st_hint.show()
        else:
            self.root.addWidget(self.map, 1)
            for w in (self.files_card, self.layers_card, self.pend_card, self.tools, self.status):
                w.setParent(self.map); w.show(); w.raise_()
            self.tools_lay.setDirection(QBoxLayout.TopToBottom); self.sep1.setFixedSize(28, 1)
            self.files_card.setFixedWidth(250); self.layers_card.setFixedWidth(250); self.pend_card.setFixedWidth(330)
            self.opts.setVisible(False); self.st_hint.setVisible(False)
            self.files_card.setVisible(not self.files)        # out of the way once a map is open
            self._place_floats()
        self.act_btn["files"].setVisible(mode == "focus")
        self.empty.raise_()
        self.restyle()

    def _toggle_files(self):
        if self.layout_mode == "focus":
            self.files_card.setVisible(not self.files_card.isVisible())
            self._place_floats()

    def _place_floats(self):
        if self.layout_mode != "focus":
            return
        W, H = self.map.width(), self.map.height()
        m = 14
        self.tools.adjustSize()
        self.tools.move(m, max(m, (H - self.tools.height()) // 2))
        fh = min(max(self.files_card.sizeHint().height(), 360), H - 2 * m)
        self.files_card.setGeometry(m + self.tools.width() + m, m, 250, fh)
        lh = min(self.layers_card.sizeHint().height() + 40, int(H * 0.5))
        self.layers_card.setGeometry(W - 250 - m, m, 250, lh)
        self.pend_card.adjustSize()
        ph = self.pend_card.sizeHint().height()
        self.pend_card.setGeometry((W - 330) // 2, H - ph - m, 330, ph)
        sh = self.status.sizeHint().height()
        sw = min(360, (W - 330) // 2 - 2 * m)
        self.status.setGeometry(W - sw - m, H - sh - m, sw, sh)

    def _map_resized(self):
        self.empty.setGeometry(0, 0, self.map.width(), self.map.height())
        self._place_floats()
        if self.combo_chip.isVisible():
            self._place_chip()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._map_resized()
        self._place_floats()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._place_floats)

    def restyle(self):
        """Re-colour icons and overlays for the current theme."""
        t = TH()
        for key, b in self.tool_btn.items():
            b.setIcon(icon(key, t.on_accent if b.isChecked() and not t.dark else t.text))
        for key, b in self.act_btn.items():
            b.setIcon(icon(key, t.text))
        self.cycle_btn.setIcon(icon("cycle", t.text))
        self.keep_btn.setIcon(icon("check", t.on_accent)); self.drop_btn.setIcon(icon("x", t.text))
        self.open_btn.setIcon(icon("open", t.text)); self.export_btn.setIcon(icon("export", t.on_accent))
        self.close_btn.setIcon(icon("x", t.text))
        self.sep1.setStyleSheet(f"background: {t.card_border};")
        self.map.viewport().update()
        self._refresh_layers(); self._draw()
        if self.layout_mode == "focus":
            QTimer.singleShot(0, self._place_floats)

    # ============================================================ files
    def _pick_files(self):
        last = self.settings.value("extract_dir", "", type=str)
        paths, _ = QFileDialog.getOpenFileNames(self, "Open maps or images", last, SRC.OPEN_FILTER)
        if paths:
            self.settings.setValue("extract_dir", str(Path(paths[0]).parent))
            self.open_files(paths)

    def open_files(self, paths):
        paths = [p for p in paths if Path(p).suffix.lower() in SRC.PDF_EXT | SRC.IMG_EXT]
        if not paths:
            return
        self.st_model.setText(f"Opening {len(paths)} file(s)…")
        self._run("open", lambda: [SRC.open_source(p) for p in paths])

    def _add_sources(self, srcs):
        for s in srcs:
            fs = FileState(s); self.files.append(fs)
            it = QListWidgetItem(s.name); it.setToolTip(s.path); self.file_list.addItem(it)
            if s.placement.startswith("Grid labels"):
                self.stat.emit("placed_by_grid", 1)
        self.file_list.setCurrentRow(len(self.files) - 1)
        if self.layout_mode == "focus":
            self.files_card.hide(); self._place_floats()

    def _switch_file(self, row):
        if row < 0 or row >= len(self.files):
            return
        if self.cur is not None and self.cur in self.files:
            self.cur.view_rect = self.map.mapToScene(self.map.viewport().rect()).boundingRect()
        self._drop_pending(silent=True); self.review.clear(); self.line_clicks.clear(); self.selected = None
        self.cur = self.files[row]
        self.map.set_image(self.cur.qimg)
        if self.cur.view_rect is not None:
            self.map.fitInView(self.cur.view_rect, Qt.KeepAspectRatio)
        self.empty.hide()
        s = self.cur.src
        gsd = s.gsd
        txt = f"Placed from: {s.placement}"
        if s.epsg:
            txt += f"\nEPSG:{s.epsg}"
        if gsd:
            txt += f" · {gsd * 100:.1f} cm/px" if gsd < 1 else f" · {gsd:.2f} m/px"
        for n in s.notes:
            txt += f"\n• {n}"
        self.place_lbl.setText(txt)
        self.crs_row.setVisible(s.placed and s.epsg is None)
        self._load_styles()
        self._refresh_all()

    def _file_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        if not self.files:
            return
        m = QMenu(self)
        a1 = m.addAction("Remove"); a2 = m.addAction("Remove all")
        it = self.file_list.itemAt(pos)
        a1.setEnabled(it is not None)
        got = m.exec(self.file_list.mapToGlobal(pos))
        if got is a1 and it is not None:
            self.close_files([self.file_list.row(it)])
        elif got is a2:
            self.close_files(list(range(len(self.files))))

    def close_current(self):
        r = self.file_list.currentRow()
        if 0 <= r < len(self.files):
            self.close_files([r])

    def close_files(self, rows):
        """Remove files from the list (never from disk); asks first if any has
        kept features not yet exported."""
        if self._job:
            self.toast.emit("Wait a moment: still working on the last step"); return
        rows = sorted(set(r for r in rows if 0 <= r < len(self.files)), reverse=True)
        unsaved = [self.files[r] for r in rows if self.files[r].session.unsaved]
        if unsaved:
            names = "\n".join(f"• {fs.src.name} ({fs.session.count()} kept)" for fs in unsaved[:6])
            ans = QMessageBox.question(self, "C.H.A.M.B.E.R",
                                       f"These have features that haven't been exported:\n\n{names}\n\nRemove anyway?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
        closing_cur = self.cur is not None and self.files.index(self.cur) in rows
        if closing_cur:
            self.pending = None; self.review.clear(); self.line_clicks.clear(); self.line_preview = None
            self.selected = None; self.picked_style = None
        self.review = [(fs, c) for fs, c in self.review if self.files.index(fs) not in rows]
        self.file_list.blockSignals(True)
        for r in rows:
            self.file_list.takeItem(r)
            del self.files[r]                       # drops its image and model memory too
        self.file_list.blockSignals(False)
        if not self.files:
            self.cur = None
            self.map.scene().clear(); self.map.pix = None; self._items = []; self._pend_items = []
            self.empty.show(); self.empty.raise_()
            self.place_lbl.setText("—"); self.crs_row.hide()
            self.style_list.clear(); self.layer_list.clear()
            self.pend_title.setText("Nothing yet"); self.pend_info.setText("Open a map or image to start.")
            self.st_coord.setText("—"); self.st_model.setText("Model: idle")
            self.pendingChanged.emit(False)
            self._refresh_all()
        elif closing_cur:
            self.cur = None
            self.file_list.setCurrentRow(min(rows[-1], len(self.files) - 1))
            self._switch_file(self.file_list.currentRow())
        self.toast.emit(f"Removed {len(rows)} file{'s' if len(rows) != 1 else ''}")

    def _set_epsg(self):
        if not self.cur:
            return
        try:
            from pyproj import CRS
            e = int(self.crs_edit.text().strip()); CRS.from_epsg(e)
            self.cur.src.epsg = e
            self._switch_file(self.file_list.currentRow())
        except Exception:
            self.toast.emit("That EPSG code isn't known")

    # ============================================================ drawn PDF styles
    def _load_styles(self):
        self.style_list.clear(); self.picked_style = None
        if self.cur.src.kind != "pdf":
            self.style_list.addItem("(not a PDF)"); self.style_list.setEnabled(False); self.take_btn.setEnabled(False)
            return
        if self.cur.styles is None:
            from .extract import pdfvec
            try:
                self.cur.styles = pdfvec.read_styles(self.cur.src)
            except Exception:
                self.cur.styles = []
        st = self.cur.styles
        self.style_list.setEnabled(bool(st)); self.take_btn.setEnabled(bool(st))
        if not st:
            self.style_list.addItem("Nothing drawn: it's a flat image")
            self.style_list.setEnabled(False)
        for s in st:
            pm = QPixmap(14, 14); pm.fill(Qt.transparent)
            pp = QPainter(pm); pp.setBrush(QColor(s.fill or s.stroke or "#888")); pp.setPen(QPen(QColor(s.stroke or "#6b7280"), 2))
            pp.drawRect(1, 1, 12, 12); pp.end()
            it = QListWidgetItem(f"{s.label}  ·  {len(s.paths)}"); it.setIcon(icon_from_pixmap(pm))
            self.style_list.addItem(it)

    def _style_selected(self, row):
        if self.cur and self.cur.styles and 0 <= row < len(self.cur.styles):
            self.picked_style = self.cur.styles[row]
            s = self.picked_style
            self.pend_title.setText(s.label)
            self.pend_info.setText(f"{len(s.paths)} drawn {'shapes' if s.kind == 'polygon' else 'lines'} · "
                                   f"Take puts them into “{self.active_layer}”")
            self._draw()

    def _take_style(self):
        if not (self.cur and self.picked_style):
            return
        from .extract import pdfvec
        h, w = self.cur.src.image.shape[:2]
        geoms = pdfvec.style_geometries(self.picked_style, (w, h))
        kind = "polygon" if all(g.geom_type == "Polygon" for g in geoms) else "line"
        L = self.cur.session.layers.get(self.active_layer)
        if L is None or L.kind != kind:
            name = self.picked_style.label.split("  ")[0]
            L = self.cur.session.layer(name, kind, self.picked_style.stroke or self.picked_style.fill or "#e879f9")
        if kind == "line":
            geoms = [g for g in geoms if g.geom_type == "LineString"]
        else:
            geoms = [g for g in geoms if g.geom_type == "Polygon"]
        self.cur.session.add(L.name, [Feature(g, "pdf") for g in geoms])
        self.toast.emit(f"Took {len(geoms)} from the PDF into {L.name}")
        self.sound.emit("combo"); self._flash = (L.name, time.time())
        for g in geoms[:40]:
            self._spawn("keep", g, QColor(L.color))
        self.stat.emit("features", len(geoms))
        self.picked_style = None; self.style_list.clearSelection()
        self._refresh_all()

    # ============================================================ layers
    def _refresh_layers(self):
        self.layer_list.clear()
        if not self.cur:
            return
        t = TH()
        for L in self.cur.session.layers.values():
            n = len(L.features)
            unit = ""
            if n and L.kind != "point" and self.cur.src.metric:
                tot = sum(self.cur.session.measure(f.geom)[1] for f in L.features)
                unit = f"  ·  {tot / 1e4:.2f} ha" if L.kind == "polygon" and tot > 5000 else (
                       f"  ·  {tot:.0f} m²" if L.kind == "polygon" else (f"  ·  {tot / 1000:.2f} km" if tot > 1000 else f"  ·  {tot:.0f} m"))
            mark = "●" if L.name == self.active_layer else "○"
            it = QListWidgetItem(f"{mark}  {L.name}   {n}{unit}")
            pm = QPixmap(16, 16); pm.fill(Qt.transparent)
            p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
            c = QColor(L.color)
            if L.visible:
                c2 = QColor(c); c2.setAlpha(80); p.setBrush(c2)
            else:
                p.setBrush(Qt.NoBrush)
            p.setPen(QPen(c, 2)); p.drawRoundedRect(2, 2, 12, 12, 3, 3); p.end()
            it.setIcon(icon_from_pixmap(pm))
            it.setData(Qt.UserRole, L.name)
            it.setToolTip("Click: draw into this layer · Ctrl+click: show / hide")
            if L.name == self.active_layer:
                f = it.font(); f.setBold(True); it.setFont(f)
            if self._flash[0] == L.name and time.time() - self._flash[1] < 0.7:
                fc = QColor(L.color); fc.setAlpha(90); it.setBackground(fc)
            if not L.visible:
                it.setForeground(QColor(t.muted))
            self.layer_list.addItem(it)
        L = self.cur.session.layers.get(self.active_layer)
        if L is not None and L.kind == "line":
            self.width_mode.blockSignals(True)
            self.width_mode.setCurrentIndex(1 if getattr(L, "width_mode", "measured") == "fixed" else 0)
            self.width_mode.blockSignals(False)
        self.square_cb.blockSignals(True)
        self.square_cb.setChecked(bool(L and getattr(L, "square", False)))
        self.square_cb.setEnabled(bool(L and L.kind == "polygon"))
        self.square_cb.blockSignals(False)

    def _layer_clicked(self, item):
        name = item.data(Qt.UserRole)
        from PySide6.QtWidgets import QApplication
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            L = self.cur.session.layers[name]; L.visible = not L.visible
        else:
            self.active_layer = name
            k = self.cur.session.layers[name].kind
            tool = {"polygon": "area", "line": "line", "point": "point"}[k]
            if self.map.tool not in ("pick",) and self._tool_kind(self.map.tool) != k:
                self.set_tool(tool, keep_layer=True)
        self._refresh_layers(); self._draw()

    def _new_layer(self):
        name, ok = QInputDialog.getText(self, "New layer", "Name (e.g. Ponds, Footpaths, Poles):")
        if not ok or not name.strip() or not self.cur:
            return
        kinds = ["polygon (areas)", "line", "point"]
        k, ok = QInputDialog.getItem(self, "New layer", "What kind of features?", kinds, 0, False)
        if not ok:
            return
        palette = ["#e879f9", "#f97316", "#a3e635", "#38bdf8", "#facc15", "#fb7185"]
        n = len(self.cur.session.layers)
        for fs in self.files:
            fs.session.layer(name.strip(), k.split(" ")[0], palette[n % len(palette)])
        self.active_layer = name.strip(); self._refresh_layers()

    def _square_toggled(self, on):
        L = self.cur and self.cur.session.layers.get(self.active_layer)
        if L:
            L.square = on
            if self.pending and self.pending.layer == L.name and self.pending.result is not None:
                self._polys_from_result(self.pending)
                self._show_pending()

    # ============================================================ tools
    @staticmethod
    def _tool_kind(tool):
        return {"area": "polygon", "box": "polygon", "line": "line", "point": "point", "brush": "line", "red": "line"}.get(tool)

    def set_tool(self, tool, keep_layer=False):
        if tool != "line" and self.line_clicks:
            self._finish_line()
        self.map.tool = tool
        self.tool_btn[tool].setChecked(True)
        painting = tool in PAINT_TOOLS
        self.map.setCursor(Qt.BlankCursor if painting else (Qt.CrossCursor if tool != "pick" else Qt.PointingHandCursor))
        if not painting:
            self.map.hide_ring()
        for w in self._road_widgets:
            w.setVisible(painting)
        self.opts.setVisible(self.layout_mode == "cols" or painting)
        self._update_brush()
        if self.layout_mode == "focus":
            QTimer.singleShot(0, self._place_floats)
        k = self._tool_kind(tool)
        if self.cur and k and not keep_layer:
            L = self.cur.session.layers.get(self.active_layer)
            if not L or L.kind != k:
                self.active_layer = {"polygon": "Buildings", "line": "Roads", "point": "Landmarks"}[k]
        hints = {"area": "Click a feature · Shift+click add · Ctrl+click cut · Tab size · Enter keep",
                 "box": "Drag a box around one feature", "line": "Click along it · Enter to finish · Backspace undo a click",
                 "point": "Click to drop a point", "pick": "Click a feature to select · click a drawn PDF line to take its style",
                 "brush": "Paint along roads · Ctrl+wheel or [ ] brush size · Enter finds roads · Backspace undoes a stroke",
                 "red": "Paint what isn't road · close a loop to paint everything inside red · Enter finds roads"}
        self.st_hint.setText(hints[tool])
        self.restyle()

    def _need_model(self):
        from .extract import sam
        if not sam.available():
            QMessageBox.warning(self, "C.H.A.M.B.E.R", "The outline model files are missing from assets/models.")
            return False
        if self.cur.seg is None:
            self.cur.seg = sam.Segmenter(self.cur.src.image, self.cur.src.gsd)
        return True

    def _on_click(self, x, y, mods, button):
        if not self.cur:
            return
        h, w = self.cur.src.image.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return
        tool = self.map.tool
        if button == Qt.RightButton:
            if tool == "line" and self.line_clicks:
                self._backspace()
            return
        if self.review:
            self.toast.emit("Reviewing found features: Enter keeps, Esc drops")
            return
        if tool in ("area",):
            add = bool(mods & Qt.ShiftModifier); cut = bool(mods & (Qt.ControlModifier | Qt.AltModifier))
            if self.pending and self.pending.method in ("click", "box") and (add or cut):
                pr = self.pending.prompts
                pr["points"].append((x, y)); pr["labels"].append(0 if cut else 1)
                self._predict(self.pending.layer, pr, refine=self.pending.result)
                return
            if self.pending:
                self.accept()
            self._predict(self.active_layer, {"points": [(x, y)], "labels": [1], "box": None})
        elif tool == "line":
            self.line_clicks.append((x, y)); self._update_line_preview()
        elif tool == "point":
            from shapely.geometry import Point
            if self.pending:
                self.accept()
            self.cur.session.add(self.active_layer, Feature(Point(x, y), "point"))
            self._celebrate(self.active_layer, Point(x, y))
            self.stat.emit("features", 1); self._refresh_all()
        elif tool == "pick":
            self._pick_at(x, y)

    def _on_box(self, x0, y0, x1, y1):
        if not self.cur or self.map.tool != "box":
            return
        if self.pending:
            self.accept()
        self._predict(self.active_layer, {"points": [], "labels": [], "box": (x0, y0, x1, y1)})

    def _on_double(self, x, y):
        if self.map.tool == "line" and len(self.line_clicks) >= 2:
            self._finish_line()

    def _on_move(self, x, y):
        if not self.cur:
            return
        h, w = self.cur.src.image.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return
        s = self.cur.src
        if s.placed:
            X, Y = s.to_map(x, y)
            self.st_coord.setText(f"{float(X):,.2f} E · {float(Y):,.2f} N" if s.metric else f"{float(X):.6f}, {float(Y):.6f}")
        else:
            self.st_coord.setText(f"pixel {x:.0f}, {y:.0f}")

    def _pick_at(self, x, y):
        from shapely.geometry import Point
        p = Point(x, y)
        tol = 8 / max(self.map.transform().m11(), 1e-6)
        best = None
        for L in self.cur.session.layers.values():
            if not L.visible:
                continue
            for f in L.features:
                d = f.geom.distance(p) if f.geom.geom_type != "Polygon" else (0 if f.geom.contains(p) else f.geom.exterior.distance(p))
                if d <= tol and (best is None or d < best[0]):
                    best = (d, L.name, f)
        if best:
            self.selected = (best[1], best[2]); self._show_selected(); self._draw(); return
        self.selected = None
        if self.cur.styles:
            from .extract import pdfvec
            s = pdfvec.nearest_style(self.cur.styles, x, y, tol * 1.5)
            if s:
                self.style_list.setCurrentRow(self.cur.styles.index(s))
                return
        self._show_selected(); self._draw()

    def _show_selected(self):
        if not self.selected:
            self.pend_title.setText("Nothing selected"); self.pend_info.setText("")
            return
        lname, f = self.selected
        kind, v, u = self.cur.session.measure(f.geom)
        val = f"{v:,.1f} {u}" if kind != "point" else ""
        self.pend_title.setText(f"{lname[:-1] if lname.endswith('s') else lname}" + (f" · {val}" if val else ""))
        self.pend_info.setText(f"{f.method}" + (f" · “{f.text}”" if f.text else "") + "  ·  Delete removes it")

    def _delete_selected(self):
        if self.file_list.hasFocus():
            self.close_current(); return
        if self.selected and self.cur:
            self.cur.session.remove(*self.selected); self.selected = None
            self._show_selected(); self._refresh_all()

    # ============================================================ outlines (model)
    def _predict(self, layer, prompts, refine=None):
        if not self._need_model():
            return
        seg = self.cur.seg
        pts, labs, box = list(prompts["points"]), list(prompts["labels"]), prompts["box"]
        new_window = True
        if refine is not None:
            new_window = False
        else:
            xs = [p[0] for p in pts] + ([box[0], box[2]] if box else [])
            ys = [p[1] for p in pts] + ([box[1], box[3]] if box else [])
            h, w = self.cur.src.image.shape[:2]
            cx, cy = np.mean(xs), np.mean(ys)
            new_window = not any(abs(k[0] + seg.size / 2 - cx) < seg.size / 2 and abs(k[1] + seg.size / 2 - cy) < seg.size / 2
                                 for k in list(seg.cache))
        self.st_model.setText("Model: reading this area…" if new_window else "Model: outlining…")
        if refine is None:
            xs = [p[0] for p in pts] + ([box[0], box[2]] if box else [])
            ys = [p[1] for p in pts] + ([box[1], box[3]] if box else [])
            wx, wy = seg.window_pos(xs, ys)
            if not seg.is_encoded(wx, wy):
                h, w = self.cur.src.image.shape[:2]
                self._start_think(QRectF(wx, wy, min(seg.size, w - wx), min(seg.size, h - wy)))
                self.sound.emit("thinking")
        method = "box" if box else "click"
        def job():
            t0 = time.time()
            r = seg.predict(pts, labs, box=box, prev=refine)
            return (layer, prompts, r, method, time.time() - t0)
        self._run("predict", job)

    def _polys_from_result(self, pend):
        r = pend.result
        gsd = self.cur.src.gsd
        simp = (0.15 / gsd) if gsd else 1.5
        L = self.cur.session.layers.get(pend.layer)
        square = bool(L and getattr(L, "square", False))
        polys, scores = [], []
        for m, s in zip(r.masks, r.scores):
            p = SH.mask_to_polygon(m, r.window.x0, r.window.y0, simplify_px=max(simp, 1.0))
            if p is None:
                continue
            if square:
                p = SH.square_up(p, tol_px=max(simp * 1.5, 1.5))
            if any(abs(p.area - q.area) < 0.02 * max(p.area, 1) for q in polys):
                continue
            polys.append(p); scores.append(float(s))
        pend.polys, pend.scores = polys, scores
        pend.idx = min(pend.idx, max(len(polys) - 1, 0))

    def _show_pending(self):
        p = self.pending
        if not p or not p.polys:
            self.pendingChanged.emit(False); self._draw(); return
        kind, v, u = self.cur.session.measure(p.geom)
        name = p.layer[:-1] if p.layer.endswith("s") else p.layer
        self.pend_title.setText(f"{name} · {v:,.1f} {u}" if kind != "point" else name)
        if p.surface is not None and "width_m" in p.attrs:
            wu = "m" if self.cur.src.metric else "px"
            self.pend_title.setText(f"{name} · {v:,.0f} {u} long · {p.attrs['width_m']:.1f} {wu} wide")
        bits = []
        if p.scores:
            bits.append(f"confidence {p.scores[p.idx]:.3f}")
        if len(p.polys) > 1:
            bits.append(f"size {p.idx + 1} of {len(p.polys)} (Tab)")
        if self.review:
            bits.append(f"{len(self.review)} more to review")
        verts = len(p.geom.exterior.coords) - 1 if p.geom.geom_type == "Polygon" else len(p.geom.coords)
        bits.insert(0, f"{verts} vertices")
        self.pend_info.setText(" · ".join(bits))
        self.all_btn.setVisible(bool(self.review))
        self._waiting(True)
        self.pendingChanged.emit(True)
        self._draw()

    def cycle(self):
        if self.pending and len(self.pending.polys) > 1:
            self.pending.idx = (self.pending.idx + 1) % len(self.pending.polys)
            self._show_pending()

    def _enter(self):
        if self.map.tool in PAINT_TOOLS and not self.pending and not self.review:
            self.find_roads(); return
        if self.map.tool == "line" and self.line_clicks and not self.pending:
            self._finish_line()
        else:
            self.accept()

    def accept(self):
        p = self.pending
        if not p or not p.polys:
            return
        self.cur.session.add(p.layer, Feature(p.geom, p.method, p.scores[p.idx] if p.scores else 1.0, attrs=dict(p.attrs)))
        if p.surface is not None:
            L = self.cur.session.layers[p.layer]
            sname = f"{p.layer} surface"
            self.cur.session.layer(sname, "polygon", L.color)
            self.cur.session.add(sname, Feature(p.surface, p.method, p.scores[p.idx] if p.scores else 1.0, attrs=dict(p.attrs)))
            self._spawn("keep", p.surface, QColor(L.color))
        self._celebrate(p.layer, p.geom)
        self.stat.emit("features", 1)
        if p.method == "similar":
            self.stat.emit("similar_kept", 1)
        self._after_feature(p.layer)
        self.pending = None
        self._next_review() if self.review else self._settle()

    def reject(self):
        if self.line_clicks and not self.pending:
            self.line_clicks.clear(); self.line_preview = None; self._draw(); return
        if self.pending:
            self._spawn("drop", self.pending.geom); self.sound.emit("drop")
            self.combo = 0; self._place_chip()
        self.pending = None
        self._next_review() if self.review else self._settle()

    def accept_all(self):
        if self.pending:
            self.accept()
        n = 0
        while self.pending:
            self.accept(); n += 1
        self.toast.emit("Kept every one found")

    def _drop_pending(self, silent=False):
        self.pending = None; self.review.clear()
        if not silent:
            self._settle()

    def _waiting(self, on):
        for b in (self.keep_btn, self.drop_btn, self.cycle_btn):
            b.setEnabled(on)

    def _settle(self):
        self.all_btn.setVisible(False)
        self._waiting(False)
        self.pend_title.setText("Nothing waiting"); self.pend_info.setText("Click the map for the next one.")
        self.pendingChanged.emit(False)
        self._refresh_all()

    def _after_feature(self, layer):
        L = self.cur.session.layers.get(layer)
        if layer == "Trees":
            self.stat.emit("trees", 1)
        if L and L.kind == "line" and self.cur.src.metric and L.features:
            self.stat.emit("road_m", self.cur.session.measure(L.features[-1].geom)[1])

    # ============================================================ lines
    def _update_line_preview(self):
        clicks = list(self.line_clicks)
        if len(clicks) < 2 or not self.snap_cb.isChecked():
            from shapely.geometry import LineString
            self.line_preview = LineString(clicks) if len(clicks) >= 2 else None
            self._draw(); return
        img, gsd = self.cur.src.image, self.cur.src.gsd
        self.st_model.setText("Snapping…")
        self._run("line", lambda: (clicks, SH.snap_line(img, clicks, gsd)))

    def _backspace(self):
        if self.map.tool in PAINT_TOOLS and self.cur and self.cur.strokes:
            self.cur.strokes.pop(); self._relearn(); self._draw(); return
        if self.line_clicks:
            self.line_clicks.pop(); self._update_line_preview()

    def _finish_line(self):
        from shapely.geometry import LineString
        clicks = list(self.line_clicks); self.line_clicks.clear()
        if len(clicks) < 2:
            self.line_preview = None; self._draw(); return
        g = self.line_preview if (self.line_preview is not None and self.snap_cb.isChecked()) else LineString(clicks)
        self.line_preview = None
        layer = self.active_layer if self.cur.session.layers[self.active_layer].kind == "line" else "Roads"
        self.pending = Pending(layer, [g], [1.0], "line")
        self.accept()

    # ============================================================ find similar / text
    def find_similar(self):
        if not self.cur or self._job:
            return
        L = self.cur.session.layers.get(self.active_layer)
        ex = [f.geom for f in (L.features if L else []) if f.geom.geom_type == "Polygon" and f.method in ("click", "box", "similar")]
        if not ex:
            self.toast.emit(f"Keep one or more {self.active_layer.lower()} first, then Find similar"); return
        if not self._need_model():
            return
        if self.pending:
            self.accept()
        scope = ["all", "here", "files"][self.scope.currentIndex()]
        strict = self.strict.value() / 100
        targets = self.files if scope == "files" else [self.cur]
        from .extract import similar, sam
        examples = ex[-8:]
        layer = self.active_layer
        def job():
            out = []
            proto = similar.prototype(self.cur.seg, examples)
            for fs in targets:
                if fs.seg is None:
                    fs.seg = sam.Segmenter(fs.src.image, fs.src.gsd)
                taken = [f.geom for Lr in fs.session.layers.values() for f in Lr.features if f.geom.geom_type == "Polygon"]
                # other open files are searched with this file's examples
                cands = similar.find_similar(fs.seg, examples, existing=taken if fs is self.cur else taken,
                                             scope="here" if scope == "here" else "all", strictness=strict,
                                             proto=None if fs is self.cur else proto,
                                             progress=lambda a, b: self.bridge.progress.emit(a, b))
                out.append((fs, cands))
            return layer, out
        self._start_scan()
        self.st_model.setText("Looking for similar ones…")
        self._run("similar", job)

    def read_text(self):
        if not self.cur or self._job:
            return
        from .extract import labels
        src = self.cur.src
        self.st_model.setText("Reading map text…")
        self._run("text", lambda: labels.read_labels(src, progress=lambda a, b: self.bridge.progress.emit(a, b)))

    def _next_review(self):
        if not self.review:
            self._settle(); return
        fs, c = self.review.pop(0)
        if fs is not self.cur:
            self.file_list.blockSignals(True); self.file_list.setCurrentRow(self.files.index(fs)); self.file_list.blockSignals(False)
            self.cur = fs; self.map.set_image(fs.qimg)
        if getattr(c, "surface", None) is not None:
            self.pending = Pending(self._review_layer, [c.poly], [c.score], "brush", surface=c.surface,
                                   attrs={"width_m": round(c.width, 2)})
        else:
            self.pending = Pending(self._review_layer, [c.poly], [c.score], "similar")
        b = c.poly.bounds
        if getattr(c, "surface", None) is not None:        # roads: show the whole piece with room around it
            g = fs.src.gsd or 0.05
            r = QRectF(b[0], b[1], b[2] - b[0], b[3] - b[1])
            m = max(20 / g, 0.25 * max(r.width(), r.height()))
            self.map.fitInView(r.adjusted(-m, -m, m, m), Qt.KeepAspectRatio)
        else:
            self.map.zoom_to(QRectF(b[0], b[1], b[2] - b[0], b[3] - b[1]), pad=4)
        self._show_pending()

    # ============================================================ background jobs
    def _run(self, tag, fn):
        if self._job:
            self._queued = (tag, fn); return
        self._job = tag
        def work():
            try:
                self.bridge.done.emit(tag, fn())
            except Exception:
                self.bridge.failed.emit(tag, traceback.format_exc())
        threading.Thread(target=work, daemon=True).start()

    def _job_progress(self, a, b):
        self.st_model.setText(f"Working… {a}/{b}")

    def _job_done(self, tag, res):
        self._job = None
        if tag == "open":
            self._add_sources(res); self.st_model.setText("Model: ready")
        elif tag == "predict":
            self._stop_think()
            layer, prompts, r, method, dt = res
            self.st_model.setText(f"Model: {dt:.1f} s")
            if not len(r.masks):
                self.toast.emit("Nothing found there. Try a box.")
            else:
                pend = self.pending if (self.pending and prompts is self.pending.prompts) else Pending(layer, [], [], method, prompts)
                pend.result = r; pend.idx = 0
                self.pending = pend
                self._polys_from_result(pend)
                if not pend.polys:
                    self.pending = None; self.toast.emit("Too small to outline. Zoom in or use a box.")
                else:
                    self._spawn("appear", pend.geom); self.sound.emit("tick")
                self._show_pending()
        elif tag == "line":
            clicks, line = res
            if clicks == self.line_clicks:
                self.line_preview = line
            self.st_model.setText("Model: ready"); self._draw()
        elif tag == "similar":
            self._stop_scan()
            layer, out = res
            self._review_layer = layer
            self.review = [(fs, c) for fs, cands in out for c in cands]
            n = len(self.review)
            self.st_model.setText("Model: ready")
            if n:
                self.sound.emit("found")
                self.toast.emit(f"Found {n} that look alike. Enter keeps, Esc drops")
                self._next_review()
            else:
                self.toast.emit("No look-alikes found. Try Looser.")
        elif tag == "learn":
            self._stop_think(); self.st_model.setText("Model: ready"); self._draw_heat()
        elif tag == "roads":
            self._stop_scan()
            layer, fs, segs = res
            self._review_layer = layer
            self.review = self._road_review(layer, fs, segs)
            self.st_model.setText("Model: ready")
            if self.review:
                tot = sum(c.poly.length for _f, c in self.review) * (fs.src.gsd or 1)
                unit = "m" if fs.src.metric else "px"
                self.sound.emit("found")
                self.toast.emit(f"Traced {len(self.review)} road pieces, {tot:,.0f} {unit}. Enter keeps, Esc drops")
                self._next_review()
            else:
                self.toast.emit("No new roads found. Paint a few more strokes, or paint what isn't road red.")
            self._draw()
        elif tag == "text":
            from shapely.geometry import Point
            L = self.cur.session.layers.get("Landmarks")
            items = [Feature(Point(x, y), "label", c, t) for t, x, y, c in res]
            if items:
                self.cur.session.add("Landmarks", items)
                self.toast.emit(f"Read {len(items)} labels into Landmarks")
            else:
                self.toast.emit("No text found (or the OCR engine isn't installed)")
            self.st_model.setText("Model: ready"); self._refresh_all()
        if self._queued:
            q, self._queued = self._queued, None
            self._run(*q)

    def _job_failed(self, tag, tb):
        self._job = None; self._stop_scan(); self._stop_think()
        self.st_model.setText("Something went wrong")
        QMessageBox.warning(self, "C.H.A.M.B.E.R", f"That didn't work ({tag}).\n\n{tb.strip().splitlines()[-1]}")
        if self._queued:
            q, self._queued = self._queued, None
            self._run(*q)

    # ============================================================ scan effect
    def _start_scan(self):
        self._scan = 0.0; self._scan_t.start(30)

    def _stop_scan(self):
        self._scan_t.stop(); self._scan = None
        it = getattr(self, "_scan_item", None)
        if it is not None and it.scene() is self.map.scene():
            self.map.scene().removeItem(it)
        self._scan_item = None
        self._draw()

    def _scan_step(self):
        self._scan = (self._scan + 0.012) % 1.0
        self._draw_scan()

    # ============================================================ drawing
    def _march(self):
        if self.pending or self.line_clicks:
            self._ants = (self._ants + 1) % 16
            for it in getattr(self, "_pend_items", []):
                pn = it.pen(); pn.setDashOffset(self._ants); it.setPen(pn)

    def _refresh_all(self):
        self._refresh_layers(); self._draw()
        self.act_btn["undo"].setEnabled(bool(self.cur and self.cur.session.undo_stack))
        self.act_btn["redo"].setEnabled(bool(self.cur and self.cur.session.redo_stack))
        if not self.pending and not self.selected:
            self.pendingChanged.emit(False)

    def _draw(self):
        sc = self.map.scene()
        for it in getattr(self, "_items", []):
            if it.scene() is sc:
                sc.removeItem(it)
        self._items, self._pend_items = [], []
        if not self.cur or self.map.pix is None:
            return
        t = TH()
        def add(it, z):
            it.setZValue(z); sc.addItem(it); self._items.append(it); return it
        # features
        for L in self.cur.session.layers.values():
            if not L.visible or not L.features:
                continue
            c = QColor(L.color)
            for f in L.features:
                sel = self.selected is not None and self.selected[1] is f
                if f.geom.geom_type == "Point":
                    e = QGraphicsEllipseItem(-5, -5, 10, 10); e.setPos(f.geom.x, f.geom.y)
                    e.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                    e.setBrush(c); e.setPen(pen("#111827", 1.5)); add(e, 20)
                    if f.text:
                        from PySide6.QtWidgets import QGraphicsSimpleTextItem
                        tx = QGraphicsSimpleTextItem(f.text); tx.setPos(f.geom.x, f.geom.y)
                        tx.setFlag(QGraphicsItem.ItemIgnoresTransformations); tx.setBrush(QColor("#ffffff"))
                        tx.setPen(pen("#111827", 0.6)); add(tx, 21)
                    continue
                it = QGraphicsPathItem(geom_path(f.geom))
                it.setPen(pen(c, 4.5 if sel else 2.6))
                if f.geom.geom_type == "Polygon":
                    fc = QColor(c); fc.setAlpha(110 if sel else 46); it.setBrush(fc)
                add(it, 10)
        # drawn PDF style preview
        if self.picked_style is not None:
            col = QColor(t.accent)
            for kind, pts in self.picked_style.paths:
                path = QPainterPath(QPointF(*pts[0]))
                for x, y in pts[1:]:
                    path.lineTo(QPointF(x, y))
                it = QGraphicsPathItem(path); it.setPen(pen(col, 5, alpha=220)); add(it, 15)
        # review candidates (faint)
        for fs, c in self.review:
            if fs is self.cur:
                it = QGraphicsPathItem(geom_path(c.poly)); it.setPen(pen(t.accent, 1.6, Qt.DashLine, 170)); add(it, 12)
        # brush strokes
        for s in (self.cur.strokes if self.map.tool in PAINT_TOOLS and not self.review else []):
            col = QColor("#38bdf8" if s.kind == "road" else "#ef4444"); col.setAlpha(70)
            path = QPainterPath(QPointF(*s.pts[0]))
            for x, y in s.pts[1:]:
                path.lineTo(QPointF(x, y))
            if len(s.pts) == 1:
                path.lineTo(QPointF(s.pts[0][0] + 0.01, s.pts[0][1]))
            it = QGraphicsPathItem(path); it.setPen(QPen(col, 2 * s.radius_px, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); add(it, 8)
            if s.closed():
                poly = QPainterPath(QPointF(*s.pts[0]))
                for x, y in s.pts[1:]:
                    poly.lineTo(QPointF(x, y))
                poly.closeSubpath()
                f = QGraphicsPathItem(poly); f.setPen(QPen(Qt.NoPen)); f.setBrush(col); add(f, 8)
        # pending
        if self.pending and self.pending.surface is not None:
            sf = QGraphicsPathItem(geom_path(self.pending.surface))
            fc = QColor(t.accent); fc.setAlpha(55); sf.setBrush(fc); sf.setPen(pen(t.accent, 1.5, Qt.DashLine)); add(sf, 29)
        if self.pending and self.pending.polys:
            g = self.pending.geom
            glowc = QColor(t.accent)
            for w, a in ((9, 60), (5, 110)):
                it = QGraphicsPathItem(geom_path(g)); it.setPen(pen(glowc, w, alpha=a)); add(it, 30)
            it = QGraphicsPathItem(geom_path(g)); it.setPen(pen("#ffffff", 2.2, Qt.DashLine))
            if g.geom_type == "Polygon":
                fc = QColor(t.accent); fc.setAlpha(60); it.setBrush(fc)
            add(it, 31); self._pend_items.append(it)
            for (x, y), l in zip(self.pending.prompts["points"], self.pending.prompts["labels"]):
                self._dot(x, y, "#ffffff" if l else "#ef4444", add)
            b = self.pending.prompts.get("box")
            if b:
                r = QGraphicsRectItem(QRectF(QPointF(b[0], b[1]), QPointF(b[2], b[3])))
                r.setPen(pen(t.accent, 1.5, Qt.DashLine)); add(r, 29)
        # line in progress
        if self.line_clicks:
            if self.line_preview is not None:
                it = QGraphicsPathItem(geom_path(self.line_preview)); it.setPen(pen(t.accent, 3.2, Qt.DashLine)); add(it, 30)
                self._pend_items.append(it)
            for x, y in self.line_clicks:
                self._dot(x, y, "#ffffff", add)
        if self._scan is not None:
            self._draw_scan()
        self._draw_heat()

    def _dot(self, x, y, color, add):
        e = QGraphicsEllipseItem(-6, -6, 12, 12); e.setPos(x, y)
        e.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        e.setBrush(QColor(color)); e.setPen(pen("#111827", 2)); add(e, 40)

    def _draw_scan(self):
        """The 'scanner' sweep while Find similar is looking."""
        if self._scan is None or not self.cur:
            return
        sc = self.map.scene()
        it = getattr(self, "_scan_item", None)
        if it is not None and it.scene() is sc:
            sc.removeItem(it)
        h, w = self.cur.src.image.shape[:2]
        x = self._scan * w
        band = max(w * 0.06, 20)
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(x - band, 0, x, 0)
        c0 = QColor(TH().accent); c0.setAlpha(0); c1 = QColor(TH().accent); c1.setAlpha(110)
        g.setColorAt(0, c0); g.setColorAt(1, c1)
        r = QGraphicsRectItem(x - band, 0, band, h); r.setBrush(QBrush(g)); r.setPen(QPen(Qt.NoPen)); r.setZValue(60)
        sc.addItem(r); self._scan_item = r

    # ============================================================ Road Brush / Paint the Map Red
    def _px_per_m(self):
        g = self.cur.src.gsd if self.cur else None
        return (1 / g) if g else None

    def _update_brush(self):
        ppm = self._px_per_m()
        self.map.brush_px = self.brush_m * ppm if ppm else self.brush_m * 10
        if self.map.tool in PAINT_TOOLS:
            size = f"{2 * self.brush_m:.1f} m" if ppm else f"{2 * self.brush_m * 10:.0f} px"
            self.st_coord.setText(f"Brush {size} wide  ·  [ ] or Ctrl+wheel")

    def _brush_step(self, d):
        self.brush_m = float(np.clip(self.brush_m * (1.15 if d > 0 else 1 / 1.15), 0.3, 60))
        self.settings.setValue("brush_m", self.brush_m)
        self._update_brush()

    def _width_mode_changed(self, i):
        L = self.cur and self.cur.session.layers.get(self.active_layer)
        if L is not None:
            L.width_mode = "fixed" if i == 1 else "measured"

    def _on_painted(self, pts):
        if not self.cur:
            return
        from .extract.roads import Stroke
        kind = "road" if self.map.tool == "brush" else "red"
        s = Stroke(kind, [(float(x), float(y)) for x, y in pts], self.map.brush_px)
        self.cur.strokes.append(s)
        L = self.cur.session.layers.get(self.active_layer)
        if L is None or L.kind != "line":
            self.active_layer = "Roads"; self._refresh_layers()
        self.sound.emit("tick")
        if s.closed():
            self.toast.emit("Painted the map red: everything inside is 'not road'")
            self.stat.emit("red_loop", 1)
        self._draw()
        self._relearn()

    def _relearn(self):
        if not self.cur:
            return
        fs = self.cur
        if not any(s.kind == "road" for s in fs.strokes):
            if fs.roads is not None:
                fs.roads.prob = None
            self._draw_heat(); return
        first = fs.roads is None or fs.roads.feat is None
        if first:
            h, w = fs.src.image.shape[:2]
            self._start_think(QRectF(0, 0, w, h)); self.st_model.setText("Learning what roads look like…")
        strokes = list(fs.strokes)
        def job():
            from .extract.roads import RoadLearner
            if fs.roads is None:
                fs.roads = RoadLearner(fs.src.image, fs.src.gsd, progress=lambda a, b: self.bridge.progress.emit(a, b))
            fs.roads.learn(strokes)
            return fs
        self._run("learn", job)

    def find_roads(self):
        if not self.cur or self._job:
            return
        if not any(s.kind == "road" for s in self.cur.strokes):
            self.toast.emit("Paint along a road first (Road Brush, R)"); return
        fs = self.cur
        strokes = list(fs.strokes)
        scope = "grow" if self.road_scope.currentIndex() == 0 else "whole"
        strict = (self.strict.value() - 70) / 25            # the Looser / Stricter slider
        layer = self.active_layer if fs.session.layers.get(self.active_layer) and fs.session.layers[self.active_layer].kind == "line" else "Roads"
        self.st_model.setText("Tracing roads…")
        self._start_scan()
        def job():
            from .extract.roads import RoadLearner
            if fs.roads is None:
                fs.roads = RoadLearner(fs.src.image, fs.src.gsd)
            fs.roads.learn(strokes)
            return layer, fs, fs.roads.extract(strokes, scope, strict=strict)
        self._run("roads", job)

    def clear_paint(self):
        if self.cur and self.cur.strokes:
            self.cur.strokes.clear()
            if self.cur.roads is not None:
                self.cur.roads.prob = None
            self._draw()

    def _road_review(self, layer, fs, segs):
        from types import SimpleNamespace
        L = fs.session.layers[layer]
        fixed = getattr(L, "width_mode", "measured") == "fixed"
        have = [f.geom for f in L.features]
        items = []
        g = fs.src.gsd or 1.0
        # longest first; a piece shorter than the road is wide is just a junction blob
        segs = sorted(segs, key=lambda s: -s.line.length)
        segs = [s for s in segs if s.painted or s.line.length * g >= max(4.0, 0.7 * s.width_m)]
        for sg in segs:
            line = sg.line
            if have:
                from shapely.ops import unary_union
                cover = unary_union(have).buffer(max(sg.width_m / (fs.src.gsd or 1) / 2, 4))
                if line.difference(cover).length < 0.2 * line.length:
                    continue                              # already kept
            if fixed:
                r = self.map.brush_px
                surface, width = line.buffer(r, cap_style=2, join_style=1), 2 * self.brush_m
            else:
                surface, width = sg.surface, sg.width_m
            items.append((fs, SimpleNamespace(poly=line, score=sg.score, surface=surface, width=width)))
        return items

    def _draw_heat(self):
        sc = self.map.scene()
        if self._heat is not None and self._heat.scene() is sc:
            sc.removeItem(self._heat)
        self._heat = None
        fs = self.cur
        if not fs or fs.roads is None or fs.roads.prob is None or not self.heat_cb.isChecked() or self.map.pix is None:
            return
        if self.map.tool not in PAINT_TOOLS or self.review:
            return
        p = fs.roads.prob
        c = QColor(TH().accent if TH().key != "atlas" else "#0ea5e9")
        rgba = np.zeros(p.shape + (4,), np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = c.red(), c.green(), c.blue()
        rgba[..., 3] = (np.clip((p - 0.3) / 0.5, 0, 1) * 150).astype(np.uint8)
        qi = QImage(np.ascontiguousarray(rgba).data, p.shape[1], p.shape[0], 4 * p.shape[1], QImage.Format_RGBA8888).copy()
        it = QGraphicsPixmapItem(QPixmap.fromImage(qi)); it.setTransformationMode(Qt.SmoothTransformation)
        it.setScale(1 / fs.roads.f); it.setZValue(5); sc.addItem(it)
        self._heat = it

    # ============================================================ feedback & effects
    def _celebrate(self, layer, geom):
        """Keep: a ring pulses out of the feature, the layer row flashes, the
        combo counts up and the keep sound climbs a note per combo step."""
        now = time.time()
        self.combo = self.combo + 1 if now - self._combo_t < 20 else 1
        self._combo_t = now
        L = self.cur.session.layers.get(layer)
        self._spawn("keep", geom, QColor(L.color if L else TH().accent))
        self._flash = (layer, now)
        QTimer.singleShot(720, self._refresh_layers)
        self.sound.emit(f"keep{min(self.combo - 1, 9)}")
        if self.combo >= 5 and self.combo % 5 == 0:
            self.sound.emit("combo")
        self._place_chip()

    def _place_chip(self):
        c = self.combo_chip
        if self.combo < 3 or not self.cur:
            c.hide(); return
        t = TH()
        hot = self.combo >= 10
        bg = t.accent2 if hot else t.accent
        c.setStyleSheet(f"QLabel {{ background: {bg}; color: {t.on_accent if not t.dark or not hot else '#0B0D18'};"
                        f" border-radius: 14px; padding: 5px 14px; font-weight: 800; font-size: 11pt; }}")
        c.setText(f"{'🔥 ' if hot else ''}Combo ×{self.combo}")
        c.adjustSize()
        top = 14 if self.layout_mode == "cols" else 74
        c.move((self.map.width() - c.width()) // 2, top); c.show(); c.raise_()
        self._chip_t = time.time()
        QTimer.singleShot(4000, self._fade_chip)

    def _fade_chip(self):
        if time.time() - getattr(self, "_chip_t", 0) >= 3.9:
            self.combo_chip.hide()

    def _spawn(self, kind, geom, color=None):
        if geom is None or self.map.pix is None:
            return
        sc = self.map.scene()
        if geom.geom_type == "Point":
            from shapely.geometry import Point as _P
            geom = geom.buffer(6 / max(self.map.transform().m11(), 1e-6))
        it = QGraphicsPathItem(geom_path(geom)); it.setZValue(45)
        it.setTransformOriginPoint(QPointF(geom.centroid.x, geom.centroid.y))
        sc.addItem(it)
        self._fx.append([kind, it, time.time(), QColor(color or TH().accent)])
        if not self._fx_timer.isActive():
            self._fx_timer.start(16)

    def _fx_step(self):
        now = time.time(); sc = self.map.scene(); alive = []
        for kind, it, t0, col in self._fx:
            dur = {"keep": 0.55, "drop": 0.35, "appear": 0.35}[kind]
            u = (now - t0) / dur
            if u >= 1 or it.scene() is not sc:
                if it.scene() is sc:
                    sc.removeItem(it)
                continue
            ease = 1 - (1 - u) ** 3
            c = QColor(col)
            if kind == "keep":                     # a ring that grows and fades
                c.setAlpha(int(230 * (1 - u)))
                it.setPen(pen(c, 2 + 7 * (1 - u))); it.setScale(1 + 0.18 * ease)
                f = QColor(col); f.setAlpha(int(120 * (1 - u))); it.setBrush(f)
            elif kind == "drop":                   # shrinks away in red
                c = QColor("#ef4444"); c.setAlpha(int(200 * (1 - u)))
                it.setPen(pen(c, 2.5, Qt.DashLine)); it.setScale(1 - 0.25 * ease)
            else:                                  # appear: a bright flash on the new outline
                c = QColor("#ffffff"); c.setAlpha(int(255 * (1 - u)))
                it.setPen(pen(c, 3 + 5 * (1 - u)))
            alive.append([kind, it, t0, col])
        self._fx = alive
        if not alive and self._think is None:
            self._fx_timer.stop()

    def _start_think(self, rect):
        """While the model reads a new area: a sweeping scan line and grid over it."""
        self._stop_think()
        sc = self.map.scene()
        frame = QGraphicsRectItem(rect); frame.setPen(pen(TH().accent, 1.5, Qt.DashLine)); frame.setZValue(55)
        c = QColor(TH().accent); c.setAlpha(28); frame.setBrush(c)
        line = QGraphicsRectItem(QRectF(rect.left(), rect.top(), rect.width(), max(rect.height() * 0.02, 2)))
        lc = QColor(TH().accent); lc.setAlpha(150); line.setBrush(lc); line.setPen(QPen(Qt.NoPen)); line.setZValue(56)
        sc.addItem(frame); sc.addItem(line)
        self._think = (frame, line, rect, time.time())
        if getattr(self, "_think_timer", None) is None:
            self._think_timer = QTimer(self); self._think_timer.timeout.connect(self._think_step)
        self._think_timer.start(30)

    def _think_step(self):
        if not self._think:
            return
        frame, line, rect, t0 = self._think
        u = ((time.time() - t0) / 0.9) % 1.0
        line.setRect(QRectF(rect.left(), rect.top() + u * rect.height(), rect.width(), max(rect.height() * 0.02, 2)))
        a = int(20 + 18 * abs(np.sin((time.time() - t0) * 3)))
        c = QColor(TH().accent); c.setAlpha(a); frame.setBrush(c)

    def _stop_think(self):
        if getattr(self, "_think_timer", None):
            self._think_timer.stop()
        if self._think:
            sc = self.map.scene()
            for it in self._think[:2]:
                if it.scene() is sc:
                    sc.removeItem(it)
        self._think = None

    # ============================================================ undo / export
    def undo(self):
        if self.cur and self.cur.session.undo():
            self.selected = None; self._refresh_all()

    def redo(self):
        if self.cur and self.cur.session.redo():
            self._refresh_all()

    def export(self):
        if not self.files:
            return
        if self.pending:
            self.accept()
        d = ExportDialog(self, self.settings, len(self.files))
        if d.exec() != QDialog.Accepted:
            return
        fmts, folder, all_files = d.values()
        targets = self.files if all_files else [self.cur]
        written, notes = [], []
        for fs in targets:
            out = Path(folder) if folder else Path(fs.src.path).parent / f"{Path(fs.src.path).stem}_extract"
            if fs.session.count() == 0:
                continue
            w, n = fs.session.export(out, fmts)
            written += w; notes += [f"{fs.src.name}: {x}" for x in n]
        self.stat.emit("formats:" + ",".join(fmts), 1)
        msg = f"Wrote {len(written)} file(s)" + (f" to {written[0].parent}" if written else "")
        if notes:
            msg += "\n\n" + "\n".join(notes[:8])
        QMessageBox.information(self, "C.H.A.M.B.E.R", msg)
        if written:
            try:
                os.startfile(str(written[0].parent))
            except Exception:
                pass

    # ============================================================ for the app
    def has_pending(self):
        return bool(self.pending or self.review or self.line_clicks)


def icon_from_pixmap(pm):
    from PySide6.QtGui import QIcon
    return QIcon(pm)


class ExportDialog(QDialog):
    FORMATS = [("gpkg", "GeoPackage (all layers in one file)", True), ("shp", "Shapefile", False),
               ("geojson", "GeoJSON", False), ("kml", "KML (Google Earth)", False), ("dxf", "DXF (CAD)", False)]

    def __init__(self, parent, settings, n_files):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Export"); self.setMinimumWidth(420)
        self.setStyleSheet(TM.qss())
        lay = QVBoxLayout(self); lay.setSpacing(8)
        t = QLabel("FORMATS"); t.setObjectName("cardTitle"); lay.addWidget(t)
        self.cb = {}
        for k, name, d in self.FORMATS:
            c = QCheckBox(name); c.setChecked(settings.value(f"x_fmt_{k}", d, type=bool)); lay.addWidget(c); self.cb[k] = c
        t = QLabel("WHERE"); t.setObjectName("cardTitle"); lay.addWidget(t)
        row = QHBoxLayout()
        self.folder = QLineEdit(settings.value("x_folder", "", type=str))
        self.folder.setPlaceholderText("Next to each file, in <name>_extract")
        b = QPushButton("Browse…"); b.clicked.connect(self._browse)
        row.addWidget(self.folder, 1); row.addWidget(b); lay.addLayout(row)
        self.all = QCheckBox(f"All {n_files} open files"); self.all.setChecked(n_files > 1); self.all.setVisible(n_files > 1)
        lay.addWidget(self.all)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Export"); bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Export to", self.folder.text())
        if d:
            self.folder.setText(d)

    def values(self):
        fm = [k for k, c in self.cb.items() if c.isChecked()] or ["gpkg"]
        for k, c in self.cb.items():
            self.settings.setValue(f"x_fmt_{k}", c.isChecked())
        self.settings.setValue("x_folder", self.folder.text())
        return fm, self.folder.text().strip(), self.all.isChecked()
