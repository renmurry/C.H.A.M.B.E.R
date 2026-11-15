"""Text printed on the map, as points: place names, landmark names, numbers.

PDF with real text: read straight from the page (exact).
Images and flattened PDFs: offline OCR (the same engine the batch mode uses).
Grid labels around the frame are left out: they place the map, they aren't on it.
"""
from __future__ import annotations
import math
from typing import NamedTuple
import numpy as np


class Label(NamedTuple):
    text: str
    x: float              # centre, image px
    y: float
    conf: float
    angle: float = 0.0    # reading direction, degrees in image axes (0 = left to right)
    height: float = 12.0  # letter height, px
    width: float = 0.0    # length of the text, px
    parts: tuple = ()     # filled in by bind.merge_stacked


def _is_grid(t):
    from .gridref import _value
    return _value(t) is not None


def from_pdf(src):
    import pymupdf
    page = pymupdf.open(src.path)[src.page_index]
    h, w = src.image.shape[:2]
    ax, ay = src.page_to_px(0, 0); bx, by = src.page_to_px(1, 0)
    k = math.hypot(bx - ax, by - ay)                 # image px per PDF point
    out = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            t = " ".join(s["text"].strip() for s in spans)
            if not t or _is_grid(t):
                continue
            x0, y0, x1, y1 = line["bbox"]
            x, y = src.page_to_px((x0 + x1) / 2, (y0 + y1) / 2)
            if 0 <= x < w and 0 <= y < h:
                c, s_ = line.get("dir", (1.0, 0.0))
                size = max(s["size"] for s in spans) * k
                length = max(abs(x1 - x0), abs(y1 - y0)) * k
                out.append(Label(t, float(x), float(y), 1.0, math.degrees(math.atan2(s_, c)), size * 0.75, length))
    return out


def from_ocr(image, min_conf=0.6, progress=None):
    """OCR in overlapping tiles so small map text isn't lost. Returns
    (text, x, y, confidence) or None when the OCR engine isn't installed."""
    from ..ocr import _engine, _clean
    eng = _engine()
    if eng is None:
        return None
    h, w = image.shape[:2]
    T, O = 1600, 200
    xs = list(range(0, max(w - T, 0) + 1, T - O)) or [0]
    ys = list(range(0, max(h - T, 0) + 1, T - O)) or [0]
    if xs[-1] + T < w: xs.append(w - T)
    if ys[-1] + T < h: ys.append(h - T)
    found, n = [], len(xs) * len(ys)
    for i, (ty, tx) in enumerate([(y, x) for y in ys for x in xs]):
        res, _ = eng(np.ascontiguousarray(image[ty:ty + T, tx:tx + T][..., ::-1]))
        for box, txt, conf in res or []:
            t = _clean(txt)
            if not t or float(conf) < min_conf or _is_grid(t):
                continue
            bx = [p[0] for p in box]; by = [p[1] for p in box]
            (x0, y0), (x1, y1), _, (x3, y3) = box[:4]
            found.append(Label(t, tx + sum(bx) / 4, ty + sum(by) / 4, float(conf),
                               math.degrees(math.atan2(y1 - y0, x1 - x0)),
                               math.hypot(x3 - x0, y3 - y0) * 0.75, math.hypot(x1 - x0, y1 - y0)))
        if progress:
            progress(i + 1, n)
    # the same word read twice in an overlap: keep the surer one
    keep = []
    for f in sorted(found, key=lambda f: -f[3]):
        if not any(k[0] == f[0] and abs(k[1] - f[1]) < 40 and abs(k[2] - f[2]) < 40 for k in keep):
            keep.append(f)
    return keep


def read_labels(src, progress=None):
    if src.kind == "pdf":
        got = from_pdf(src)
        if got:
            return got
    return from_ocr(src.image, progress=progress) or []
