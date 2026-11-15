"""Small stroke icons, drawn in the current theme's text colour."""
from __future__ import annotations
from PySide6.QtCore import QByteArray, Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter

PATHS = {
    "area":    '<circle cx="12" cy="12" r="7.5" stroke-dasharray="3 2.2"/><circle cx="12" cy="12" r="2.2"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"/>',
    "box":     '<rect x="4" y="5" width="16" height="14" rx="1.5" stroke-dasharray="3 2.5"/>',
    "line":    '<path d="M3 17l5-6 4 3 8-9"/><circle cx="3" cy="17" r="1.4"/><circle cx="20" cy="5" r="1.4"/>',
    "point":   '<path d="M12 21s-6-5.3-6-10a6 6 0 0112 0c0 4.7-6 10-6 10z"/><circle cx="12" cy="11" r="2.2"/>',
    "pick":    '<path d="M4 4l7 17 2.5-7.5L21 11z"/><path d="M14 14l6 6"/>',
    "plus":    '<path d="M12 5v14M5 12h14"/>',
    "minus":   '<path d="M5 12h14"/>',
    "similar": '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/><path d="M15 3h6v6M9 21H3v-6"/>',
    "text":    '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
    "undo":    '<path d="M9 7L4 12l5 5"/><path d="M4 12h10a6 6 0 010 12"/>',
    "redo":    '<path d="M15 7l5 5-5 5"/><path d="M20 12H10a6 6 0 000 12"/>',
    "check":   '<path d="M5 12l5 5 9-10"/>',
    "x":       '<path d="M6 6l12 12M18 6L6 18"/>',
    "cycle":   '<path d="M4 12a8 8 0 0114-5.3L20 9"/><path d="M20 4v5h-5"/><path d="M20 12a8 8 0 01-14 5.3L4 15"/><path d="M4 20v-5h5"/>',
    "eye":     '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "eyeoff":  '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0112 5c6 0 10 7 10 7a17 17 0 01-3 3.7M6.6 6.6C3.8 8.4 2 12 2 12s4 7 10 7a9.8 9.8 0 005.4-1.6"/>',
    "export":  '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 19h16"/>',
    "open":    '<path d="M3 7h6l2 2h10v10H3z"/>',
    "fit":     '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "files":   '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/>',
    "layers":  '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "trash":   '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "sound_off": '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l5 6M22 9l-5 6"/>',
    "sound_fx":  '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9.5a4 4 0 010 5"/>',
    "sound_all": '<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
    "brush":   '<path d="M19 3l2 2-9 9-3-3z"/><path d="M9 11c-3 0-5 2-5 5 0 2-1 3-2 3 2 2 7 2 9-1 1.5-2.2.5-4.5-2-7z"/>',
    "red":     '<path d="M3 8a2 2 0 012-2h11a2 2 0 012 2v2a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M18 9h2v5h-8v3"/><path d="M11 17h2v4h-2z"/>',
    "roads":   '<path d="M8 21L10 3M16 21L14 3"/><path d="M12 5v2M12 11v2M12 17v2"/>',
    "square":  '<path d="M5 19L9 5h10l-4 14z"/><path d="M5 19h10" stroke-dasharray="2 2"/>',
}


def icon(name, color="#000000", size=20):
    from PySide6.QtSvg import QSvgRenderer
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    ico = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale); pm.fill(Qt.transparent)
        p = QPainter(pm); r.render(p, QRectF(0, 0, size * scale, size * scale)); p.end()
        pm.setDevicePixelRatio(scale)
        ico.addPixmap(pm)
    return ico
