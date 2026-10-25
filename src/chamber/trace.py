"""Find the block boundary.

Two tries: if the PDF has a real vector outline, use it. Otherwise trace it off
the image. Catch is the image is full of OTHER white stuff (text, roofs, a north
arrow, dashed neighbour lines), so chasing white pixels gives garbage. Instead
treat the solid line as a fence and grab whatever it fences in: flood-fill from
the edges, and whatever you can't reach is the block. Dashed lines leak so they
fence in nothing, and stray white gets ignored. Works nicely.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import cv2
import fitz


@dataclass
class TraceParams:
    dpi: int = 300
    simplify: float = 0.0010      # approxPolyDP tolerance as fraction of perimeter
    white_min: int = 175          # min value across all RGB channels
    sat_max: int = 45             # max (max-min) channel spread (low saturation)
    close_px: int = 5             # kernel to seal the line
    fill_px: int = 35             # kernel to absorb interior buildings
    grow_px: int = 7              # dilate to reach line centre
    min_area_frac: float = 0.02   # reject enclosed region smaller than this
    vector: bool = True           # attempt vector-first
    auto_grow: bool = True        # auto-centre on the line by measuring its width


def render_neatline(page, bbox, dpi):
    ph = page.rect.height
    z = dpi / 72.0
    clip = fitz.Rect(bbox[0], ph - bbox[3], bbox[2], ph - bbox[1])
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return img[:, :, :3].copy()


def try_vector_boundary(page, bbox):
    """Return boundary points in PDF page coords (y up) if a confident vector
    candidate exists, else None. Deliberately conservative."""
    try:
        drawings = page.get_drawings()
    except Exception:
        return None
    if not drawings:
        return None
    ph = page.rect.height
    bx0, by0, bx1, by1 = bbox
    neat_area = abs((bx1 - bx0) * (by1 - by0))
    cands = []
    for d in drawings:
        col = d.get("color")                          # stroke colour 0..1 or None
        if col is None or not all(c >= 0.85 for c in col):
            continue
        r = d["rect"]
        if r.width * r.height < 0.30 * neat_area:      # must span most of the sheet
            continue
        pts = []
        for it in d["items"]:
            for p in it[1:]:
                if isinstance(p, fitz.Point):
                    pts.append((p.x, ph - p.y))        # fitz y-down -> PDF y-up
        if len(pts) >= 4:
            cands.append((r.width * r.height, pts))
    if len(cands) != 1:           # ambiguous or none -> fall back to raster
        return None
    return cands[0][1]


def enclosed_block(img, p: TraceParams):
    """Return the filled block mask (uint8) BEFORE the centreline grow step,
    plus its area fraction. Shared by the tracer and the accuracy validator."""
    H, W = img.shape[:2]
    mx = img.max(2).astype(int); mn = img.min(2).astype(int)
    white = ((mn >= p.white_min) & ((mx - mn) <= p.sat_max)).astype(np.uint8) * 255
    white = cv2.morphologyEx(
        white, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (p.close_px, p.close_px)))
    white_mask = white.copy()

    free = (white == 0).astype(np.uint8)
    ff = free.copy()
    mask = np.zeros((H + 2, W + 2), np.uint8)
    for x in range(W):
        if ff[0, x]:     cv2.floodFill(ff, mask, (x, 0), 2)
        if ff[H - 1, x]: cv2.floodFill(ff, mask, (x, H - 1), 2)
    for y in range(H):
        if ff[y, 0]:     cv2.floodFill(ff, mask, (0, y), 2)
        if ff[y, W - 1]: cv2.floodFill(ff, mask, (W - 1, y), 2)

    inside = (ff == 1).astype(np.uint8) * 255
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(inside, 8)
    if n <= 1:
        raise ValueError("no enclosed region (boundary not closed?)")
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    blk = np.zeros_like(inside); blk[lbl == biggest] = 255
    blk = cv2.morphologyEx(
        blk, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (p.fill_px, p.fill_px)), iterations=2)
    return blk, (blk > 0).mean(), white_mask


def estimate_halfwidth(white_mask, blk):
    """Estimate the boundary line's half-thickness (px) from the white ridge in
    a band around the block edge. Used to centre the contour on the line."""
    edge = cv2.morphologyEx(blk, cv2.MORPH_GRADIENT,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    band = cv2.dilate(edge, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    ring = cv2.bitwise_and(white_mask, band)
    dist = cv2.distanceTransform((ring > 0).astype(np.uint8), cv2.DIST_L2, 3)
    vals = dist[dist > 0]
    if vals.size == 0:
        return None
    return float(np.percentile(vals, 95))


def grow_for(p, half):
    """Kernel size to shift the inner edge to the centreline."""
    if p.auto_grow and half:
        return max(3, int(round(2 * half)))
    return p.grow_px


def contour_at_grow(blk, grow_px, simplify):
    """Dilate the block mask by grow_px and return its simplified contour."""
    b = blk
    if grow_px > 0:
        b = cv2.dilate(blk, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow_px, grow_px)))
    cnts, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    approx = cv2.approxPolyDP(c, simplify * cv2.arcLength(c, True), True).reshape(-1, 2)
    return approx


def trace_raster(img, p: TraceParams):
    """Return (pixel_points Nx2, qc_dict)."""
    H, W = img.shape[:2]
    blk, _, white_mask = enclosed_block(img, p)
    half = estimate_halfwidth(white_mask, blk)
    approx = contour_at_grow(blk, grow_for(p, half), p.simplify)
    area_frac = cv2.contourArea(approx.reshape(-1, 1, 2).astype(np.int32)) / float(W * H)
    if area_frac < p.min_area_frac:
        raise ValueError(f"enclosed region too small ({area_frac:.3f})")
    return approx, {"area_frac": area_frac}
