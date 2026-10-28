"""The desktop app (Qt / PySide6): glass panels, neon highlights, an animated stage.

Tabs: Run (folders, the animation stage, progress, log), Settings (every option)
and Badges. The work runs on a background thread and talks back to the window
through Qt signals, so the window never freezes.

Glass: on Windows the window asks for the system blur behind it (see winglass.py).
If that isn't available (older Windows, other OS, or switched off in Settings) the
window paints its own dark gradient instead, so it always works.
"""
from __future__ import annotations
import json, os, random, sys, threading, time, traceback
from pathlib import Path

from PySide6.QtCore import (Qt, QObject, Signal, QTimer, QSettings, QRectF, QPointF, QSize,
                            QPropertyAnimation, QEasingCurve, Property)
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QLinearGradient, QRadialGradient,
                           QPixmap, QMovie, QImageReader, QIcon, QFont, QFontMetricsF, QPen, QBrush, QTextCursor)
from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow, QFrame, QLabel, QPushButton,
                               QLineEdit, QComboBox, QSpinBox, QCheckBox, QPlainTextEdit,
                               QHBoxLayout, QVBoxLayout, QGridLayout, QStackedWidget,
                               QButtonGroup, QFileDialog, QMessageBox, QDialog,
                               QGraphicsDropShadowEffect, QSizePolicy)

from . import __version__
from .batch import run_batch
from . import achievements as A

APP = "C.H.A.M.B.E.R"
CYAN = QColor(0, 229, 255)
MAGENTA = QColor(255, 61, 154)
TEXT = "#E8ECFF"
MUTED = "#9AA3C7"
DEBUG_CHOICES = [("Only for flagged sheets", "flagged"), ("All sheets", "all"), ("None", "none")]
CRS_CHOICES = ["Auto (UTM zone per sheet)", "EPSG:4326 (lat/lon)", "EPSG:3857 (Web Mercator)", "Custom…"]


def _resource(rel):
    """Locate a bundled asset whether running from source or a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", rel))


QSS = f"""
* {{ color: {TEXT}; font-family: 'Segoe UI Variable', 'Segoe UI', 'Noto Sans', sans-serif; font-size: 10pt; }}
QLabel#title {{ font-size: 17pt; font-weight: 700; letter-spacing: 3px; }}
QLabel#subtitle, QLabel#muted {{ color: {MUTED}; }}
QLabel#cardTitle {{ color: {MUTED}; font-size: 8.5pt; font-weight: 700; letter-spacing: 2px; }}
QLabel#status {{ color: {TEXT}; font-size: 9.5pt; }}
QFrame#card {{ background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,34); border-radius: 16px; }}
QFrame#tabbar {{ background: rgba(0,0,0,60); border: 1px solid rgba(255,255,255,30); border-radius: 18px; }}
QPushButton {{ background: rgba(255,255,255,20); border: 1px solid rgba(255,255,255,50);
              border-radius: 11px; padding: 7px 16px; }}
QPushButton:hover {{ border: 1px solid rgb(0,229,255); background: rgba(0,229,255,26); }}
QPushButton:pressed {{ background: rgba(0,229,255,50); }}
QPushButton:disabled {{ color: rgba(232,236,255,90); border: 1px solid rgba(255,255,255,22); background: rgba(255,255,255,8); }}
QPushButton#tab {{ background: transparent; border: 1px solid transparent; border-radius: 14px; padding: 6px 18px; color: {MUTED}; font-weight: 600; }}
QPushButton#tab:hover {{ color: {TEXT}; border: 1px solid rgba(0,229,255,90); }}
QPushButton#tab:checked {{ color: rgb(0,229,255); border: 1px solid rgb(0,229,255); background: rgba(0,229,255,30); }}
QPushButton#run {{ font-weight: 700; font-size: 11pt; padding: 9px 30px; color: #0B0D18; border: none;
                  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgb(0,229,255), stop:1 rgb(255,61,154)); }}
QPushButton#run:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgb(120,245,255), stop:1 rgb(255,120,190)); }}
QPushButton#run:disabled {{ color: rgba(11,13,24,140); background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(0,229,255,90), stop:1 rgba(255,61,154,90)); }}
QLineEdit, QComboBox, QSpinBox {{ background: rgba(0,0,0,70); border: 1px solid rgba(255,255,255,46);
              border-radius: 10px; padding: 6px 10px; selection-background-color: rgba(0,229,255,120); }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid rgb(0,229,255); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #151829; border: 1px solid rgba(0,229,255,120); selection-background-color: rgba(0,229,255,70); outline: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid rgba(255,255,255,90); background: rgba(0,0,0,60); }}
QCheckBox::indicator:hover {{ border: 1px solid rgb(0,229,255); }}
QCheckBox::indicator:checked {{ background: rgb(0,229,255); border: 1px solid rgb(0,229,255); }}
QPlainTextEdit {{ background: rgba(0,0,0,80); border: 1px solid rgba(255,255,255,30); border-radius: 12px;
                 padding: 6px; font-family: 'Cascadia Mono', Consolas, 'DejaVu Sans Mono', monospace; font-size: 9pt; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,60); border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: rgb(0,229,255); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QDialog {{ background: #12152A; }}
"""


def glow(widget, color=CYAN, radius=24, alpha=170):
    eff = QGraphicsDropShadowEffect(widget)
    c = QColor(color); c.setAlpha(alpha)
    eff.setColor(c); eff.setOffset(0, 0); eff.setBlurRadius(radius)
    widget.setGraphicsEffect(eff)
    return eff


def card(title=None):
    f = QFrame(); f.setObjectName("card")
    lay = QVBoxLayout(f); lay.setContentsMargins(16, 12, 16, 14); lay.setSpacing(8)
    if title:
        t = QLabel(title.upper()); t.setObjectName("cardTitle"); lay.addWidget(t)
    return f, lay


# ---------------- the animated stage ----------------
class ClipPlan:
    """Which clip plays next. Pure logic (no Qt), so it can be tested.

    The clips meet in two shared states, so any chain is seamless:
      hub      man holds the frisbee, dog ready        (start of every throw)
      arrived  dog sits in front of him, frisbee held  (end of every throw)
    throw: hub -> arrived    pet: arrived -> hub    finish: hub -> done
    While running: throw, pet, throw, pet ... (never the same throw twice in a
    row). When the run ends, the current clip plays out, then pet if needed,
    then finish, and the stage rests on its last frame."""

    def __init__(self, clips, rng=None):
        self.clips = clips
        self.rng = rng or random.Random()
        self.pos = "hub"
        self.last_throw = None

    def reset(self):
        self.pos = "hub"; self.last_throw = None

    def next(self, running, finishing):
        throws = self.clips.get("throws") or []
        if self.pos == "done":
            return None
        if running:
            if self.pos == "hub" and throws:
                pool = [t for t in throws if t != self.last_throw] or throws
                pick = self.rng.choice(pool)
                self.last_throw = pick; self.pos = "arrived"
                return pick
            if self.pos == "arrived" and self.clips.get("pet"):
                self.pos = "hub"
                return self.clips["pet"]
            return None
        if finishing:
            if self.pos == "arrived" and self.clips.get("pet"):
                self.pos = "hub"
                return self.clips["pet"]
            if self.pos == "hub" and self.clips.get("finish"):
                self.pos = "done"
                return self.clips["finish"]
        return None


class Stage(QWidget):
    """Plays the man-and-dog clips listed in assets/anim/clips.json:
      {"rest": "throw_m.webp", "throws": ["throw_s.webp", "throw_m.webp", "throw_l.webp"],
       "pet": "pet.webp", "finish": "finish.webp"}
    Missing clips are skipped; with none at all the stage shows the logo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._dir = Path(_resource("assets/anim"))
        self._clips = self._load_manifest()
        self.plan = ClipPlan(self._clips)
        self._movie = None
        self._pix = None
        self._running = False
        self._finishing = False
        self._logo = QPixmap(_resource("assets/logo_512.png"))
        self.show_rest()

    def _load_manifest(self):
        try:
            data = json.loads((self._dir / "clips.json").read_text(encoding="utf-8"))
        except Exception:
            return {}
        out = {}
        for k, v in data.items():
            if isinstance(v, list):
                out[k] = [str(self._dir / x) for x in v if (self._dir / x).exists()]
            elif (self._dir / v).exists():
                out[k] = str(self._dir / v)
        return out

    # --- public ---
    def start(self):
        """A run began. A new run starts from the hub (a clean cut if needed)."""
        self._running, self._finishing = True, False
        if self.plan.pos == "done" or self._movie is None:
            self.plan.reset()
            if self._movie is None:
                self._next()
        # if a clip is already playing, the chain simply continues from it

    def finish(self):
        """Run is over: let the current clip end, then wrap up."""
        self._running = False
        self._finishing = True
        if self._movie is None:
            self._next()

    def show_rest(self):
        """Idle: the first frame of the rest clip (man holding the frisbee)."""
        self._running = self._finishing = False
        self._stop_movie()
        self.plan.reset()
        first = self._clips.get("rest") or (self._clips.get("throws") or [None])[0]
        self._pix = None
        if first:
            img = QImageReader(first).read()       # first frame (WebP can't be jumped into)
            if not img.isNull():
                self._pix = QPixmap.fromImage(img)
        self.update()

    # --- internals ---
    def _stop_movie(self):
        if self._movie is not None:
            self._movie.stop()
            try:
                self._movie.frameChanged.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._movie.deleteLater()
            self._movie = None

    def _next(self):
        path = self.plan.next(self._running, self._finishing)
        self._stop_movie()
        if not path:
            self._finishing = False
            return                                   # rest on the last frame shown
        m = QMovie(path, parent=self)
        m.setCacheMode(QMovie.CacheNone)
        m.frameChanged.connect(lambda n, m=m: self._on_frame(m, n))
        self._movie = m
        m.start()

    def _on_frame(self, m, n):
        if m is not self._movie:
            return
        self._pix = m.currentPixmap()
        self.update()
        if n >= m.frameCount() - 1:                  # end of this clip
            m.setPaused(True)
            QTimer.singleShot(0, self._next)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.rect()
        if self._pix is not None and not self._pix.isNull():
            s = self._pix.size().scaled(r.size(), Qt.KeepAspectRatio)
            x = (r.width() - s.width()) / 2; y = (r.height() - s.height()) / 2
            p.drawPixmap(QRectF(x, y, s.width(), s.height()), self._pix, QRectF(self._pix.rect()))
        elif not self._logo.isNull():
            h = min(r.height() * 0.7, 120)
            p.setOpacity(0.35)
            p.drawPixmap(QRectF((r.width() - h) / 2, (r.height() - h) / 2, h, h), self._logo,
                         QRectF(self._logo.rect()))
        p.end()


# ---------------- the title: neon letters, click for the acronym ----------------
SUBTITLE = "Georeferenced PDF maps to GIS layers"
ACRONYM = "Cartographic Harvester for Automated Map Batch Export & Reprojection"
GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&@$<>/\\"


def acronym_initials(text, letters="CHAMBER"):
    """Indexes of the words' first letters that spell the name, in order."""
    out, want, i = [], list(letters), 0
    while i < len(text) and want:
        if (i == 0 or text[i - 1] == " ") and text[i].upper() == want[0]:
            out.append(i); want.pop(0)
        i += 1
    return out


class NeonTitle(QWidget):
    """C.H.A.M.B.E.R drawn letter by letter. Hover a letter: it lights up in
    neon. Click (or Enter): the title glitches and the subtitle decodes into
    what the name stands for; after a few seconds it glitches back."""

    GLITCH_IN, DECODE_IN, SHOW, GLITCH_OUT, DECODE_OUT = 0.40, 0.75, 6.0, 0.30, 0.50

    def __init__(self, title, subtitle, acronym, parent=None, clock=None):
        super().__init__(parent)
        self.title, self.subtitle, self.acronym = title, subtitle, acronym
        self.initials = set(acronym_initials(acronym))
        self.clock = clock or time.monotonic
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setToolTip(acronym)
        self.setAccessibleName(f"{title}: {acronym}")
        self.f_title = QFont(); self.f_title.setPointSizeF(17); self.f_title.setBold(True)
        self.f_sub = QFont(); self.f_sub.setPointSizeF(9.5)
        self.hover = None
        self.glow = [0.0] * len(title)
        self.rects = []
        self.mode = "sub"          # sub, glitch_in, decode_in, shown, glitch_out, decode_out
        self.t0 = 0.0
        self.rng = random.Random()
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick)
        self.setMinimumHeight(54)
        self.setMinimumWidth(520)

    # ---- input ----
    def mouseMoveEvent(self, e):
        pos = e.position() if hasattr(e, "position") else QPointF(e.pos())
        hit = next((i for i, r in enumerate(self.rects) if r.contains(pos) and self.title[i] != "."), None)
        if hit != self.hover:
            self.hover = hit
            self._wake()

    def leaveEvent(self, _):
        self.hover = None
        self._wake()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.trigger()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.trigger()
        else:
            super().keyPressEvent(e)

    def trigger(self):
        """Click: show the acronym, or (if it's showing) put the subtitle back."""
        if self.mode in ("sub", "decode_out", "glitch_out"):
            self._go("glitch_in")
        else:
            self._go("glitch_out")

    # ---- state machine ----
    def _go(self, mode):
        self.mode, self.t0 = mode, self.clock()
        self._wake()

    def _wake(self):
        if not self.timer.isActive():
            self.timer.start(16)
        self.update()

    def step(self):
        """Advance the animation (called by the timer; tests call it directly)."""
        dt = self.clock() - self.t0
        nxt = {"glitch_in": ("decode_in", self.GLITCH_IN), "decode_in": ("shown", self.DECODE_IN),
               "shown": ("glitch_out", self.SHOW), "glitch_out": ("decode_out", self.GLITCH_OUT),
               "decode_out": ("sub", self.DECODE_OUT)}.get(self.mode)
        if nxt and dt >= nxt[1]:
            self.mode, self.t0 = nxt[0], self.clock()
        busy = False
        for i in range(len(self.glow)):
            target = 1.0 if i == self.hover else 0.0
            g = self.glow[i] + (target - self.glow[i]) * 0.28
            self.glow[i] = target if abs(target - g) < 0.01 else g
            busy |= self.glow[i] != target
        return busy or self.mode != "sub"

    def _tick(self):
        if not self.step() and self.mode == "sub":
            self.timer.stop()
        self.update()

    # ---- drawing ----
    def _progress(self, total):
        return max(0.0, min(1.0, (self.clock() - self.t0) / total))

    def _sub_text(self):
        """The second line: subtitle, acronym, or a string decoding between them."""
        if self.mode in ("sub",):
            return self.subtitle, False
        if self.mode in ("glitch_in",):
            return self._scramble(self.subtitle, 0.25 + 0.5 * self._progress(self.GLITCH_IN)), False
        if self.mode == "decode_in":
            return self._decode(self.acronym, self._progress(self.DECODE_IN)), True
        if self.mode == "shown":
            return self.acronym, True
        if self.mode == "glitch_out":
            return self._scramble(self.acronym, 0.25 + 0.5 * self._progress(self.GLITCH_OUT)), True
        return self._decode(self.subtitle, self._progress(self.DECODE_OUT)), False

    def _scramble(self, s, amount):
        return "".join(c if c == " " or self.rng.random() > amount else self.rng.choice(GLYPHS) for c in s)

    def _decode(self, s, p):
        n = int(len(s) * p)
        return s[:n] + "".join(c if c == " " else self.rng.choice(GLYPHS) for c in s[n:])

    def _neon_char(self, p, x, base, ch, font, strength, core=QColor(TEXT)):
        path = QPainterPath(); path.addText(QPointF(x, base), font, ch)
        if strength > 0.01:
            for w, a in ((9, 26), (6, 50), (3, 110)):
                c = QColor(CYAN); c.setAlpha(int(a * strength))
                p.strokePath(path, QPen(c, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            lit = QColor(core)
            lit = QColor(int(lit.red() + (180 - lit.red()) * strength), int(lit.green() + (250 - lit.green()) * strength), 255)
            p.fillPath(path, lit)
        else:
            p.fillPath(path, core)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.TextAntialiasing)
        fm = QFontMetricsF(self.f_title)
        base = fm.ascent() + 2
        glitch = self.mode in ("glitch_in", "glitch_out")
        amt = 1.0 - (self._progress(self.GLITCH_IN if self.mode == "glitch_in" else self.GLITCH_OUT) if glitch else 1.0)
        # title, letter by letter (letter-spacing 3px)
        x = 0.0; self.rects = []
        for i, ch in enumerate(self.title):
            w = fm.horizontalAdvance(ch)
            self.rects.append(QRectF(x - 2, 0, w + 4, fm.height() + 4))
            draw = ch
            dx = 0.0
            if glitch and ch != "." and self.rng.random() < 0.55 * amt + 0.1:
                draw = self.rng.choice(GLYPHS[:36])
            if glitch:
                dx = self.rng.uniform(-4, 4) * amt
                for col, off in ((CYAN, -3), (MAGENTA, 3)):           # colour split
                    c = QColor(col); c.setAlpha(170)
                    path = QPainterPath(); path.addText(QPointF(x + dx + off * amt, base), self.f_title, draw)
                    p.fillPath(path, c)
            self._neon_char(p, x + dx, base, draw, self.f_title, self.glow[i] if not glitch else 0.0)
            x += w + 3
        if glitch:                                                    # slice tears
            for _ in range(3):
                y = self.rng.uniform(4, fm.height())
                c = QColor(CYAN if self.rng.random() < 0.5 else MAGENTA); c.setAlpha(int(140 * amt))
                p.fillRect(QRectF(self.rng.uniform(0, x * 0.6), y, self.rng.uniform(20, 90), 2), c)
        # second line
        text, is_acr = self._sub_text()
        fs = QFontMetricsF(self.f_sub)
        y2 = fm.height() + 6 + fs.ascent()
        x = 0.0
        for i, ch in enumerate(text):
            neon = is_acr and i in self.initials and self.mode in ("shown", "decode_in") and text[i] == self.acronym[i]
            if neon:
                f = QFont(self.f_sub); f.setBold(True)
                self._neon_char(p, x, y2, ch, f, 1.0)
                x += QFontMetricsF(f).horizontalAdvance(ch)
            else:
                path = QPainterPath(); path.addText(QPointF(x, y2), self.f_sub, ch)
                p.fillPath(path, QColor(MUTED) if not is_acr else QColor(TEXT))
                x += fs.horizontalAdvance(ch)
        p.end()


# ---------------- neon progress bar ----------------
class NeonBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self._v = 0.0
        self._shine = 0.0
        self._t = QTimer(self); self._t.timeout.connect(self._tick); self._t.start(33)

    def set_value(self, v):
        self._v = max(0.0, min(1.0, v)); self.update()

    def _tick(self):
        if 0 < self._v < 1:
            self._shine = (self._shine + 0.012) % 1.0
            self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bar = QRectF(6, h / 2 - 4, w - 12, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 34)); p.drawRoundedRect(bar, 4, 4)
        if self._v > 0:
            fill = QRectF(bar.x(), bar.y(), bar.width() * self._v, bar.height())
            for i, a in ((9, 20), (6, 36), (3, 70)):               # the neon glow
                p.setBrush(QColor(0, 229, 255, a))
                p.drawRoundedRect(fill.adjusted(-i, -i, i, i), 4 + i, 4 + i)
            g = QLinearGradient(fill.topLeft(), fill.topRight())
            g.setColorAt(0, CYAN); g.setColorAt(1, MAGENTA if self._v > 0.98 else QColor(120, 245, 255))
            p.setBrush(g); p.drawRoundedRect(fill, 4, 4)
            if self._v < 1:                                         # a moving shine
                sx = fill.x() + fill.width() * self._shine
                sg = QLinearGradient(QPointF(sx - 40, 0), QPointF(sx + 40, 0))
                sg.setColorAt(0, QColor(255, 255, 255, 0)); sg.setColorAt(0.5, QColor(255, 255, 255, 130))
                sg.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(sg); p.drawRoundedRect(fill, 4, 4)
        p.end()


# ---------------- worker -> UI ----------------
class Bridge(QObject):
    progress = Signal(int, int)
    result = Signal(dict)
    done = Signal(dict)
    failed = Signal(str)


# ---------------- the window ----------------
class Backdrop(QWidget):
    """Central widget. Paints a light tint over the system blur, or (no blur)
    its own dark gradient with soft colour glows."""

    def __init__(self, glass):
        super().__init__()
        self.glass = glass
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        if self.glass:
            p.fillRect(r, QColor(10, 12, 24, 120))
        else:
            g = QLinearGradient(0, 0, r.width(), r.height())
            g.setColorAt(0, QColor(13, 15, 30)); g.setColorAt(1, QColor(22, 18, 40))
            p.fillRect(r, g)
            for (fx, fy, fr, c) in ((0.1, 0.05, 0.55, QColor(0, 229, 255, 40)),
                                    (0.95, 0.9, 0.6, QColor(255, 61, 154, 38)),
                                    (0.9, 0.1, 0.4, QColor(120, 80, 255, 30))):
                rg = QRadialGradient(QPointF(r.width() * fx, r.height() * fy), r.width() * fr)
                rg.setColorAt(0, c); rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.fillRect(r, rg)
        p.end()


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("CHAMBER", "CHAMBER")
        self.setWindowTitle(f"{APP}  v{__version__}")
        ico = _resource("assets/app.ico")
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))
        self.resize(920, 820)
        self.setMinimumSize(780, 700)
        self.glass = self._want_glass()
        if self.glass:
            self.setAttribute(Qt.WA_TranslucentBackground)
        self.bridge = Bridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.result.connect(self._on_result)
        self.bridge.done.connect(self._on_done)
        self.bridge.failed.connect(self._on_failed)
        self.worker = None
        self._build()
        self._load_settings()

    # ---------- glass ----------
    def _want_glass(self):
        if os.environ.get("CHAMBER_GLASS") == "off":
            return False
        if os.environ.get("CHAMBER_GLASS") == "preview":           # screenshots only
            return True
        return sys.platform == "win32" and self.settings.value("glass", True, type=bool)

    def showEvent(self, e):
        super().showEvent(e)
        if self.glass and sys.platform == "win32" and not getattr(self, "_styled", False):
            self._styled = True
            from . import winglass
            if not winglass.apply(int(self.winId())):
                self._drop_glass()               # no blur on this PC: painted glass instead

    def _drop_glass(self):
        """Blur not available: fall back to the painted backdrop."""
        self.glass = False
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.centralWidget().glass = False
        self.centralWidget().update()

    # ---------- layout ----------
    def _build(self):
        root = Backdrop(self.glass); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(20, 16, 20, 16); outer.setSpacing(12)

        # header: logo, name, tabs
        head = QHBoxLayout(); head.setSpacing(12)
        logo = QLabel(); pm = QPixmap(_resource("assets/logo_64.png"))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(logo)
        self.title_w = NeonTitle(APP, SUBTITLE, ACRONYM)
        head.addWidget(self.title_w); head.addStretch(1)
        bar = QFrame(); bar.setObjectName("tabbar")
        bl = QHBoxLayout(bar); bl.setContentsMargins(4, 4, 4, 4); bl.setSpacing(4)
        self.tabs = QButtonGroup(self); self.tabs.setExclusive(True)
        self.pages = QStackedWidget()
        self._tab_glow = {}
        for i, name in enumerate(("Run", "Settings", "Badges")):
            b = QPushButton(name); b.setObjectName("tab"); b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.tabs.addButton(b, i); bl.addWidget(b)
        self.tabs.idToggled.connect(self._tab_changed)
        head.addWidget(bar)
        outer.addLayout(head)
        outer.addWidget(self.pages, 1)

        self.pages.addWidget(self._run_page())
        self.pages.addWidget(self._settings_page())
        self.pages.addWidget(self._badges_page())
        self.tabs.button(0).setChecked(True)

    def _tab_changed(self, idx, on):
        b = self.tabs.button(idx)
        if on:
            self.pages.setCurrentIndex(idx)
            glow(b, CYAN, 22, 200)
            if idx == 2:
                self._refresh_badges()
        else:
            b.setGraphicsEffect(None)

    def _run_page(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        # folders
        c, cl = card("Folders")
        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(8)
        self.in_edit = QLineEdit(); self.in_edit.setPlaceholderText("Folder with your PDF sheets (subfolders included)")
        self.out_edit = QLineEdit(); self.out_edit.setPlaceholderText("Where the results go (default: <PDF folder>\\converted)")
        b1 = QPushButton("Browse…"); b1.clicked.connect(self._pick_in)
        b2 = QPushButton("Browse…"); b2.clicked.connect(self._pick_out)
        for r, (lbl, ed, b) in enumerate((("PDF folder", self.in_edit, b1), ("Output folder", self.out_edit, b2))):
            l = QLabel(lbl); l.setObjectName("muted")
            g.addWidget(l, r, 0); g.addWidget(ed, r, 1); g.addWidget(b, r, 2)
        g.setColumnStretch(1, 1)
        cl.addLayout(g)
        lay.addWidget(c)

        # the stage: animation, progress, status, actions
        c, cl = card()
        self.stage = Stage(); self.stage.setMinimumHeight(190)
        cl.addWidget(self.stage, 1)
        self.bar = NeonBar(); cl.addWidget(self.bar)
        row = QHBoxLayout(); row.setSpacing(8)
        self.status = QLabel("Ready when you are."); self.status.setObjectName("status")
        row.addWidget(self.status, 1)
        self.clear_btn = QPushButton("Clear"); self.clear_btn.clicked.connect(self._clear)
        self.open_btn = QPushButton("Open results"); self.open_btn.clicked.connect(self._open_out)
        self.open_btn.setEnabled(False)
        self.run_btn = QPushButton("Run"); self.run_btn.setObjectName("run")
        self.run_btn.setCursor(Qt.PointingHandCursor); self.run_btn.clicked.connect(self._run)
        self._run_glow = glow(self.run_btn, MAGENTA, 28, 150)
        for b in (self.clear_btn, self.open_btn, self.run_btn):
            row.addWidget(b)
        cl.addLayout(row)
        lay.addWidget(c, 3)

        # log
        c, cl = card("Log")
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(110)
        cl.addWidget(self.log)
        lay.addWidget(c, 2)
        return page

    def _settings_page(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        c, cl = card("Output")
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10)
        l = QLabel("Coordinate system"); l.setObjectName("muted"); g.addWidget(l, 0, 0)
        self.crs = QComboBox(); self.crs.addItems(CRS_CHOICES); g.addWidget(self.crs, 0, 1)
        self.epsg = QLineEdit(); self.epsg.setPlaceholderText("EPSG code, e.g. 32643"); self.epsg.setMaximumWidth(200)
        g.addWidget(self.epsg, 0, 2)
        self.crs.currentIndexChanged.connect(lambda i: self.epsg.setVisible(i == len(CRS_CHOICES) - 1))
        l = QLabel("Export formats"); l.setObjectName("muted"); g.addWidget(l, 1, 0)
        fr = QHBoxLayout(); fr.setSpacing(18); self.fmt = {}
        for key, label, on in (("geojson", "GeoJSON", True), ("kml", "KML", True), ("shp", "Shapefile", False),
                               ("gpkg", "GeoPackage", False), ("dxf", "DXF", False)):
            cb = QCheckBox(label); cb.setChecked(on); self.fmt[key] = cb; fr.addWidget(cb)
        fr.addStretch(1); g.addLayout(fr, 1, 1, 1, 2)
        self.merge = QCheckBox("Also make one merged, zipped shapefile (ready for Google Earth Engine)")
        g.addWidget(self.merge, 2, 1, 1, 2)
        self.tif = QCheckBox("Also export a GeoTIFF of each sheet (slower)")
        g.addWidget(self.tif, 3, 1, 1, 2)
        g.setColumnStretch(1, 1)
        cl.addLayout(g); lay.addWidget(c)

        c, cl = card("Processing")
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10)
        l = QLabel("Parallel jobs"); l.setObjectName("muted"); g.addWidget(l, 0, 0)
        self.jobs = QSpinBox(); self.jobs.setRange(1, max(1, (os.cpu_count() or 4)))
        self.jobs.setValue(min(4, os.cpu_count() or 1)); self.jobs.setMaximumWidth(90)
        g.addWidget(self.jobs, 0, 1)
        hint = QLabel("More jobs = faster on big batches (uses more CPU)"); hint.setObjectName("muted")
        g.addWidget(hint, 0, 2)
        l = QLabel("Debug images"); l.setObjectName("muted"); g.addWidget(l, 1, 0)
        self.debug = QComboBox(); self.debug.addItems([a for a, _ in DEBUG_CHOICES]); g.addWidget(self.debug, 1, 1, 1, 2)
        self.vector = QCheckBox("Use the PDF's vector outline when it has one"); self.vector.setChecked(True)
        g.addWidget(self.vector, 2, 1, 1, 2)
        self.ocr = QCheckBox("Read sheet IDs and the header panel (offline OCR)")
        g.addWidget(self.ocr, 3, 1, 1, 2)
        g.setColumnStretch(2, 1)
        cl.addLayout(g); lay.addWidget(c)

        c, cl = card("Look")
        self.glass_cb = QCheckBox("Glass blur behind the window (Windows; takes effect next start)")
        self.glass_cb.setChecked(self.settings.value("glass", True, type=bool))
        cl.addWidget(self.glass_cb)
        lay.addWidget(c)
        lay.addStretch(1)
        return page

    def _badges_page(self):
        page = QWidget(); self._badge_lay = QVBoxLayout(page)
        self._badge_lay.setContentsMargins(0, 0, 0, 0); self._badge_lay.setSpacing(12)
        c, cl = card("Achievements")
        self._badge_head = QLabel(); self._badge_head.setObjectName("muted"); cl.addWidget(self._badge_head)
        self._badge_grid = QGridLayout(); self._badge_grid.setSpacing(10); cl.addLayout(self._badge_grid)
        self._badge_lay.addWidget(c); self._badge_lay.addStretch(1)
        return page

    def _refresh_badges(self):
        while self._badge_grid.count():
            w = self._badge_grid.takeAt(0).widget()
            if w: w.deleteLater()
        try:
            unlocked = set(A.load_stats().get("unlocked", []))
        except Exception:
            unlocked = set()
        self._badge_head.setText(f"{len(unlocked)} of {len(A.BADGES)} unlocked")
        for i, (bid, name, desc, _t) in enumerate(A.BADGES):
            got = bid in unlocked
            f = QFrame(); f.setObjectName("card")
            fl = QVBoxLayout(f); fl.setContentsMargins(14, 10, 14, 10)
            n = QLabel(("✦ " if got else "○ ") + name)
            n.setStyleSheet(f"font-weight:700; color:{'#00E5FF' if got else MUTED};")
            d = QLabel(desc); d.setObjectName("muted"); d.setWordWrap(True)
            fl.addWidget(n); fl.addWidget(d)
            if got:
                glow(f, CYAN, 22, 120)
            self._badge_grid.addWidget(f, i // 2, i % 2)

    # ---------- settings persistence ----------
    def _load_settings(self):
        s = self.settings
        self.crs.setCurrentIndex(s.value("crs", 0, type=int))
        self.epsg.setText(s.value("epsg", "", type=str))
        self.epsg.setVisible(self.crs.currentIndex() == len(CRS_CHOICES) - 1)
        for k, cb in self.fmt.items():
            cb.setChecked(s.value(f"fmt_{k}", cb.isChecked(), type=bool))
        self.merge.setChecked(s.value("merge", False, type=bool))
        self.tif.setChecked(s.value("tif", False, type=bool))
        self.jobs.setValue(s.value("jobs", self.jobs.value(), type=int))
        self.debug.setCurrentIndex(s.value("debug", 0, type=int))
        self.vector.setChecked(s.value("vector", True, type=bool))
        self.ocr.setChecked(s.value("ocr", False, type=bool))

    def _save_settings(self):
        s = self.settings
        s.setValue("crs", self.crs.currentIndex()); s.setValue("epsg", self.epsg.text())
        for k, cb in self.fmt.items():
            s.setValue(f"fmt_{k}", cb.isChecked())
        s.setValue("merge", self.merge.isChecked()); s.setValue("tif", self.tif.isChecked())
        s.setValue("jobs", self.jobs.value()); s.setValue("debug", self.debug.currentIndex())
        s.setValue("vector", self.vector.isChecked()); s.setValue("ocr", self.ocr.isChecked())
        s.setValue("glass", self.glass_cb.isChecked())

    def closeEvent(self, e):
        self._save_settings()
        super().closeEvent(e)

    # ---------- helpers ----------
    def _pick_in(self):
        d = QFileDialog.getExistingDirectory(self, "Select the folder containing your PDFs")
        if d:
            self.in_edit.setText(d)
            if not self.out_edit.text():
                self.out_edit.setText(str(Path(d) / "converted"))

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Select an output folder")
        if d:
            self.out_edit.setText(d)

    def _epsg_value(self):
        i = self.crs.currentIndex()
        if i == 0: return "auto"
        if i == len(CRS_CHOICES) - 1: return self.epsg.text().strip()
        return CRS_CHOICES[i].split(":")[1].split(" ")[0]

    def _log(self, msg, kind=None):
        color = {"ok": "#5CFFB0", "flag": "#FFC857", "fail": "#FF5C8A", "head": "#00E5FF"}.get(kind, TEXT)
        weight = "700" if kind == "head" else "400"
        safe = (msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\n", "<br>").replace("  ", "&nbsp;&nbsp;"))
        self.log.appendHtml(f'<span style="color:{color}; font-weight:{weight}">{safe}</span>')
        self.log.moveCursor(QTextCursor.End)

    @staticmethod
    def _eta(done, total, started):
        if done < 2:
            return "warming up…"
        left = (time.time() - started) / done * (total - done)
        return "under a minute left" if left < 60 else f"about {int(left // 60) + 1} min left"

    def _warn(self, text):
        QMessageBox.warning(self, APP, text)

    def _open_out(self):
        out = self.out_edit.text()
        if out and os.path.isdir(out):
            try:
                os.startfile(out)            # Windows
            except AttributeError:
                pass

    def _clear(self):
        self.log.clear(); self.bar.set_value(0); self.stage.show_rest()
        self.status.setText("Ready when you are.")
        self.in_edit.clear(); self.out_edit.clear(); self.open_btn.setEnabled(False)

    def _busy(self, on):
        for w in (self.run_btn, self.clear_btn):
            w.setEnabled(not on)
        self.open_btn.setEnabled(False if on else bool(self.out_edit.text()))

    # ---------- run ----------
    def _run(self):
        indir = self.in_edit.text().strip(); outdir = self.out_edit.text().strip()
        if not indir or not Path(indir).is_dir():
            return self._warn("Please choose a valid PDF folder.")
        if not outdir:
            outdir = str(Path(indir) / "converted"); self.out_edit.setText(outdir)
        pdfs = list(Path(indir).rglob("*.pdf"))
        if not pdfs:
            return self._warn("No PDF files found in that folder.")
        formats = [k for k, cb in self.fmt.items() if cb.isChecked()]
        if not formats:
            self.tabs.button(1).setChecked(True)
            return self._warn("Pick at least one export format in Settings.")
        epsg = self._epsg_value()
        if epsg != "auto" and not epsg.isdigit():
            self.tabs.button(1).setChecked(True)
            return self._warn("Type a numeric EPSG code (for example 32643), or pick Auto.")
        self._save_settings()
        self._last_formats = formats
        params = {"epsg": epsg, "dpi": 300, "simplify": 0.0010, "white_min": 175,
                  "vector": self.vector.isChecked(), "tif": self.tif.isChecked(),
                  "formats": formats, "merge_zip": self.merge.isChecked(),
                  "ocr": self.ocr.isChecked(), "output_dir": outdir,
                  "debug_images": DEBUG_CHOICES[self.debug.currentIndex()][1]}
        self._busy(True); self.bar.set_value(0)
        self._started = time.time(); self._total = len(pdfs)
        self.status.setText(f"0/{len(pdfs)}  ·  off we go!")
        self._log(f"Processing {len(pdfs)} PDF(s)  ->  {outdir}   (CRS {epsg})", "head")
        self.stage.start()
        jobs = self.jobs.value()

        def work():
            try:
                summary = run_batch(indir, outdir, params, jobs=jobs,
                                    on_progress=lambda d, t: self.bridge.progress.emit(d, t),
                                    on_log=lambda r: self.bridge.result.emit(r))
                self.bridge.done.emit(summary)
            except Exception:
                self.bridge.failed.emit(traceback.format_exc())

        self.worker = threading.Thread(target=work, daemon=True); self.worker.start()

    def _on_progress(self, d, t):
        self.bar.set_value(d / t if t else 0)
        self.status.setText(f"{d}/{t}  ·  {self._eta(d, t, self._started)}")

    def _on_result(self, r):
        if r["error"]:
            self._log(f"  FAIL  {r['file']}: {r['error']}", "fail")
        else:
            p = r["props"]
            self._log(f"  ok    {r['file']}   {p['area_ha']} ha  [{p['qc']}]",
                      "ok" if p["qc"] == "ok" else "flag")

    def _on_done(self, s):
        clean = s["failed"] == 0 and s["flagged"] == 0
        self._log(f"\nDone: {s['ok']} ok, {s['flagged']} flagged, {s['failed']} failed.", "head")
        self.bar.set_value(1.0); self.stage.finish()
        self.status.setText("Good dog! All done." if clean else "Done. A few sheets to review.")
        self._busy(False)
        try:
            _, newly = A.record_run(s, getattr(self, "_last_formats", []))
        except Exception:
            newly = []
        Finished(self, s, newly).exec()

    def _on_failed(self, tb):
        self._log("\nERROR:\n" + tb, "fail")
        self.stage.show_rest(); self.status.setText("Something went wrong. See the log.")
        self._busy(False)
        QMessageBox.critical(self, APP, "Something went wrong. See the log.")


class Confetti(QWidget):
    def __init__(self, parent, on):
        super().__init__(parent)
        self.setFixedHeight(90)
        self.bits = [[random.uniform(0, 1), random.uniform(-0.6, 0), random.uniform(0.012, 0.03),
                      random.choice([CYAN, MAGENTA, QColor(255, 200, 87), QColor(92, 255, 176)])]
                     for _ in range(40)] if on else []
        self._t = QTimer(self); self._t.timeout.connect(self._tick)
        if on:
            self._t.start(30)
        self._n = 0

    def _tick(self):
        self._n += 1
        for b in self.bits:
            b[1] += b[2]
        self.update()
        if self._n > 80:
            self._t.stop()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
        for x, y, _v, c in self.bits:
            if 0 <= y <= 1:
                p.setBrush(c); p.drawRoundedRect(QRectF(x * self.width(), y * self.height(), 6, 6), 2, 2)
        p.end()


class Finished(QDialog):
    def __init__(self, app, s, newly):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(APP); self.setModal(True); self.setMinimumWidth(440)
        self.setStyleSheet(QSS)
        clean = s["failed"] == 0 and s["flagged"] == 0 and s["ok"] > 0
        head = "All done!" if clean else ("Done — a few to review" if not s["failed"] else "Run complete")
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 18, 24, 18); lay.setSpacing(6)
        h = QLabel(head); h.setStyleSheet("font-size:17pt; font-weight:700; color:#00E5FF;")
        h.setAlignment(Qt.AlignCenter); lay.addWidget(h)
        n = QLabel(f"{s['ok']} ok     {s['flagged']} flagged     {s['failed']} failed")
        n.setAlignment(Qt.AlignCenter); lay.addWidget(n)
        o = QLabel(f"Saved in:\n{s['output_dir']}"); o.setObjectName("muted"); o.setAlignment(Qt.AlignCenter)
        lay.addWidget(o)
        lay.addWidget(Confetti(self, clean))
        if newly:
            c, cl = card("Achievement unlocked")
            for _bid, name, desc in newly:
                r = QLabel(f"✦ {name}  —  {desc}"); r.setStyleSheet("color:#00E5FF; font-weight:600;")
                cl.addWidget(r)
            lay.addWidget(c)
        row = QHBoxLayout(); row.addStretch(1)
        b = QPushButton("Open results"); b.clicked.connect(app._open_out); row.addWidget(b)
        c = QPushButton("Close"); c.clicked.connect(self.accept); row.addWidget(c)
        lay.addLayout(row)


def main():
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("CHAMBER")
    app.setStyleSheet(QSS)
    w = App(); w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
