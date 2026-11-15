"""Place a PDF page on the ground from the grid labels printed around the map,
e.g. "410000 E" / "1350000 N", or degree labels like 12°30'00"N.

Each axis is fitted on its own (value = a * page_position + b), which is exact
for north-up maps. The fit is refused when the labels disagree, so a wrong
placement never slips through quietly.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

_PROJ = re.compile(r"^\s*(?:([EN])\s*)?(\d{1,3}(?:[ ,]\d{3})+|\d{4,8})(?:\.(\d+))?\s*(?:m\s*)?([EN])?\s*$")
_DMS = re.compile(r"""^\s*(\d{1,3})\s*°\s*(?:(\d{1,2})\s*['′]\s*)?(?:(\d{1,2}(?:\.\d+)?)\s*["″]\s*)?([NSEW])\s*$""")
_EPSG = re.compile(r"EPSG\s*[:#]?\s*(\d{4,6})", re.I)
_UTM = re.compile(r"UTM\s*(?:zone)?\s*(\d{1,2})\s*([NS])", re.I)


@dataclass
class GridFit:
    ax: float; bx: float          # X = ax * page_x + bx
    ay: float; by: float          # Y = ay * page_y + by   (page y grows downwards)
    n_x: int; n_y: int
    max_resid: float              # in map units
    epsg: int | None              # from the page text, if printed
    geographic: bool              # degree labels -> EPSG:4326

    def page_to_map(self, x, y):
        return self.ax * x + self.bx, self.ay * y + self.by

    def note(self):
        unit = "°" if self.geographic else " m"
        return f"Grid labels ({self.n_x + self.n_y} read, fit {self.max_resid:.3f}{unit})"


def _value(text):
    """'410000 E' -> (410000.0, 'E'); '12°30\\'00"N' -> (12.5, 'N', geographic)."""
    m = _PROJ.match(text)
    if m:
        axis = m.group(1) or m.group(4)
        if not axis or (m.group(1) and m.group(4)):
            return None
        v = float(re.sub(r"[ ,]", "", m.group(2)) + ("." + m.group(3) if m.group(3) else ""))
        return v, axis, False
    m = _DMS.match(text)
    if m:
        v = float(m.group(1)) + float(m.group(2) or 0) / 60 + float(m.group(3) or 0) / 3600
        h = m.group(4)
        if h in "SW":
            v = -v
        return v, ("N" if h in "NS" else "E"), True
    return None


def page_crs(page_text: str):
    m = _EPSG.search(page_text)
    if m:
        return int(m.group(1))
    m = _UTM.search(page_text)
    if m and re.search(r"WGS\s*-?\s*84", page_text, re.I):
        return (32600 if m.group(2).upper() == "N" else 32700) + int(m.group(1))
    return None


def _fit(vals, pos):
    import numpy as np
    vals, pos = np.asarray(vals, float), np.asarray(pos, float)
    if len(set(vals.round(6))) < 2 or np.ptp(pos) < 20:
        return None
    a, b = np.polyfit(pos, vals, 1)
    return a, b, float(np.abs(vals - (a * pos + b)).max())


def fit_page(page) -> GridFit | None:
    """Grid fit for a PyMuPDF page, or None when the labels can't be trusted."""
    xs, ys, geo = [], [], set()
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            t = "".join(s["text"] for s in line["spans"]).strip()
            r = _value(t)
            if not r:
                continue
            v, axis, g = r
            x0, y0, x1, y1 = line["bbox"]
            (xs if axis == "E" else ys).append((v, (x0 + x1) / 2 if axis == "E" else (y0 + y1) / 2))
            geo.add(g)
    if len(geo) != 1:
        return None
    # each tick is usually labelled twice (top and bottom): duplicates are fine
    fx = _fit([v for v, _ in xs], [p for _, p in xs]) if len(xs) >= 2 else None
    fy = _fit([v for v, _ in ys], [p for _, p in ys]) if len(ys) >= 2 else None
    if not fx or not fy:
        return None
    (ax, bx, rx), (ay, by, ry) = fx, fy
    if ax <= 0 or ay >= 0:                     # east must grow right, north must grow up
        return None
    span = max(abs(ax), abs(ay)) * max(page.rect.width, page.rect.height)
    if max(rx, ry) > 0.002 * span:             # labels disagree with each other
        return None
    g = geo.pop()
    epsg = 4326 if g else page_crs(page.get_text())
    return GridFit(ax, bx, ay, by, len(xs), len(ys), max(rx, ry), epsg, g)
