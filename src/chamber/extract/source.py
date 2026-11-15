"""Open any input and work out where its pixels sit on the ground.

Inputs: PDF (GeoPDF or plain), GeoTIFF, JPG/PNG/TIF with or without a world
file. Placement, best first:
  1. GeoPDF tags in the PDF (exact)
  2. GeoTIFF / world file
  3. grid labels printed around the map frame (gridref.py)
  4. none: everything stays in pixel units (you can still extract)

Geographic placements are converted to the local UTM zone so areas and lengths
come out in metres.
"""
from __future__ import annotations
import os, warnings
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np

MAX_SIDE = 8000          # bigger inputs are read downsampled to this
PDF_EXT = {".pdf"}
IMG_EXT = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".jp2", ".bmp", ".webp"}
OPEN_FILTER = "Maps and images (*.pdf *.tif *.tiff *.jpg *.jpeg *.png *.jp2 *.bmp *.webp)"


@dataclass
class Source:
    path: str
    kind: str                                  # pdf | raster | image
    image: np.ndarray                          # H x W x 3, uint8, RGB
    epsg: int | None = None                    # CRS of map coordinates
    placement: str = "None (pixel units)"
    page_index: int = 0
    page_affine: tuple | None = None           # (sx, ox, sy, oy): page = (ox + x*sx, oy + y*sy)
    notes: list = field(default_factory=list)
    _to_map: object = None                     # f(xs, ys) -> (X, Y), vectorised

    @property
    def name(self):
        return Path(self.path).name

    @property
    def placed(self):
        return self._to_map is not None

    def to_map(self, xs, ys):
        """Pixel -> map coordinates. Unplaced: X = x, Y = -y (so it shows upright in a GIS)."""
        xs, ys = np.asarray(xs, float), np.asarray(ys, float)
        if self._to_map is None:
            return xs, -ys
        return self._to_map(xs, ys)

    def px_to_page(self, x, y):
        sx, ox, sy, oy = self.page_affine
        return ox + x * sx, oy + y * sy

    def page_to_px(self, x, y):
        sx, ox, sy, oy = self.page_affine
        return (np.asarray(x, float) - ox) / sx, (np.asarray(y, float) - oy) / sy

    @property
    def gsd(self):
        """Metres per pixel at the image centre (None if unplaced)."""
        if not self.placed or not self.metric:
            return None
        h, w = self.image.shape[:2]
        X, Y = self.to_map([w / 2, w / 2 + 1, w / 2], [h / 2, h / 2, h / 2 + 1])
        return float((np.hypot(X[1] - X[0], Y[1] - Y[0]) + np.hypot(X[2] - X[0], Y[2] - Y[0])) / 2)

    @property
    def metric(self):
        if not self.placed or self.epsg is None:
            return False
        try:
            from pyproj import CRS
            c = CRS.from_epsg(self.epsg)
            return c.is_projected and c.axis_info[0].unit_name in ("metre", "meter")
        except Exception:
            return False


def _utm_wrap(lonlat_fn, lon_c, lat_c):
    """Wrap a pixel->lon/lat function so it returns UTM metres instead."""
    from pyproj import Transformer
    from ..georef import utm_epsg
    epsg = utm_epsg(lon_c, lat_c)
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    def f(xs, ys):
        lon, lat = lonlat_fn(xs, ys)
        return tr.transform(lon, lat)
    return f, epsg


def _to_rgb(a):
    """Any band layout / bit depth -> H x W x 3 uint8."""
    if a.ndim == 2:
        a = a[..., None]
    if a.shape[2] == 1:
        a = np.repeat(a, 3, axis=2)
    a = a[..., :3]
    if a.dtype != np.uint8:
        a = a.astype(np.float32)
        lo, hi = np.percentile(a[a > 0] if (a > 0).any() else a, (1, 99))
        a = np.clip((a - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(a)


# ---------------------------------------------------------------- PDF
def _pdf_raster(page):
    """The page's main photo at its own resolution if it has one, else a render.
    Returns (rgb, page_affine)."""
    import pymupdf
    area = page.rect.width * page.rect.height
    best = None
    for img in page.get_images(full=True):
        for r in page.get_image_rects(img[0]):
            if r.width * r.height > 0.3 * area and (best is None or r.width * r.height > best[1].width * best[1].height):
                best = (img[0], r)
    if best:
        try:
            pix = pymupdf.Pixmap(page.parent, best[0])
            if pix.alpha or pix.n not in (3,):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]
            r = best[1]
            f = min(1.0, MAX_SIDE / max(a.shape[:2]))
            if f < 1:
                import cv2
                a = cv2.resize(a, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            h, w = a.shape[:2]
            return np.ascontiguousarray(a), (r.width / w, r.x0, r.height / h, r.y0)
        except Exception:
            pass                                   # odd image encoding: render instead
    dpi = min(300.0, MAX_SIDE / max(page.rect.width, page.rect.height) * 72)
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]
    s = 72.0 / dpi
    return np.ascontiguousarray(a), (s, page.rect.x0, s, page.rect.y0)


def _open_pdf(path, page_index=0):
    import pymupdf
    from . import gridref
    doc = pymupdf.open(path)
    page = doc[page_index]
    rgb, aff = _pdf_raster(page)
    src = Source(str(path), "pdf", rgb, page_index=page_index, page_affine=aff)
    if len(doc) > 1:
        src.notes.append(f"PDF has {len(doc)} pages; showing page {page_index + 1}")
    # 1. GeoPDF tags
    try:
        from ..georef import read_georef
        g = read_georef(path)
        if g.page_index == page_index:
            inv = ~page.transformation_matrix              # MuPDF space -> PDF space (y up)
            def lonlat(xs, ys):
                px, py = src.px_to_page(xs, ys)
                # affine is linear, so transform the page points in one go
                X = px * inv.a + py * inv.c + inv.e
                Y = px * inv.b + py * inv.d + inv.f
                out = np.array([g.affine(x, y) for x, y in zip(np.ravel(X), np.ravel(Y))])
                return out[:, 0].reshape(np.shape(X)), out[:, 1].reshape(np.shape(X))
            src._to_map, src.epsg = _utm_wrap(lonlat, *g.centroid_lonlat)
            src.placement = "GeoPDF tags"
            return src
    except Exception:
        pass
    # 2. grid labels
    fit = gridref.fit_page(page)
    if fit:
        def m(xs, ys):
            px, py = src.px_to_page(xs, ys)
            return fit.page_to_map(px, py)
        if fit.geographic:
            h, w = rgb.shape[:2]
            lon_c, lat_c = m(w / 2, h / 2)
            src._to_map, src.epsg = _utm_wrap(m, float(lon_c), float(lat_c))
        else:
            src._to_map, src.epsg = m, fit.epsg
            if fit.epsg is None:
                src.notes.append("Grid labels found but no coordinate system printed: pick one before export")
        src.placement = fit.note()
    return src


# ---------------------------------------------------------------- images
def _exif_gps(path):
    try:
        from PIL import Image
        ex = Image.open(path).getexif().get_ifd(0x8825)
        if not ex:
            return None
        def deg(v, ref):
            d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -d if ref in ("S", "W") else d
        return deg(ex[2], ex[1]), deg(ex[4], ex[3])
    except Exception:
        return None


def _open_raster(path):
    import rasterio
    from rasterio.enums import Resampling
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path) as ds:
            f = min(1.0, MAX_SIDE / max(ds.width, ds.height))
            h, w = max(1, int(ds.height * f)), max(1, int(ds.width * f))
            bands = [1, 2, 3] if ds.count >= 3 else [1]
            a = ds.read(bands, out_shape=(len(bands), h, w), resampling=Resampling.average)
            a = np.moveaxis(a, 0, -1)
            T = ds.transform * ds.transform.scale(ds.width / w, ds.height / h)
            crs = ds.crs
            identity = ds.transform.is_identity
    src = Source(str(path), "raster" if not identity else "image", _to_rgb(a))
    if identity:
        gps = _exif_gps(path)
        if gps:
            src.notes.append(f"Photo has one GPS point ({gps[0]:.5f}, {gps[1]:.5f}); "
                             "one point can't place an image, so it stays in pixel units")
        return src
    def m(xs, ys):                     # pixel edges: x = 0 is the image's left edge
        xs, ys = np.asarray(xs, float), np.asarray(ys, float)
        return T.a * xs + T.b * ys + T.c, T.d * xs + T.e * ys + T.f
    if crs is not None and crs.is_geographic:
        lon_c, lat_c = m(w / 2, h / 2)
        src._to_map, src.epsg = _utm_wrap(m, float(lon_c), float(lat_c))
    else:
        src._to_map = m
        src.epsg = crs.to_epsg() if crs is not None else None
        if crs is None:
            src.notes.append("World file found but no coordinate system: pick one before export")
    has_wf = any(Path(str(path)).with_suffix(e).exists() for e in (".jgw", ".pgw", ".tfw", ".wld", ".j2w"))
    src.placement = "World file" if has_wf and not str(path).lower().endswith((".tif", ".tiff")) else "GeoTIFF"
    return src


def open_source(path, page_index=0) -> Source:
    ext = Path(path).suffix.lower()
    if ext in PDF_EXT:
        return _open_pdf(path, page_index)
    if ext in IMG_EXT:
        return _open_raster(path)
    raise ValueError(f"Can't open {Path(path).name}: use a PDF, GeoTIFF or image")
