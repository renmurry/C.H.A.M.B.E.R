"""Road Brush and Paint the Map Red: learn what roads look like from your
strokes, then trace them as a network.

  Road Brush         paint along a road (or stream, path...) with a brush about
                     as wide as it. Each stroke is a "this is road" example.
  Paint the Map Red  paint over things that are NOT road. Close a red stroke
                     into a loop (circle, box, any shape) and everything inside
                     counts as not road too.

Learning: every cell of a grid over the image (about 0.25 m on drone images)
is described by the model encoder's features (squeezed to a few numbers),
colour and texture. A small linear model is fitted to your strokes; it is
refitted in a fraction of a second after every stroke.

Extraction: road cells -> cleaned mask -> one-pixel skeleton -> a network:
lines meet exactly at junctions, short dead-end stubs are dropped, small gaps
(a tree over the road) are bridged. Each segment gets a centreline and a
surface polygon, either measured from the image or a fixed width.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

MAX_CELLS = 700_000
PCA_DIMS = 24


@dataclass
class Stroke:
    kind: str                 # "road" | "red"
    pts: list                 # [(x, y)] image px
    radius_px: float

    def closed(self):
        if self.kind != "red" or len(self.pts) < 4:
            return False
        p = np.asarray(self.pts, float)
        span = np.ptp(p, axis=0).max()
        return np.hypot(*(p[0] - p[-1])) < max(3 * self.radius_px, 0.12 * span)


@dataclass
class Segment:
    line: object              # shapely LineString, image px
    surface: object           # shapely Polygon, image px
    width_m: float            # measured median width (metres; px if unplaced)
    painted: bool = False     # came straight from a stroke
    score: float = 1.0        # mean road probability along it


class RoadLearner:
    def __init__(self, image, gsd=None, progress=None):
        import cv2
        self.image = image
        self.gsd = gsd
        H, W = image.shape[:2]
        f = min(1.0, (gsd / 0.25) if gsd else 1.0, (MAX_CELLS / (H * W)) ** 0.5)
        self.f = f                                    # grid cells per image px
        self.gh, self.gw = max(8, int(H * f)), max(8, int(W * f))
        self.cell_m = (gsd / f) if gsd else None
        self.progress = progress
        self.feat = None
        self.prob = None
        self.agg = "mean"
        self.w = None

    # ---------------- features
    def _raw_grids(self, image, step0, steps):
        """Encoder features for one orientation of the image: per window, a 64x64x256 grid."""
        from .sam import Segmenter
        H, W = image.shape[:2]
        # coarse windows (~150 m on drone images): roads are big; this keeps it to a few windows
        size = int(np.clip((150 / self.gsd) if self.gsd else max(H, W) / 2, 1024, max(H, W)))
        seg = Segmenter(image, self.gsd, window_px=size, cache=2)
        wins = seg.windows_all()
        grids = []
        for i, (x0, y0) in enumerate(wins):
            win = seg.encode(x0, y0)
            e, cell = seg.embedding_grid(win)
            n = int(np.ceil(win.size * win.scale / 16))
            grids.append((x0, y0, cell, np.ascontiguousarray(e[:n, :n])))
            if self.progress:
                self.progress(step0 + i + 1, steps)
        return grids, len(wins)

    def _place(self, grids, gh, gw, mu, P):
        import cv2
        out = np.zeros((gh, gw, PCA_DIMS), np.float32); cnt = np.zeros((gh, gw, 1), np.float32)
        for x0, y0, cell, e in grids:
            z = ((e.reshape(-1, 256) - mu) @ P).reshape(e.shape[0], e.shape[1], PCA_DIMS).astype(np.float32)
            side = max(1, int(round(e.shape[0] * cell * self.f)))
            up = cv2.resize(z, (side, side), interpolation=cv2.INTER_LINEAR)
            gx0, gy0 = int(x0 * self.f), int(y0 * self.f)
            hh, ww = min(side, gh - gy0), min(side, gw - gx0)
            if hh > 0 and ww > 0:
                out[gy0:gy0 + hh, gx0:gx0 + ww] += up[:hh, :ww]; cnt[gy0:gy0 + hh, gx0:gx0 + ww] += 1
        return out / np.maximum(cnt, 1)

    def _embeddings(self):
        """Encoder features squeezed to PCA_DIMS numbers per cell, for the image as
        it is and turned a quarter turn (so a road learnt running east-west is also
        recognised running north-south). Returns (as_is, turned_back)."""
        g0, n0 = self._raw_grids(self.image, 0, 1)
        rot = np.ascontiguousarray(np.rot90(self.image, 1))
        g1, _ = self._raw_grids(rot, n0, 2 * n0 + 1)
        sample = np.vstack([g[3].reshape(-1, 256) for g in g0 + g1])
        rng = np.random.default_rng(0)
        if len(sample) > 20000:
            sample = sample[rng.choice(len(sample), 20000, replace=False)]
        mu = sample.mean(0)
        _, _, vt = np.linalg.svd(sample - mu, full_matrices=False)
        P = vt[:PCA_DIMS].T
        e0 = self._place(g0, self.gh, self.gw, mu, P)
        e1 = self._place(g1, self.gw, self.gh, mu, P)          # rotated image: grid is gw x gh
        e1 = np.ascontiguousarray(np.rot90(e1, -1))
        return e0, e1

    def prepare(self):
        """Compute the per-cell features once (the slow part: a few seconds)."""
        import cv2
        if self.feat is not None:
            return
        small = cv2.resize(self.image, (self.gw, self.gh), interpolation=cv2.INTER_AREA)
        lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
        L = lab[..., 0]
        mu = cv2.blur(L, (5, 5)); sd = np.sqrt(np.maximum(cv2.blur(L * L, (5, 5)) - mu * mu, 0))
        grad = cv2.blur(np.hypot(cv2.Sobel(L, cv2.CV_32F, 1, 0), cv2.Sobel(L, cv2.CV_32F, 0, 1)), (5, 5))
        try:
            e0, e1 = self._embeddings()
        except Exception:
            e0 = e1 = np.zeros((self.gh, self.gw, 0), np.float32)   # no model: colour and texture only
        rest = np.concatenate([cv2.blur(lab, (7, 7)), sd[..., None], grad[..., None]], axis=2)
        X0 = np.concatenate([e0, rest], axis=2).reshape(-1, e0.shape[2] + rest.shape[2]).astype(np.float32)
        X1 = np.concatenate([e1, rest], axis=2).reshape(-1, e1.shape[2] + rest.shape[2]).astype(np.float32)
        both = np.vstack([X0, X1])
        self.mean, self.std = both.mean(0), both.std(0) + 1e-6
        self.feat = (X0 - self.mean) / self.std
        self.feat_turned = (X1 - self.mean) / self.std
        if self.progress:
            self.progress(1, 1)

    # ---------------- strokes -> masks
    def masks(self, strokes):
        import cv2
        pos = np.zeros((self.gh, self.gw), np.uint8); neg = np.zeros_like(pos)
        for s in strokes:
            p = (np.asarray(s.pts, float) * self.f).astype(np.int32)
            th = max(1, int(round(2 * s.radius_px * self.f)))
            m = pos if s.kind == "road" else neg
            if len(p) == 1:
                cv2.circle(m, tuple(p[0]), max(1, th // 2), 1, -1)
            else:
                cv2.polylines(m, [p], False, 1, thickness=th)
            if s.closed():
                cv2.fillPoly(m, [p], 1)                # a closed red loop: the inside is not road
        pos[neg > 0] = 0
        return pos.astype(bool), neg.astype(bool)

    # ---------------- learning
    def learn(self, strokes):
        """Fit road / not-road to the strokes; returns the road probability grid."""
        import cv2
        self.prepare()
        pos, neg = self.masks(strokes)
        if not pos.any():
            self.prob = None
            return None
        rng = np.random.default_rng(0)
        pi = np.flatnonzero(pos.ravel()); ni = np.flatnonzero(neg.ravel())
        # cells far from any road stroke act as mild "not road" examples, but only
        # those that look clearly unlike the painted road: an unpainted road
        # elsewhere must not be taught as "not road"
        far = np.flatnonzero((cv2.dilate(pos.astype(np.uint8), np.ones((41, 41), np.uint8)) == 0).ravel())
        if len(far):
            cen = self.feat[pi].mean(0)
            dpos = np.linalg.norm(self.feat[pi[:5000]] - cen, axis=1)
            cand = far if len(far) <= 200000 else rng.choice(far, 200000, replace=False)
            dfar = np.linalg.norm(self.feat[cand] - cen, axis=1)
            far = cand[dfar > np.percentile(dpos, 97) * 1.25]
        bg = rng.choice(far, size=min(len(far), 3 * len(pi), 40000), replace=False) if len(far) else far
        if len(pi) > 30000:
            pi = rng.choice(pi, 30000, replace=False)
        if len(ni) > 30000:
            ni = rng.choice(ni, 30000, replace=False)
        idx = np.concatenate([pi, ni, bg])
        y = np.concatenate([np.ones(len(pi)), -np.ones(len(ni) + len(bg))])
        w = np.concatenate([np.full(len(pi), 1 / len(pi)), np.full(len(ni), 1 / max(len(ni), 1)),
                            np.full(len(bg), (0.4 if len(ni) else 1.0) / max(len(bg), 1))])
        # every example twice: as seen, and as seen with the image turned a quarter
        F = np.vstack([self.feat[idx], self.feat_turned[idx]])
        A = np.hstack([F, np.ones((len(F), 1), np.float32)])
        y = np.concatenate([y, y]); w = np.concatenate([w, w])
        Aw = A * w[:, None]
        sol = np.linalg.solve(A.T @ Aw + 1e-3 * np.eye(A.shape[1]), Aw.T @ y)
        z0, z1 = self.feat @ sol[:-1], self.feat_turned @ sol[:-1]
        z = (np.maximum(z0, z1) if self.agg == "max" else 0.5 * (z0 + z1)) + sol[-1]
        prob = 1 / (1 + np.exp(-3 * z.reshape(self.gh, self.gw)))
        prob = cv2.GaussianBlur(prob.astype(np.float32), (0, 0), 1.2)
        prob[neg] = 0.0
        self.prob, self._pos, self._neg = prob, pos, neg
        return prob

    # ---------------- extraction
    def road_mask(self, scope="grow", hi=0.6, lo=0.4):
        """Hysteresis: cells above `lo` count as road when they connect to cells
        above `hi` (or to your strokes). Weak road joined to sure road is road."""
        import cv2
        cell = self.cell_m or (1 / self.f)
        k = lambda metres: max(3, int(round(metres / cell)) | 1)
        weak = (self.prob > lo).astype(np.uint8)
        strong = (self.prob > hi) | self._pos
        nw, wl = cv2.connectedComponents(weak, connectivity=8)
        keep = set(np.unique(wl[strong])) - {0}
        m = np.isin(wl, list(keep)).astype(np.uint8)
        m[self._pos] = 1                               # what you painted is road, full stop
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k(0.8), k(0.8))))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k(2.5), k(2.5))))
        # cars, shadows, a median strip: holes up to ~20 x 20 m are part of the road
        cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hier is not None:
            max_hole = (20 / cell) ** 2
            for c, h in zip(cs, hier[0]):
                if h[3] >= 0 and cv2.contourArea(c) < max_hole:
                    cv2.drawContours(m, [c], -1, 1, -1)
        # a smooth edge gives a clean skeleton (no whiskers at every bump)
        m = (cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(1.0, 1.0 / cell)) > 0.5).astype(np.uint8)
        m[self._neg] = 0
        n, lab = cv2.connectedComponents(m, connectivity=8)
        if scope == "grow":                            # only what's joined to your strokes,
            ids = set(np.unique(lab[self._pos])) - {0}  # allowing small breaks (shade, a junction)
            base = np.isin(lab, list(ids)).astype(np.uint8)
            # weaker road-shaped pieces close to what's already found join too
            wm = cv2.morphologyEx(weak, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k(2.5), k(2.5))))
            wm[self._neg] = 0
            nW, wlab = cv2.connectedComponents(wm, connectivity=8)
            reach = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k(6.0), k(6.0)))
            taken = set()
            for _ in range(12):
                near = cv2.dilate(base, reach)
                new = {i for i in set(np.unique(wlab[near > 0])) - {0} - taken if self._roadlike(wlab == i, min_len_m=6)}
                if not new:
                    break
                taken |= new
                base = (base | np.isin(wlab, list(new))).astype(np.uint8)
            return base
        else:                                          # anything road-shaped
            ids = {k for k in range(1, n) if self._roadlike(lab == k)} | (set(np.unique(lab[self._pos])) - {0})
        return np.isin(lab, list(ids)).astype(np.uint8)

    def _roadlike(self, comp, min_len_m=12, min_elong=3.0):
        import cv2
        area = comp.sum()
        if area < 20:
            return False
        dt = cv2.distanceTransform(comp.astype(np.uint8), cv2.DIST_L2, 3)
        half = dt[comp].mean() + 1e-6
        length = area / (2 * half * 1.6)
        cell = self.cell_m or 1.0
        return length * cell >= min_len_m and length / (2 * half) >= min_elong

    def extract(self, strokes, scope="grow", spur_m=6.0, gap_m=8.0, strict=0.5):
        """Segments for everything found, plus the painted roads themselves."""
        import cv2
        if self.prob is None:
            self.learn(strokes)
        if self.prob is None:
            return []
        # strict 0 (looser) .. 1 (stricter) moves both thresholds together
        hi, lo = 0.5 + 0.2 * strict, 0.3 + 0.2 * strict
        m = self.road_mask(scope, hi, lo)
        dtm = cv2.distanceTransform(m, cv2.DIST_L2, 5)
        lines = network(thin(m), self.cell_m or 1.0, spur_m, gap_m, halfwidth=dtm)
        lines = [straight_exit(l, dtm, self.gw, self.gh) for l in lines]
        lines = t_junctions(lines, gap_m / (self.cell_m or 1.0))
        segs = []
        if lines:
            surfaces = split_surface(m, lines)
            dt = cv2.distanceTransform(m, cv2.DIST_L2, 5)
            for ln, surf in zip(lines, surfaces):
                c = np.asarray(ln.coords)
                ii = np.clip(c[:, 1].astype(int), 0, self.gh - 1); jj = np.clip(c[:, 0].astype(int), 0, self.gw - 1)
                width = float(np.median(dt[ii, jj])) * 2 * (self.cell_m or (1 / self.f))
                score = float(self.prob[ii, jj].mean())
                segs.append(Segment(self._to_px(ln), self._to_px(surf), width, False, score))
        # painted strokes that the network missed (e.g. cut by parked cars): follow the stroke
        from shapely.ops import unary_union
        net = unary_union([s.line for s in segs]) if segs else None
        for s in strokes:
            if s.kind != "road" or len(s.pts) < 2:
                continue
            from shapely.geometry import LineString
            st = LineString(s.pts)
            if net is not None and st.difference(net.buffer(s.radius_px * 1.5)).length < 0.15 * st.length:
                continue
            ln = recentre(st, m, self.f, search=max(4.0, s.radius_px * self.f * 1.5))
            width = 2 * s.radius_px * (self.gsd or 1)
            segs.append(Segment(ln, ln.buffer(s.radius_px, cap_style=2), width, True, 1.0))
        return segs

    def _to_px(self, g):
        import shapely
        return shapely.transform(g, lambda c: (c + 0.5) / self.f)


# ---------------------------------------------------------------- geometry helpers
def thin(img):
    """Zhang-Suen thinning (vectorised): a one-pixel-wide skeleton."""
    I = (img > 0).astype(np.uint8).copy()
    while True:
        changed = 0
        for step in (0, 1):
            P = np.pad(I, 1)
            p2, p3, p4, p5 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:]
            p6, p7, p8, p9 = P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(nb)
            seq = nb + [p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            c = ((p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)) if step == 0 else ((p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0))
            rm = (I == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            I[rm] = 0; changed += int(rm.sum())
        if not changed:
            return I


_N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def network(sk, cell_m, spur_m=6.0, gap_m=8.0, halfwidth=None):
    """Skeleton -> list of LineStrings (grid coords) meeting exactly at junctions.
    halfwidth: distance-to-edge grid; a dead-end stub shorter than about the road's
    width where it branches off is just a bump in the edge, and is dropped."""
    import cv2
    from shapely.geometry import LineString, Point
    sk = (sk > 0).astype(np.uint8)
    if not sk.any():
        return []
    deg = cv2.filter2D(sk, -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT) * sk - sk
    junc = ((deg >= 3) & (sk > 0)).astype(np.uint8)
    nj, jl, _, jc = cv2.connectedComponentsWithStats(junc, connectivity=8)
    jl = jl.astype(np.int32)
    centre = {k: (float(jc[k][0]), float(jc[k][1])) for k in range(1, nj)}
    chains = sk.copy(); chains[junc > 0] = 0
    nc, cl = cv2.connectedComponents(chains, connectivity=8)
    H, W = sk.shape
    edges = []                                      # [pts list (x, y), start_node, end_node]
    for k in range(1, nc):
        ys, xs = np.nonzero(cl == k)
        pix = set(zip(ys.tolist(), xs.tolist()))
        nb = lambda p: [(p[0] + dy, p[1] + dx) for dy, dx in _N8 if (p[0] + dy, p[1] + dx) in pix]
        ends = [p for p in pix if len(nb(p)) <= 1]
        start = ends[0] if ends else next(iter(pix))
        order, seen, cur = [start], {start}, start
        while True:
            nxt = [q for q in nb(cur) if q not in seen]
            if not nxt:
                break
            cur = min(nxt, key=lambda q: abs(q[0] - cur[0]) + abs(q[1] - cur[1])); order.append(cur); seen.add(cur)
        def touching(p):
            for dy, dx in _N8:
                y, x = p[0] + dy, p[1] + dx
                if 0 <= y < H and 0 <= x < W and jl[y, x]:
                    return int(jl[y, x])
            return 0
        a, b = touching(order[0]), touching(order[-1])
        pts = [(x, y) for y, x in order]
        if a: pts = [centre[a]] + pts
        if b: pts = pts + [centre[b]]
        if len(pts) >= 2:
            edges.append([pts, a, b])
    # drop short dead-end stubs, then fuse edges through junctions left with two edges
    def length(pts):
        p = np.asarray(pts); return float(np.hypot(*np.diff(p, axis=0).T).sum()) * cell_m
    for _ in range(3):
        degree = {}
        for _p, a, b in edges:
            for n in (a, b):
                if n: degree[n] = degree.get(n, 0) + 1
        keep = []
        for pts, a, b in edges:
            dead = (a == 0) != (b == 0)
            lim = spur_m
            if dead and halfwidth is not None:
                jx, jy = pts[0] if a else pts[-1]
                hw = halfwidth[min(int(jy), halfwidth.shape[0] - 1), min(int(jx), halfwidth.shape[1] - 1)]
                lim = max(spur_m, 2.2 * hw * cell_m)
            if dead and length(pts) < lim:
                continue
            if a == 0 and b == 0 and length(pts) < spur_m * 1.5:
                continue
            keep.append([pts, a, b])
        edges = keep
        # two junctions a few metres apart are really one junction
        for e in list(edges):
            pts, a, b = e
            if a and b and (a == b or length(pts) < 3.5):
                if e not in edges:
                    continue
                edges.remove(e)
                if a != b:
                    ca, cb = centre[a], centre[b]
                    mid = ((ca[0] + cb[0]) / 2, (ca[1] + cb[1]) / 2); centre[a] = mid
                    for f in edges:
                        if f[1] == b: f[1] = a; f[0] = [mid] + f[0][1:]
                        elif f[1] == a: f[0] = [mid] + f[0][1:]
                        if f[2] == b: f[2] = a; f[0] = f[0][:-1] + [mid]
                        elif f[2] == a: f[0] = f[0][:-1] + [mid]
        degree = {}
        for _p, a, b in edges:
            for n in (a, b):
                if n: degree[n] = degree.get(n, 0) + 1
        for n, d in degree.items():
            if d != 2:
                continue
            two = [e for e in edges if n in (e[1], e[2])]
            if len(two) != 2 or two[0] is two[1]:
                continue
            e1, e2 = two
            p1 = e1[0] if e1[2] == n else e1[0][::-1]
            o1 = e1[1] if e1[2] == n else e1[2]
            p2 = e2[0] if e2[1] == n else e2[0][::-1]
            o2 = e2[2] if e2[1] == n else e2[1]
            edges.remove(e1); edges.remove(e2)
            edges.append([p1 + p2[1:], o1, o2])
    lines = [LineString(p) for p, _a, _b in edges if len(p) >= 2]
    # bridge small gaps between free ends that point at each other
    free = []
    for i, (p, a, b) in enumerate(edges):
        if not a: free.append((i, np.asarray(p[0]), np.asarray(p[0]) - np.asarray(p[min(4, len(p) - 1)])))
        if not b: free.append((i, np.asarray(p[-1]), np.asarray(p[-1]) - np.asarray(p[max(-5, -len(p))])))
    used = set()
    for u in range(len(free)):
        for v in range(u + 1, len(free)):
            i, pi, di = free[u]; j, pj, dj = free[v]
            if i == j or u in used or v in used:
                continue
            gap = pj - pi; d = np.hypot(*gap) * cell_m
            if 0 < d < gap_m:
                g = gap / (np.hypot(*gap) + 1e-9)
                ok = np.dot(di / (np.hypot(*di) + 1e-9), g) > 0.5 and np.dot(dj / (np.hypot(*dj) + 1e-9), -g) > 0.5
                if ok:
                    lines.append(LineString([tuple(pi), tuple(pj)])); used |= {u, v}
    out = []
    for l in lines:
        s = smooth(l)
        if s.length * cell_m >= 2:
            out.append(s)
    return out


def straight_exit(line, halfwidth, W, H):
    """A road that leaves the image makes its skeleton bend toward a corner.
    Cut that bend off and run the line straight out to the edge instead."""
    from shapely.geometry import LineString
    p = np.asarray(line.coords, float)
    if len(p) < 4:
        return line
    def near_edge(q, hw):
        return min(q[0], q[1], W - 1 - q[0], H - 1 - q[1]) <= hw + 2
    for end in (0, 1):
        q = p if end == 1 else p[::-1]
        tip = q[-1]
        hw = halfwidth[min(int(tip[1]), H - 1), min(int(tip[0]), W - 1)]
        if not near_edge(tip, max(hw, 2)):
            continue
        # walk back until we're a road-width away from the edge
        k = len(q) - 1
        while k > 1 and near_edge(q[k], 1.2 * max(hw, 2)):
            k -= 1
        if k < 1:
            continue
        cut = np.hypot(*np.diff(q[k:], axis=0).T).sum() if k < len(q) - 1 else 0.0
        total = np.hypot(*np.diff(q, axis=0).T).sum()
        if cut > 3 * max(hw, 2) or cut > 0.2 * total:      # not a little hook: leave it alone
            continue
        d = q[k] - q[max(k - 3, 0)]
        n = np.hypot(*d)
        if n < 1e-6:
            continue
        d /= n
        ts = []
        for axis, lim in ((0, 0), (0, W - 1), (1, 0), (1, H - 1)):
            if abs(d[axis]) > 1e-9:
                t = (lim - q[k][axis]) / d[axis]
                if t > 0:
                    ts.append(t)
        if not ts:
            continue
        if min(ts) > 3 * max(hw, 2) + cut:                 # don't shoot off across open ground
            continue
        out = q[k] + d * min(ts)
        q = np.vstack([q[:k + 1], out])
        p = q if end == 1 else q[::-1]
    return LineString(p)


def t_junctions(lines, gap):
    """A line that stops just short of another (within `gap`) is joined to it,
    and the other line is split there, making a proper T junction."""
    from shapely.geometry import Point, LineString
    from shapely.ops import substring
    lines = list(lines)
    changed = True
    rounds = 0
    while changed and rounds < 20:
        changed = False; rounds += 1
        for i, li in enumerate(lines):
            for end in (0, -1):
                tip = Point(li.coords[end])
                # already connected to something?
                if any(j != i and lj.distance(tip) < 0.75 for j, lj in enumerate(lines)):
                    continue
                best = None
                for j, lj in enumerate(lines):
                    if j == i:
                        continue
                    d = lj.distance(tip)
                    if d < gap and (best is None or d < best[0]):
                        best = (d, j)
                if best is None:
                    continue
                j = best[1]; lj = lines[j]
                s = lj.project(tip); snap = lj.interpolate(s)
                c = list(li.coords)
                c = ([tuple(snap.coords[0])] + c) if end == 0 else (c + [tuple(snap.coords[0])])
                lines[i] = LineString(c)
                if 0.75 < s < lj.length - 0.75:                 # split the other line at the T
                    lines[j] = substring(lj, 0, s)
                    lines.append(substring(lj, s, lj.length))
                changed = True
                break
            if changed:
                break
    return lines


def _despike(p, max_turn=0.5):
    """Remove vertices where the line doubles back on itself (a V-shaped kink)."""
    p = list(map(tuple, p))
    k = 1
    while k < len(p) - 1:
        a, b, c = np.asarray(p[k - 1]), np.asarray(p[k]), np.asarray(p[k + 1])
        u, v = b - a, c - b
        nu, nv = np.hypot(*u), np.hypot(*v)
        if nu > 1e-9 and nv > 1e-9 and np.dot(u, v) / (nu * nv) < -max_turn:
            del p[k]; k = max(1, k - 1)
        else:
            k += 1
    return np.asarray(p, float)


def smooth(line, n=3, tol=0.6):
    """Chaikin smoothing that keeps both ends exactly where they are (junctions stay joined)."""
    from shapely.geometry import LineString
    p = _despike(np.asarray(line.coords, float))
    for _ in range(n):
        if len(p) < 3:
            break
        q = 0.75 * p[:-1] + 0.25 * p[1:]; r = 0.25 * p[:-1] + 0.75 * p[1:]
        p = np.vstack([p[:1], np.column_stack([q, r]).reshape(-1, 2)[1:-1], p[-1:]])
    return LineString(p).simplify(tol)


def split_surface(mask, lines):
    """The road surface, divided between segments: each cell goes to its nearest centreline."""
    import cv2
    from shapely.geometry import Polygon
    H, W = mask.shape
    seed = np.full((H, W), 255, np.uint8)
    ids = np.zeros((H, W), np.int32)
    for i, l in enumerate(lines, 1):
        cv2.polylines(seed, [np.asarray(l.coords, np.int32)], False, 0, 1)
        lm = np.zeros((H, W), np.uint8); cv2.polylines(lm, [np.asarray(l.coords, np.int32)], False, 1, 1)
        ids[lm > 0] = i
    _d, lab = cv2.distanceTransformWithLabels(seed, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(seed == 0)
    lut = np.zeros(lab.max() + 1, np.int32)
    lut[lab[ys, xs]] = ids[ys, xs]
    owner = lut[lab] * (mask > 0)
    out = []
    for i, l in enumerate(lines, 1):
        part = (owner == i).astype(np.uint8)
        part = cv2.morphologyEx(part, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        cs, _ = cv2.findContours(part, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cs:
            out.append(l.buffer(1.0)); continue
        c = max(cs, key=cv2.contourArea)
        c = cv2.approxPolyDP(c, 1.2, True)[:, 0, :].astype(float)
        p = Polygon(c).buffer(0) if len(c) >= 3 else l.buffer(1.0)
        if p.geom_type == "MultiPolygon":
            p = max(p.geoms, key=lambda g: g.area)
        out.append(p.buffer(1.0).buffer(-1.0) if not p.is_empty else l.buffer(1.0))
    return out


def recentre(stroke, mask, f, search=None):
    """Move a painted stroke onto the middle of the road surface where the road
    can be seen; keep it where it can't (cars, shade). Image px in and out."""
    import cv2
    from shapely.geometry import LineString
    pts = np.asarray(stroke.segmentize(max(stroke.length / 200, 2.0)).coords, float)
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    H, W = mask.shape
    out = []
    for i, p in enumerate(pts):
        a = pts[max(i - 2, 0)]; b = pts[min(i + 2, len(pts) - 1)]
        d = b - a; n = np.array([-d[1], d[0]]) / (np.hypot(*d) + 1e-9)
        best, bv = p, -1.0
        span = search or 40
        for t in np.linspace(-span, span, 33):
            q = p + n * t / f
            gy, gx = int(q[1] * f), int(q[0] * f)
            if 0 <= gy < H and 0 <= gx < W and dt[gy, gx] > bv:
                bv, best = dt[gy, gx], q
        out.append(best if bv > 1.5 else p)
    return smooth(LineString(np.asarray(out)), n=2, tol=1.0)
