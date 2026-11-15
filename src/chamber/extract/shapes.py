"""Turn masks into clean polygons, square up buildings, and snap lines to roads."""
from __future__ import annotations
import heapq
import numpy as np


# ---------------------------------------------------------------- masks
def mask_to_polygon(mask, x0=0, y0=0, simplify_px=1.5, open_px=3):
    """Largest outline in a boolean mask -> shapely Polygon in image px (or None)."""
    import cv2
    from shapely.geometry import Polygon
    m = mask.astype(np.uint8)
    if open_px:
        k = np.ones((open_px, open_px), np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    if cv2.contourArea(c) < 9:
        return None
    # contour points are pixel indices; +0.5 puts them on pixel centres, so
    # outlines line up with the image (pixel 0 spans 0..1)
    c = cv2.approxPolyDP(c, simplify_px, True)[:, 0, :].astype(float) + 0.5
    if len(c) < 3:
        return None
    p = Polygon(c + [x0, y0]).buffer(0)
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda g: g.area)
    return p if not p.is_empty else None


# ---------------------------------------------------------------- buildings
def square_up(poly, tol_px=2.0):
    """Building-like outline: a rectangle when it nearly is one, otherwise
    straight walls at right angles. Returns the input if squaring would
    change the area by more than 20%."""
    from shapely import affinity
    from shapely.geometry import Polygon
    if poly is None or poly.is_empty:
        return poly
    mrr = poly.minimum_rotated_rectangle
    if mrr.area > 0 and poly.area / mrr.area >= 0.86:
        # the bounding rectangle sits on the outermost bumps of a ragged edge:
        # shrink it about its centre until it holds the same area as the outline
        f = (poly.area / mrr.area) ** 0.5
        return affinity.scale(mrr, f, f, origin=mrr.centroid)
    # rotate so the walls run along x/y
    c = np.array(mrr.exterior.coords)
    e = c[1] - c[0]
    ang = np.degrees(np.arctan2(e[1], e[0]))
    org = poly.centroid
    r = affinity.rotate(poly, -ang, origin=org).simplify(tol_px)
    pts = np.array(r.exterior.coords)[:-1]
    if len(pts) < 4:
        return poly
    # classify edges as horizontal/vertical, merge runs, rebuild corners
    n = len(pts)
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    cls = ["h" if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else "v" for a, b in edges]
    runs = []
    for (a, b), k in zip(edges, cls):
        if runs and runs[-1][0] == k:
            runs[-1][1].extend([a, b])
        else:
            runs.append([k, [a, b]])
    if len(runs) > 1 and runs[0][0] == runs[-1][0]:
        runs[0][1].extend(runs.pop()[1])
    if len(runs) < 4 or len(runs) % 2:
        return poly
    lines = []
    for k, ps in runs:
        ps = np.array(ps)
        lines.append((k, ps[:, 1].mean() if k == "h" else ps[:, 0].mean()))
    corners = []
    for i in range(len(lines)):
        (k1, v1), (k2, v2) = lines[i], lines[(i + 1) % len(lines)]
        corners.append((v2, v1) if k1 == "h" else (v1, v2))
    q = Polygon(corners).buffer(0)
    if q.is_empty or q.geom_type != "Polygon":
        return poly
    q = affinity.rotate(q, ang, origin=org)
    return q if abs(q.area - poly.area) <= 0.2 * poly.area else poly


# ---------------------------------------------------------------- lines
def _dijkstra(cost, a, b):
    """Cheapest 8-connected path on a cost grid from a to b (row, col)."""
    H, W = cost.shape
    dist = np.full(cost.shape, np.inf); prev = -np.ones(cost.shape, np.int64)
    dist[a] = 0.0; heap = [(0.0, a[0], a[1])]
    steps = [(-1, -1, 1.4142), (-1, 0, 1), (-1, 1, 1.4142), (0, -1, 1), (0, 1, 1), (1, -1, 1.4142), (1, 0, 1), (1, 1, 1.4142)]
    while heap:
        d, r, c = heapq.heappop(heap)
        if (r, c) == b:
            break
        if d > dist[r, c]:
            continue
        cc = cost[r, c]
        for dr, dc, s in steps:
            rr, c2 = r + dr, c + dc
            if 0 <= rr < H and 0 <= c2 < W:
                nd = d + s * 0.5 * (cc + cost[rr, c2])
                if nd < dist[rr, c2]:
                    dist[rr, c2] = nd; prev[rr, c2] = r * W + c; heapq.heappush(heap, (nd, rr, c2))
    path, i = [], b[0] * W + b[1]
    while i >= 0:
        path.append(divmod(i, W))
        if path[-1] == a:
            break
        i = prev[path[-1]]
    return path[::-1]


def _chaikin(pts, n=2):
    for _ in range(n):
        if len(pts) < 3:
            break
        q = 0.75 * pts[:-1] + 0.25 * pts[1:]; r = 0.25 * pts[:-1] + 0.75 * pts[1:]
        pts = np.vstack([pts[:1], np.column_stack([q, r]).reshape(-1, 2), pts[-1:]])
    return pts


def snap_line(image, clicks, gsd=None, step_m=0.25, smooth=True, pull=0.45):
    """Clicks along a road/stream/path -> a line that follows it.

    Cost: colour distance from what's under the clicks (CIELAB), lowered toward
    the middle of the matching strip so the line rides the centre instead of
    hugging an edge or a shadow, plus a pull toward the straight line between
    clicks (pull 0 = follow colour only, 1 = straight lines). Works on a downsampled grid for speed.
    Returns a shapely LineString in image px."""
    import cv2
    from shapely.geometry import LineString
    H, W = image.shape[:2]
    f = min(1.0, gsd / step_m) if gsd else min(1.0, 1500 / max(H, W))
    clicks = np.asarray(clicks, float)
    out = [clicks[0]]
    for a, b in zip(clicks[:-1], clicks[1:]):
        seg_len = np.hypot(*(b - a))
        pad = max(40 / f, 0.5 * seg_len)
        x0, y0 = int(max(0, min(a[0], b[0]) - pad)), int(max(0, min(a[1], b[1]) - pad))
        x1, y1 = int(min(W, max(a[0], b[0]) + pad)), int(min(H, max(a[1], b[1]) + pad))
        crop = image[y0:y1, x0:x1]
        small = cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else crop
        lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
        ga = (int((a[1] - y0) * f), int((a[0] - x0) * f)); gb = (int((b[1] - y0) * f), int((b[0] - x0) * f))
        ga = (min(ga[0], lab.shape[0] - 1), min(ga[1], lab.shape[1] - 1)); gb = (min(gb[0], lab.shape[0] - 1), min(gb[1], lab.shape[1] - 1))
        ref = np.vstack([lab[max(0, r - 3):r + 4, max(0, c - 3):c + 4].reshape(-1, 3) for r, c in (ga, gb)]).mean(0)
        dist = cv2.GaussianBlur(np.linalg.norm(lab - ref, axis=2), (0, 0), 2)
        thr = max(12.0, np.percentile(dist, 30))
        like = (dist < thr).astype(np.uint8)
        dt = cv2.distanceTransform(like, cv2.DIST_L2, 3)
        centre = dt / (dt.max() + 1e-6)
        # stay near the straight line between the two clicks: the line follows
        # gentle bends; for sharp bends the user adds a click
        rr, cc = np.mgrid[0:lab.shape[0], 0:lab.shape[1]]
        ab = np.array(gb, float) - np.array(ga, float); L2 = max(ab @ ab, 1.0)
        t = np.clip(((rr - ga[0]) * ab[0] + (cc - ga[1]) * ab[1]) / L2, 0, 1)
        dev = np.hypot(rr - (ga[0] + t * ab[0]), cc - (ga[1] + t * ab[1])) / max(np.sqrt(L2) * 0.25, 8)
        cost = (1 / (1 + np.exp(-(dist - thr) / 4)) + 0.5 * (1 - centre)) * (1 - pull) + pull * dev ** 2 + 0.02
        path = _dijkstra(cost, ga, gb)
        pts = np.array([(c / f + x0, r / f + y0) for r, c in path], float)
        out.extend(pts[1:-1]); out.append(b)
    tol = (0.4 / gsd) if gsd else 2.0
    pts = np.array(LineString(out).simplify(tol * 2).coords)     # drop grid stair-steps
    if smooth and len(pts) > 2:
        pts = _chaikin(pts, 3)
    return LineString(pts).simplify(tol * 0.25)
