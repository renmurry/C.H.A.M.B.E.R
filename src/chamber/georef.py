"""Pull the exact coordinates out of the PDF (/VP -> /Measure).

This part is exact. The trace is the fuzzy part. Keep them apart so the fuzzy
bit never messes up the exact bit.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import numpy as np


@dataclass
class GeoRef:
    page_index: int
    bbox: list           # [x0, y0, x1, y1] in PDF page points, y up
    affine: Callable     # (x_page, y_page) -> (lon, lat)  WGS84
    wkt: str
    centroid_lonlat: tuple
    n_viewports: int


def utm_epsg(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing (lon, lat)."""
    zone = int((lon + 180.0) / 6.0) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def _affine_from_corners(corners_page, corners_geo) -> Callable:
    """Least-squares affine [lon,lat] = A . [x,y,1] (handles rotation/skew)."""
    P = np.array([[x, y, 1.0] for x, y in corners_page])
    L = np.array(corners_geo)
    coef, *_ = np.linalg.lstsq(P, L, rcond=None)   # 3x2
    return lambda x, y: tuple(np.array([x, y, 1.0]) @ coef)


def read_georef(pdf_path) -> GeoRef:
    """Read georeferencing from the first page that carries a /VP viewport."""
    import pikepdf
    pdf = pikepdf.open(str(pdf_path))
    for pi, page in enumerate(pdf.pages):
        vp = page.get("/VP")
        if vp is None:
            continue
        n_vp = len(vp)
        vp0 = vp[0]                                   # first viewport
        bbox = [float(v) for v in vp0["/BBox"]]
        meas = vp0["/Measure"]
        gpts = [float(v) for v in meas["/GPTS"]]      # lat,lon pairs (WGS84)
        lpts = [float(v) for v in meas["/LPTS"]]      # normalised [0..1] of BBox
        wkt = str(meas["/GCS"].get("/WKT", "")) if "/GCS" in meas else ""

        corners_geo = [(gpts[i + 1], gpts[i]) for i in range(0, len(gpts), 2)]
        bx0, by0, bx1, by1 = bbox
        corners_page = [(bx0 + lpts[i] * (bx1 - bx0),
                         by0 + lpts[i + 1] * (by1 - by0))
                        for i in range(0, len(lpts), 2)]
        if len(corners_geo) < 3:
            raise ValueError("viewport has too few GPTS corners")
        affine = _affine_from_corners(corners_page, corners_geo)
        lon_c = sum(c[0] for c in corners_geo) / len(corners_geo)
        lat_c = sum(c[1] for c in corners_geo) / len(corners_geo)
        return GeoRef(pi, bbox, affine, wkt, (lon_c, lat_c), n_vp)
    raise ValueError("this PDF has no georeferencing in it (no /VP viewport), so it cannot be mapped")


def pixel_to_page(px, py, W, H, bbox):
    """Map a pixel in the rendered neatline image to PDF page coords (y up)."""
    bx0, by0, bx1, by1 = bbox
    return (bx0 + (px / W) * (bx1 - bx0),
            by1 - (py / H) * (by1 - by0))            # image top row = high y (north)
