"""Read: give extracted features the names printed on the map.

A label belongs to
  - a line (road, stream) when it sits close to it and runs along it,
  - an area (village, pond, building) when it sits inside it,
  - a point (pin) when it sits right next to it.
Each label goes to the one feature it fits best. A feature that collects
several labels (a road named twice along its length) takes the name most of
them agree on. Labels that fit nothing stay where they are.
"""
from __future__ import annotations
import math
import re
from collections import defaultdict
from dataclasses import dataclass

MAX_LEN = 40          # longer text is a note or a title, not a name
LINE_ANGLE = 25.0     # degrees a road label may lean away from its road


@dataclass
class Match:
    label: int        # index into the labels list
    feature: object
    layer: str
    score: float


def usable(text):
    t = text.strip()
    return 0 < len(t) <= MAX_LEN and re.search(r"[A-Za-z0-9]", t) is not None


def merge_stacked(labels):
    """Join names printed on two lines ("Green / Valley") into one label.
    Only joins lines of the same size, same angle, one right under the other."""
    used, out = set(), []
    order = sorted(range(len(labels)), key=lambda i: labels[i].y)
    for i in order:
        if i in used:
            continue
        a = labels[i]
        for j in order:
            if j == i or j in used:
                continue
            b = labels[j]
            if abs(_angle_diff(a.angle, b.angle)) > 8 or not (0.8 < b.height / max(a.height, 1e-6) < 1.25):
                continue
            ca, sa = math.cos(math.radians(a.angle)), math.sin(math.radians(a.angle))
            dx, dy = b.x - a.x, b.y - a.y
            along, across = dx * ca + dy * sa, -dx * sa + dy * ca
            h = max(a.height, b.height)
            if 0.8 * h <= across <= 1.9 * h and abs(along) <= 0.35 * max(a.width, b.width):
                used.update((i, j))
                out.append(a._replace(text=f"{a.text} {b.text}", x=(a.x + b.x) / 2, y=(a.y + b.y) / 2,
                                      conf=min(a.conf, b.conf), width=max(a.width, b.width),
                                      height=across + h, parts=(i, j)))
                break
        else:
            used.add(i); out.append(a._replace(parts=(i,)))
    return out


def _angle_diff(a, b):
    """Smallest difference between two text/line directions, ignoring which way they read."""
    d = (a - b) % 180.0
    return min(d, 180.0 - d)


def _line_angle_at(line, pt):
    """Direction (degrees, image axes) of the line where it passes closest to pt."""
    d = line.project(pt)
    a = line.interpolate(max(d - 2.0, 0)); b = line.interpolate(min(d + 2.0, line.length))
    if a.distance(b) < 1e-9:
        return None
    return math.degrees(math.atan2(b.y - a.y, b.x - a.x))


def _score(label, feat_geom, kind):
    from shapely.geometry import Point
    p = Point(label.x, label.y)
    h = max(label.height, 1.0)
    if kind == "line":
        d = feat_geom.distance(p)
        reach = 2.2 * h
        if d > reach:
            return 0.0
        lines = getattr(feat_geom, "geoms", [feat_geom])
        near = min(lines, key=lambda g: g.distance(p))
        ang = _line_angle_at(near, p)
        if ang is None:
            return 0.0
        tilt = _angle_diff(ang, label.angle)
        if label.width > 2.5 * h and tilt > LINE_ANGLE:     # a real word that crosses the road
            return 0.0
        lean = 1.0 - min(tilt, LINE_ANGLE) / LINE_ANGLE * 0.5
        return label.conf * (0.6 + 0.4 * (1 - d / reach)) * lean
    if kind == "polygon":
        if feat_geom.area < 0.3 * label.width * h:           # the text is far bigger than the shape
            return 0.0
        if feat_geom.contains(p):
            return label.conf * 0.55
        if feat_geom.distance(p) <= 0.4 * h:
            return label.conf * 0.35
        return 0.0
    d = feat_geom.distance(p)
    reach = 3.0 * h
    return label.conf * (0.5 + 0.5 * (1 - d / reach)) if d <= reach else 0.0


def match(labels, targets):
    """labels: Label tuples. targets: (layer, kind, feature) for everything that may take a name.
    Returns {feature id: (layer, feature, name, [label indices], score)}."""
    from shapely.strtree import STRtree
    targets = [t for t in targets if t[2].geom is not None and not t[2].geom.is_empty]
    if not labels or not targets:
        return {}
    tree = STRtree([t[2].geom for t in targets])
    per_feat = defaultdict(list)
    for li, lab in enumerate(labels):
        if not usable(lab.text):
            continue
        from shapely.geometry import Point
        pad = 3.0 * max(lab.height, 1.0)
        best = None
        for ti in tree.query(Point(lab.x, lab.y).buffer(pad)):
            layer, kind, f = targets[int(ti)]
            s = _score(lab, f.geom, kind)
            if s > 0 and (best is None or s > best[0] or
                          (s == best[0] and kind == "polygon" and f.geom.area < best[3].geom.area)):
                best = (s, layer, kind, f)
        if best:
            per_feat[best[3].fid].append((li, best[0], best[1], best[3]))
    out = {}
    for fid, got in per_feat.items():
        votes = defaultdict(float)
        for li, s, *_ in got:
            votes[labels[li].text.strip().lower()] += s
        win = max(votes, key=votes.get)
        pick = max((g for g in got if labels[g[0]].text.strip().lower() == win), key=lambda g: g[1])
        layer, feat = got[0][2], got[0][3]
        used = [g[0] for g in got if labels[g[0]].text.strip().lower() == win]
        out[fid] = (layer, feat, labels[pick[0]].text.strip(), used, votes[win] / sum(votes.values()))
    return out
