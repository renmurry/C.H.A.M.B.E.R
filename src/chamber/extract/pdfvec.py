"""Lines and shapes drawn inside a PDF, grouped by how they look (colour,
width, fill). Click one drawn line and the whole group can be taken in one go:
every road drawn in orange 3 pt, every plot boundary drawn in red.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Style:
    key: tuple
    label: str
    stroke: str | None             # "#rrggbb"
    fill: str | None
    width: float
    paths: list = field(default_factory=list)     # list of (kind, Nx2 pixel array), kind: line|polygon

    @property
    def kind(self):
        kinds = {k for k, _ in self.paths}
        return "polygon" if kinds == {"polygon"} else "line"


_NAMES = [("black", (0, 0, 0)), ("white", (255, 255, 255)), ("grey", (128, 128, 128)),
          ("red", (220, 30, 30)), ("orange", (255, 150, 0)), ("yellow", (250, 220, 0)),
          ("green", (40, 160, 60)), ("cyan", (0, 200, 220)), ("blue", (30, 80, 220)),
          ("purple", (130, 60, 180)), ("pink", (240, 100, 170)), ("brown", (130, 80, 40))]


def colour_name(rgb):
    r, g, b = (int(round(c * 255)) for c in rgb)
    return min(_NAMES, key=lambda n: sum((a - c) ** 2 for a, c in zip(n[1], (r, g, b))))[0]


def _hex(rgb):
    return None if not rgb else "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb[:3])


def _bezier(p0, p1, p2, p3, n=8):
    t = np.linspace(0, 1, n)[1:, None]
    P = [np.array([p.x, p.y]) for p in (p0, p1, p2, p3)]
    return (1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t ** 2 * P[2] + t ** 3 * P[3]


def _subpaths(d):
    """Chain a drawing's items into separate runs of page points."""
    runs, cur = [], []
    def start(p):
        nonlocal cur
        if cur and np.hypot(cur[-1][0] - p.x, cur[-1][1] - p.y) < 1e-3:
            return
        if len(cur) > 1:
            runs.append(cur)
        cur = [(p.x, p.y)]
    for it in d["items"]:
        op = it[0]
        if op == "l":
            start(it[1]); cur.append((it[2].x, it[2].y))
        elif op == "c":
            start(it[1]); cur += [tuple(q) for q in _bezier(*it[1:5])]
        elif op == "re":
            r = it[1]
            if len(cur) > 1: runs.append(cur)
            runs.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)]); cur = []
        elif op == "qu":
            q = it[1]
            if len(cur) > 1: runs.append(cur)
            runs.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y), (q.ul.x, q.ul.y)]); cur = []
    if len(cur) > 1:
        runs.append(cur)
    return runs


def read_styles(src, min_len_px=6.0):
    """Drawn paths of a PDF source, grouped by style, in the source's pixel space,
    keeping only what falls on the image (the map), not the page margins."""
    import pymupdf
    if src.kind != "pdf":
        return []
    page = pymupdf.open(src.path)[src.page_index]
    h, w = src.image.shape[:2]
    groups = {}
    for d in page.get_drawings():
        stroke, fill = d.get("color"), d.get("fill")
        width = round(float(d.get("width") or 0), 1)
        if not stroke and not fill:
            continue
        for run in _subpaths(d):
            a = np.array(run, float)
            px, py = src.page_to_px(a[:, 0], a[:, 1])
            pts = np.column_stack([px, py])
            inside = (pts[:, 0] >= -1) & (pts[:, 0] <= w + 1) & (pts[:, 1] >= -1) & (pts[:, 1] <= h + 1)
            if not inside.any():
                continue
            length = np.hypot(*np.diff(pts, axis=0).T).sum()
            if length < min_len_px:
                continue
            closed = np.hypot(*(pts[0] - pts[-1])) < 1e-6 * max(w, h) + 0.5 or d.get("closePath")
            kind = "polygon" if (fill or closed) and len(pts) >= 4 else "line"
            key = (_hex(stroke), _hex(fill) if fill else None, width if stroke else 0)
            if key not in groups:
                base = colour_name(stroke or fill)
                lab = (f"{base.capitalize()} line {width:g} pt" if stroke and not fill
                       else f"{colour_name(fill).capitalize()} fill" + (f", {base} edge" if stroke else ""))
                groups[key] = Style(key, lab, key[0], key[1], width)
            groups[key].paths.append((kind, pts))
    styles = sorted(groups.values(), key=lambda s: -len(s.paths))
    # same label twice (e.g. two near-identical reds): number them
    seen = {}
    for s in styles:
        seen[s.label] = seen.get(s.label, 0) + 1
        if seen[s.label] > 1:
            s.label += f" ({seen[s.label]})"
    return styles


def nearest_style(styles, x, y, tol_px):
    """The style whose drawn path passes closest to (x, y), within tol_px."""
    from shapely.geometry import Point, LineString
    p, best = Point(x, y), (None, tol_px)
    for s in styles:
        for kind, pts in s.paths:
            if len(pts) < 2:
                continue
            d = LineString(pts).distance(p)
            if d < best[1]:
                best = (s, d)
    return best[0]


def style_geometries(style, clip_wh):
    """Shapely geometries (pixel space) for a style, clipped to the image and
    with touching line pieces joined into longer lines."""
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import linemerge, unary_union
    frame = box(0, 0, *clip_wh)
    polys, lines = [], []
    for kind, pts in style.paths:
        if kind == "polygon":
            g = Polygon(pts).buffer(0)
            if not g.is_empty:
                polys.append(g.intersection(frame))
        else:
            lines.append(LineString(pts).intersection(frame))
    out = [g for g in polys if not g.is_empty and g.area > 1]
    if lines:
        u = unary_union([l for l in lines if not l.is_empty])
        merged = linemerge(u) if u.geom_type == "MultiLineString" else u
        parts = getattr(merged, "geoms", [merged])
        out += [l for l in parts if l.length > 1]
    return out
