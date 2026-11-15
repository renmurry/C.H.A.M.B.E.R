"""The layers you build while extracting, undo, measuring and export."""
from __future__ import annotations
import itertools
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np

DEFAULT_LAYERS = [("Buildings", "polygon", "#22d3ee"), ("Roads", "line", "#f472b6"),
                  ("Water", "polygon", "#60a5fa"), ("Streams", "line", "#3b82f6"),
                  ("Trees", "polygon", "#4ade80"), ("Landmarks", "point", "#fbbf24")]
_ids = itertools.count(1)


@dataclass
class Feature:
    geom: object                 # shapely, image px
    method: str                  # click | box | line | pdf | label | similar | point
    conf: float = 1.0
    text: str = ""
    attrs: dict = field(default_factory=dict)      # extra numbers, e.g. width_m for roads
    fid: int = field(default_factory=lambda: next(_ids))
    name: str = ""               # the name printed on the map (Read) or typed in
    meta: dict = field(default_factory=dict)       # app-only notes, never exported


@dataclass
class Layer:
    name: str
    kind: str                    # polygon | line | point
    color: str
    visible: bool = True
    features: list = field(default_factory=list)


class Session:
    def __init__(self, source):
        self.source = source
        self.layers = {n: Layer(n, k, c) for n, k, c in DEFAULT_LAYERS}
        self.undo_stack, self.redo_stack = [], []
        self.changes = 0             # edits so far
        self._group = None           # edits collected into one undo step
        self.exported_at = 0         # value of `changes` at the last export

    # ---------- layers ----------
    def layer(self, name, kind="polygon", color="#e879f9"):
        if name not in self.layers:
            self.layers[name] = Layer(name, kind, color)
        return self.layers[name]

    @property
    def unsaved(self):
        """Kept features not written by an export since the last change."""
        return self.count() > 0 and self.changes != self.exported_at

    def count(self):
        return sum(len(l.features) for l in self.layers.values())

    # ---------- edits (all undoable) ----------
    def _push(self, op):
        if self._group is not None:
            self._group.append(op)
        else:
            self.undo_stack.append(op); self.redo_stack.clear()
        self.changes += 1

    def group(self):
        """`with session.group():` turns every edit inside into a single undo step."""
        sess = self

        class _G:
            def __enter__(self):
                self.outer = sess._group is not None
                if not self.outer:
                    sess._group = []

            def __exit__(self, *exc):
                if self.outer:
                    return False
                ops, sess._group = sess._group, None
                if ops:
                    sess.undo_stack.append(("batch", None, ops)); sess.redo_stack.clear()
                return False
        return _G()

    def add(self, layer, feats):
        feats = feats if isinstance(feats, list) else [feats]
        L = self.layers[layer]
        L.features.extend(feats)
        self._push(("add", layer, feats))
        return feats

    def remove(self, layer, feat):
        L = self.layers[layer]
        i = L.features.index(feat); L.features.pop(i)
        self._push(("remove", layer, [feat], i))

    def rename(self, layer, feat, name):
        old = feat.name
        if old == name:
            return
        feat.name = name
        self._push(("rename", layer, [feat], old, name))

    def _back(self, op):
        if op[0] == "batch":
            for o in reversed(op[2]):
                self._back(o)
            return
        L = self.layers[op[1]]
        if op[0] == "add":
            for f in op[2]:
                L.features.remove(f)
        elif op[0] == "remove":
            L.features.insert(op[3], op[2][0])
        else:
            op[2][0].name = op[3]

    def _forward(self, op):
        if op[0] == "batch":
            for o in op[2]:
                self._forward(o)
            return
        L = self.layers[op[1]]
        if op[0] == "add":
            L.features.extend(op[2])
        elif op[0] == "remove":
            L.features.remove(op[2][0])
        else:
            op[2][0].name = op[4]

    def undo(self):
        if not self.undo_stack:
            return None
        op = self.undo_stack.pop()
        self._back(op)
        self.redo_stack.append(op)
        self.changes += 1
        return op

    def redo(self):
        if not self.redo_stack:
            return None
        op = self.redo_stack.pop()
        self._forward(op)
        self.undo_stack.append(op)
        self.changes += 1
        return op

    def find(self, fid):
        for L in self.layers.values():
            for f in L.features:
                if f.fid == fid:
                    return L, f
        return None, None

    # ---------- measuring ----------
    def to_map(self, geom):
        import shapely
        return shapely.transform(geom, lambda c: np.column_stack(self.source.to_map(c[:, 0], c[:, 1])))

    def measure(self, geom):
        """(text, value, unit) for the info panel and attributes."""
        g = self.to_map(geom)
        m = self.source.metric
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            return ("area", g.area, "m²" if m else "px²")
        if geom.geom_type in ("LineString", "MultiLineString"):
            return ("length", g.length, "m" if m else "px")
        return ("point", 0.0, "")

    # ---------- export ----------
    def export(self, folder, formats=("gpkg",), stem=None, epsg=None):
        """Write every non-empty layer. Returns (written_paths, notes)."""
        import shapely
        from pyogrio.raw import write
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        stem = stem or Path(self.source.path).stem
        epsg = epsg or self.source.epsg
        crs = f"EPSG:{epsg}" if (epsg and self.source.placed) else None
        written, notes = [], []
        if not self.source.placed:
            notes.append("Not placed on the map: coordinates are image pixels (y flipped so it shows upright)")
        for L in self.layers.values():
            if not L.features:
                continue
            geoms = [self.to_map(f.geom) for f in L.features]
            meas = [self.measure(f.geom) for f in L.features]
            fields = ["fid", "layer", "name", "method", "conf", "text", "area_m2" if self.source.metric else "area",
                      "length_m" if self.source.metric else "length", "src_file"]
            data = [np.array([f.fid for f in L.features], dtype="i4"),
                    np.array([L.name] * len(geoms), dtype=object),
                    np.array([f.name for f in L.features], dtype=object),
                    np.array([f.method for f in L.features], dtype=object),
                    np.array([round(f.conf, 3) for f in L.features], dtype="f8"),
                    np.array([f.text for f in L.features], dtype=object),
                    np.array([round(v, 2) if k == "area" else 0.0 for k, v, _ in meas], dtype="f8"),
                    np.array([round(v, 2) if k == "length" else 0.0 for k, v, _ in meas], dtype="f8"),
                    np.array([self.source.name] * len(geoms), dtype=object)]
            extra = sorted({k for f in L.features for k in f.attrs})
            for k in extra:
                fields.append(k[:10])
                data.append(np.array([float(f.attrs.get(k, 0.0)) for f in L.features], dtype="f8"))
            gtype = {"polygon": "MultiPolygon", "line": "MultiLineString", "point": "Point"}[L.kind]
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in L.name).strip("_") or "layer"
            for fmt in formats:
                try:
                    if fmt == "kml":
                        if not crs:
                            notes.append("KML skipped: KML needs a placed map"); continue
                        from pyproj import Transformer
                        tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
                        gg = [shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1]))) for g in geoms]
                        p = folder / f"{stem}_{safe}.kml"
                        write(str(p), geometry=np.array([shapely.to_wkb(g) for g in gg], dtype=object),
                              field_data=data, fields=fields, driver="KML", geometry_type=gtype,
                              crs="EPSG:4326", promote_to_multi=L.kind != "point")
                    elif fmt == "dxf":
                        p = folder / f"{stem}_{safe}.dxf"
                        write(str(p), geometry=np.array([shapely.to_wkb(g) for g in geoms], dtype=object),
                              field_data=[], fields=[], driver="DXF", geometry_type=gtype.replace("Multi", ""), crs=crs)
                    else:
                        drv, ext = {"gpkg": ("GPKG", ".gpkg"), "shp": ("ESRI Shapefile", ".shp"),
                                    "geojson": ("GeoJSON", ".geojson")}[fmt]
                        p = folder / (f"{stem}_extract{ext}" if fmt == "gpkg" else f"{stem}_{safe}{ext}")
                        kw = {"layer": safe, "append": p.exists()} if fmt == "gpkg" else {}
                        write(str(p), geometry=np.array([shapely.to_wkb(g) for g in geoms], dtype=object),
                              field_data=data, fields=fields, driver=drv, geometry_type=gtype,
                              crs=crs, promote_to_multi=L.kind != "point", **kw)
                    if p not in written:
                        written.append(p)
                except Exception as e:
                    notes.append(f"{L.name} -> {fmt.upper()} failed: {type(e).__name__}: {e}")
        if written:
            self.exported_at = self.changes
        return written, notes
