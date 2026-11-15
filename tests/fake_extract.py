"""A made-up map page for the Extract tests: an 'aerial photo' with three round
green trees, a grey road and a square roof, a drawn red boundary and an orange
road line on top, and grid labels around the frame. Every place and number is
invented."""
from __future__ import annotations
import numpy as np

W_PX, H_PX = 1200, 900            # photo size
GSD = 0.05                        # metres per pixel
E0, N0 = 410000.0, 1350000.0      # top-left corner of the photo (UTM 36N, invented)
TREES = [(300, 300, 45), (700, 250, 45), (900, 650, 45)]   # x, y, radius (px)
ROOF = (480, 520, 640, 680)       # x0, y0, x1, y1 (px)
ROAD_Y = (90, 150)                # road band, top/bottom rows (px)


def photo(seed=3):
    rng = np.random.default_rng(seed)
    a = np.zeros((H_PX, W_PX, 3), np.uint8)
    a[:] = (186, 160, 120)                                     # dry ground
    a[ROAD_Y[0]:ROAD_Y[1], :] = (95, 95, 100)                  # road
    x0, y0, x1, y1 = ROOF
    a[y0:y1, x0:x1] = (150, 70, 45)                            # rusty roof
    yy, xx = np.mgrid[0:H_PX, 0:W_PX]
    for cx, cy, r in TREES:
        a[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = (50, 120, 45)
    noise = rng.integers(-6, 7, a.shape)
    return np.clip(a.astype(int) + noise, 0, 255).astype(np.uint8)


def make_pdf(path, labels=True, epsg_text=True):
    """Page with the photo in a frame; returns the photo's page rect."""
    import pymupdf, io
    from PIL import Image
    doc = pymupdf.open(); page = doc.new_page(width=842, height=595)
    rect = pymupdf.Rect(60, 40, 60 + 600, 40 + 450)            # 0.5 pt per photo px
    buf = io.BytesIO(); Image.fromarray(photo()).save(buf, "PNG")
    page.insert_image(rect, stream=buf.getvalue())
    sx = rect.width / W_PX
    to_pg = lambda x, y: (rect.x0 + x * sx, rect.y0 + y * sx)
    # drawn red boundary around the roof, orange road centre line
    x0, y0, x1, y1 = ROOF
    page.draw_rect(pymupdf.Rect(*to_pg(x0, y0), *to_pg(x1, y1)), color=(1, 0.13, 0.13), width=2.4)
    yc = sum(ROAD_Y) / 2
    page.draw_line(pymupdf.Point(*to_pg(0, yc)), pymupdf.Point(*to_pg(W_PX, yc)), color=(1, 0.69, 0), width=3)
    if labels:
        for i in range(0, W_PX + 1, 200):                         # every 10 m, centred on the tick
            x, _ = to_pg(i, 0)
            t = f"{int(E0 + i * GSD)} E"
            half = pymupdf.get_text_length(t, fontsize=6) / 2
            page.insert_text((x - half, rect.y0 - 6), t, fontsize=6)
            page.insert_text((x - half, rect.y1 + 10), t, fontsize=6)
        for j in range(0, H_PX + 1, 200):
            _, y = to_pg(0, j)
            t = f"{int(N0 - j * GSD)} N"
            half = pymupdf.get_text_length(t, fontsize=6) / 2
            page.insert_text((rect.x0 - 6, y + half), t, fontsize=6, rotate=90)
    page.insert_text((700, 520), "Landmark Hall", fontsize=8)
    if epsg_text:
        page.insert_text((700, 560), "Coordinate system: WGS 84 / UTM Zone 36N (EPSG:32636)", fontsize=6)
    doc.save(str(path))
    return rect
