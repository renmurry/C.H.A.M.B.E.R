"""Quality-control flags for a traced boundary."""
from __future__ import annotations


def compute_flags(pixel_pts, img_shape, area_frac, n_vertices, method):
    H, W = img_shape[:2]
    flags = []
    if method == "raster":
        x = pixel_pts[:, 0]; y = pixel_pts[:, 1]
        if (x < 3).any() or (x > W - 3).any() or (y < 3).any() or (y > H - 3).any():
            flags.append("TOUCHES_EDGE")
        if area_frac is not None and area_frac < 0.02:
            flags.append("AREA_TOO_SMALL")
        if area_frac is not None and area_frac > 0.97:
            flags.append("AREA_TOO_LARGE")
    if n_vertices < 4:
        flags.append("DEGENERATE")
    return flags
