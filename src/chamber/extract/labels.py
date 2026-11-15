"""Text printed on the map, as points: place names, landmark names, numbers.

PDF with real text: read straight from the page (exact).
Images and flattened PDFs: offline OCR (the same engine the batch mode uses).
Grid labels around the frame are left out: they place the map, they aren't on it.
"""
from __future__ import annotations
import numpy as np


def _is_grid(t):
    from .gridref import _value
    return _value(t) is not None


def from_pdf(src):
    import pymupdf
    page = pymupdf.open(src.path)[src.page_index]
    h, w = src.image.shape[:2]
    out = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            t = " ".join(s["text"].strip() for s in line["spans"] if s["text"].strip())
            if not t or _is_grid(t):
                continue
            x0, y0, x1, y1 = line["bbox"]
            x, y = src.page_to_px((x0 + x1) / 2, (y0 + y1) / 2)
            if 0 <= x < w and 0 <= y < h:
                out.append((t, float(x), float(y), 1.0))
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
            found.append((t, tx + sum(bx) / 4, ty + sum(by) / 4, float(conf)))
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
