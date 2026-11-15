"""'Find similar': after you keep a few features of one kind, look for more that
look like them, and offer each one for Accept / Reject.

How: the model's encoder already describes every 16 x 16 patch of a window as
a 256-number vector. The kept features give an average vector (a prototype);
patches close to it are candidates. Each candidate's peak becomes a click,
the click becomes an outline, and outlines that are the wrong size or
overlap what you already have are dropped. No training, no internet.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass
class Candidate:
    poly: object          # shapely Polygon, image px
    point: tuple          # the click it came from
    score: float          # model confidence
    likeness: float       # 0..1 similarity to the examples


def _cells_inside(poly, win, scale_cell):
    """(row, col) embedding cells whose centres fall inside poly."""
    from shapely import contains_xy
    rr, cc = np.mgrid[0:64, 0:64]
    cx = win.x0 + (cc + 0.5) * scale_cell
    cy = win.y0 + (rr + 0.5) * scale_cell
    inside = contains_xy(poly, cx.ravel(), cy.ravel()).reshape(64, 64)
    if not inside.any():                                  # tiny feature: nearest cell
        p = poly.representative_point()
        r = int(np.clip((p.y - win.y0) / scale_cell, 0, 63)); c = int(np.clip((p.x - win.x0) / scale_cell, 0, 63))
        inside[r, c] = True
    return inside


def prototype(seg, examples):
    vecs, own = [], []
    for poly in examples:
        p = poly.representative_point()
        win = seg.window_for([p.x], [p.y])
        e, cell = seg.embedding_grid(win)
        m = _cells_inside(poly, win, cell)
        vecs.append(e[m])
    allv = np.vstack(vecs)
    proto = allv.mean(0); proto /= np.linalg.norm(proto) + 1e-6
    own = float(np.median(allv @ proto))
    return proto, own


def find_similar(seg, examples, existing=(), scope="all", strictness=0.88,
                 progress=None, cancelled=lambda: False, max_n=60, proto=None):
    """examples: shapely polygons (image px) of one kind. Returns Candidates.
    proto: (vector, own_similarity) from another image's examples, to search a
    second file with the first file's examples (examples then only set the size)."""
    import cv2
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    from .shapes import mask_to_polygon
    if not examples:
        return []
    cross = proto is not None
    proto, own = proto if cross else prototype(seg, examples)
    thr = own * strictness
    areas = [p.area for p in examples]
    lo, hi = 0.3 * min(areas), 3.0 * max(areas)
    taken = list(existing) + ([] if cross else list(examples))
    tree = STRtree(taken) if taken else None
    if scope == "all":
        wins = seg.windows_all()
    else:
        p = examples[-1].representative_point(); w = seg.window_for([p.x], [p.y]); wins = [(w.x0, w.y0)]
    out = []
    for i, (x0, y0) in enumerate(wins):
        if cancelled() or len(out) >= max_n:
            break
        win = seg.encode(x0, y0)
        e, cell = seg.embedding_grid(win)
        sim = e @ proto
        # only the part of the padded 1024 square that holds image
        valid = int(np.ceil(win.size * win.scale / 16))
        sim[valid:, :] = -1; sim[:, valid:] = -1
        n, lab, stats, _ = cv2.connectedComponentsWithStats((sim > thr).astype(np.uint8), connectivity=8)
        for k in range(1, n):
            comp = lab == k
            r, c = np.unravel_index(np.argmax(np.where(comp, sim, -2)), sim.shape)
            x, y = x0 + (c + 0.5) * cell, y0 + (r + 0.5) * cell
            pt = Point(x, y)
            if tree is not None and len(tree.query(pt, predicate="intersects")):
                continue
            res = seg.predict([(x, y)], [1], window=win)
            best = None
            for m, s in zip(res.masks, res.scores):
                a = m.sum()
                if lo <= a <= hi and s >= 0.80:
                    best = (m, s); break
            if best is None:
                continue
            poly = mask_to_polygon(best[0], win.x0, win.y0)
            if poly is None:
                continue
            if tree is not None:
                hit = tree.query(poly, predicate="intersects")
                if any(poly.intersection(taken[j]).area > 0.2 * min(poly.area, taken[j].area) for j in hit):
                    continue
            if any(poly.intersection(o.poly).area > 0.2 * min(poly.area, o.poly.area) for o in out):
                continue
            like = float(np.clip((sim[r, c] - thr) / max(1 - thr, 1e-6), 0, 1))
            out.append(Candidate(poly, (x, y), float(best[1]), like))
        if progress:
            progress(i + 1, len(wins))
    out.sort(key=lambda o: -(o.score * (0.5 + o.likeness)))
    return out[:max_n]
