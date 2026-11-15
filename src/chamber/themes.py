"""The three styles (Frost, Midnight, Atlas) and the six looks built from them.

A look = a style + a layout for the Extract screen:
  "cols"  - side panels around the map
  "focus" - the map fills the screen, the panels float over it

Midnight is the v1.9 look, unchanged. Everything that paints reads colours
from the current theme, so switching is one call to set_look().
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    dark: bool
    text: str
    muted: str
    accent: str            # glows, active tab, progress
    accent2: str           # second neon (run button, colour split)
    on_accent: str         # text on an accent fill
    card_bg: str
    card_border: str
    field_bg: str
    field_border: str
    btn_bg: str
    btn_border: str
    btn_hover: str
    active_bg: str         # checked tab / active tool
    active_border: str
    float_bg: str          # floating panels over the map (Focus)
    float_border: str
    radius: int            # card corner radius
    btn_radius: int
    glow: bool             # neon glows on / off
    font: str
    ok: str; flag: str; fail: str
    backdrop: tuple        # (top, bottom) colours when no system blur
    tint: tuple            # RGBA over the system blur
    blur_ok: bool          # Windows blur behind the window suits this style
    map_bg: str


FROST = Theme(
    "frost", "Frost", False,
    text="#26303b", muted="#4f5a67", accent="#2f8fb8", accent2="#7cc6e6", on_accent="#0f2a3a",
    card_bg="rgba(255,255,255,105)", card_border="rgba(255,255,255,200)",
    field_bg="rgba(255,255,255,140)", field_border="rgba(79,90,103,70)",
    btn_bg="qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(255,255,255,190), stop:1 rgba(236,239,243,150))",
    btn_border="rgba(255,255,255,230)", btn_hover="rgba(214,238,249,200)",
    active_bg="qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #d4eef9, stop:1 #9fd3ea)", active_border="rgba(255,255,255,240)",
    float_bg="rgba(250,251,252,175)", float_border="rgba(255,255,255,235)",
    radius=20, btn_radius=16, glow=True, font="'Segoe UI Variable', 'Segoe UI', 'Inter', 'Noto Sans', sans-serif",
    ok="#15803d", flag="#a16207", fail="#be123c",
    backdrop=("#e3e6ea", "#cfd4da"), tint=(236, 239, 243, 165), blur_ok=True, map_bg="#c9ced4")

MIDNIGHT = Theme(
    "midnight", "Midnight", True,
    text="#E8ECFF", muted="#9AA3C7", accent="#00E5FF", accent2="#FF3D9A", on_accent="#0B0D18",
    card_bg="rgba(255,255,255,16)", card_border="rgba(255,255,255,34)",
    field_bg="rgba(0,0,0,70)", field_border="rgba(255,255,255,46)",
    btn_bg="rgba(255,255,255,20)", btn_border="rgba(255,255,255,50)", btn_hover="rgba(0,229,255,26)",
    active_bg="rgba(0,229,255,30)", active_border="rgb(0,229,255)",
    float_bg="rgba(10,16,26,200)", float_border="rgba(0,229,255,80)",
    radius=16, btn_radius=11, glow=True, font="'Segoe UI Variable', 'Segoe UI', 'Noto Sans', sans-serif",
    ok="#5CFFB0", flag="#FFC857", fail="#FF5C8A",
    backdrop=("#0d0f1e", "#161228"), tint=(10, 12, 24, 120), blur_ok=True, map_bg="#0b0e18")

ATLAS = Theme(
    "atlas", "Atlas", False,
    text="#1f2933", muted="#52606d", accent="#0f5f5f", accent2="#b45309", on_accent="#ffffff",
    card_bg="#fbfaf6", card_border="#d9d3c4",
    field_bg="#ffffff", field_border="#c9c2b0",
    btn_bg="#fbfaf6", btn_border="#c9c2b0", btn_hover="#eef4f2",
    active_bg="#0f5f5f", active_border="#0b4a4a",
    float_bg="#fbfaf6", float_border="#c9c2b0",
    radius=6, btn_radius=6, glow=False, font="'IBM Plex Sans', 'Segoe UI', 'Noto Sans', sans-serif",
    ok="#166534", flag="#92400e", fail="#9f1239",
    backdrop=("#efece4", "#e7e2d6"), tint=(239, 236, 228, 255), blur_ok=False, map_bg="#e2ddd0")

THEMES = {t.key: t for t in (FROST, MIDNIGHT, ATLAS)}

LOOKS = [("frost", "cols", "Frost"), ("midnight", "cols", "Midnight"), ("atlas", "cols", "Atlas"),
         ("frost", "focus", "Focus + Frost"), ("midnight", "focus", "Focus + Midnight"),
         ("atlas", "focus", "Focus + Atlas")]

_current = {"theme": MIDNIGHT, "layout": "cols"}


def current() -> Theme:
    return _current["theme"]


def layout() -> str:
    return _current["layout"]


def set_look(theme_key, layout_name=None):
    _current["theme"] = THEMES[theme_key]
    if layout_name:
        _current["layout"] = layout_name


def next_look(index, rng=None, order="random"):
    """Index of the next look: a different one at random (default) or in turn."""
    import random
    if order != "random":
        return (index + 1) % len(LOOKS)
    r = rng or random
    n = index
    while n == index:
        n = r.randrange(len(LOOKS))
    return n


def qss(t: Theme | None = None) -> str:
    t = t or current()
    r, br = t.radius, t.btn_radius
    sel = "rgba(0,229,255,120)" if t.dark else "rgba(47,143,184,90)"
    return f"""
* {{ color: {t.text}; font-family: {t.font}; font-size: 10pt; }}
QLabel#title {{ font-size: 17pt; font-weight: 700; letter-spacing: 3px; }}
QLabel#subtitle, QLabel#muted {{ color: {t.muted}; }}
QLabel#cardTitle {{ color: {t.muted}; font-size: 8.5pt; font-weight: 700; letter-spacing: 2px; }}
QLabel#status {{ color: {t.text}; font-size: 9.5pt; }}
QLabel#big {{ font-size: 13pt; font-weight: 700; }}
QFrame#card {{ background: {t.card_bg}; border: 1px solid {t.card_border}; border-radius: {r}px; }}
QFrame#float {{ background: {t.float_bg}; border: 1px solid {t.float_border}; border-radius: {max(r, 14)}px; }}
QFrame#tabbar {{ background: {"rgba(0,0,0,60)" if t.dark else "rgba(255,255,255,90)"}; border: 1px solid {t.card_border}; border-radius: {max(br, 6) + 6}px; }}
QPushButton, QToolButton {{ background: {t.btn_bg}; border: 1px solid {t.btn_border}; border-radius: {br}px; padding: 7px 16px; }}
QPushButton:hover, QToolButton:hover {{ border: 1px solid {t.accent}; background: {t.btn_hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.active_bg}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.muted}; border: 1px solid {t.card_border}; background: transparent; }}
QPushButton#tab {{ background: transparent; border: 1px solid transparent; border-radius: {max(br, 6) + 2}px; padding: 6px 18px; color: {t.muted}; font-weight: 600; }}
QPushButton#tab:hover {{ color: {t.text}; border: 1px solid {t.accent}; }}
QPushButton#tab:checked {{ color: {t.accent if t.dark else t.on_accent}; border: 1px solid {t.active_border}; background: {t.active_bg}; }}
QToolButton#tool {{ padding: 6px; min-width: 32px; min-height: 32px; border-radius: {max(br, 8)}px; }}
QToolButton#tool:checked {{ background: {t.active_bg}; border: 1px solid {t.active_border}; }}
QPushButton#primary, QPushButton#run {{ font-weight: 700; color: {t.on_accent}; border: 1px solid {t.active_border};
  background: {"qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgb(0,229,255), stop:1 rgb(255,61,154))" if t.dark else t.active_bg}; }}
QPushButton#run {{ font-size: 11pt; padding: 9px 30px; border: none; }}
QPushButton#primary:hover, QPushButton#run:hover {{ background: {"qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgb(120,245,255), stop:1 rgb(255,120,190))" if t.dark else t.accent}; color: {t.on_accent if t.dark else "#ffffff"}; }}
QPushButton#run:disabled, QPushButton#primary:disabled {{ color: {t.muted}; background: {t.card_bg}; }}
QLineEdit, QComboBox, QSpinBox {{ background: {t.field_bg}; border: 1px solid {t.field_border};
  border-radius: {max(br - 2, 4)}px; padding: 6px 10px; selection-background-color: {sel}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {t.accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {"#151829" if t.dark else "#fbfcfd"}; border: 1px solid {t.accent}; selection-background-color: {sel}; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {t.field_border}; background: {t.field_bg}; }}
QCheckBox::indicator:hover {{ border: 1px solid {t.accent}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border: 1px solid {t.accent}; }}
QSlider::groove:horizontal {{ height: 4px; background: {t.card_border}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: {t.accent}; }}
QPlainTextEdit, QListWidget {{ background: {t.field_bg}; border: 1px solid {t.card_border}; border-radius: {max(r - 4, 4)}px;
  padding: 6px; }}
QPlainTextEdit {{ font-family: 'Cascadia Mono', Consolas, 'DejaVu Sans Mono', monospace; font-size: 9pt; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {sel}; color: {t.text}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {t.card_border}; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {t.accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QDialog, QMenu {{ background: {"#12152A" if t.dark else t.backdrop[0]}; }}
QMenu::item {{ padding: 6px 18px; }}
QMenu::item:selected {{ background: {sel}; }}
QToolTip {{ color: {t.text}; background: {"#12152A" if t.dark else "#fbfcfd"}; border: 1px solid {t.accent}; padding: 4px; }}
QGraphicsView {{ border: 1px solid {t.card_border}; border-radius: {r}px; background: {t.map_bg}; }}
"""
