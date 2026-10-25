"""Build a made-up georeferenced map sheet for the OCR tests.

Everything on it is invented: the place names, the codes and the location.
Layout: a header panel down the left margin, and a map frame on the right with
one white block outline, its number inside, and a neighbour's number outside.
"""
from __future__ import annotations
from pathlib import Path

PAGE_W, PAGE_H = 1190, 842            # A3 landscape, in PDF points
FRAME = (300, 40, 1170, 820)          # map frame (x0, y0, x1, y1), top-left origin
CORNER_LATLON = (26.660, 26.668, 31.235, 31.245)   # lat0, lat1, lon0, lon1

PANEL = [  # (label, value, kind)  kind: name | digits | date
    ("Name of State:", "Avalon", "name"),
    ("Code No:", "17", "digits"),
    ("Name of District:", "Brookfield", "name"),
    ("Code No:", "03", "digits"),
    ("Name of Sub-District:", "Cedar Vale", "name"),
    ("Code No:", "005", "digits"),
    ("Name of Town/Village:", "Dunmore", "name"),
    ("Code No:", "0042", "digits"),
    ("Ward No:", "0000", "digits"),
    ("Block No:", "0007", "digits"),
]
DATES = [("Created on:", "22-05-2026 13:35:02"),
         ("Modified on:", "24-06-2026 13:35:36"),
         ("Map generated on:", "25-06-2026 00:58")]


def make_sheet(path) -> Path:
    import fitz
    import pikepdf

    path = Path(path)
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    # header panel
    y = 90
    for label, value, kind in PANEL:
        page.insert_text((20, y), label, fontsize=11, fontname="helv")
        if kind == "name":
            page.insert_text((150, y - 6), value, fontsize=11, fontname="hebo")
        else:
            x = 160
            for ch in value:
                page.draw_rect(fitz.Rect(x - 3, y - 13, x + 11, y + 4), color=(0, 0, 0), width=0.8)
                page.insert_text((x, y), ch, fontsize=11, fontname="helv")
                x += 16
        y += 34
    y = PAGE_H - 120
    for label, value in DATES:
        page.insert_text((20, y), f"{label} {value}", fontsize=10, fontname="helv")
        y += 38

    # map frame: green ground, one white block, its number, a neighbour's number
    x0, y0, x1, y1 = FRAME
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=None, fill=(0.27, 0.38, 0.27))
    block = [(480, 200), (860, 170), (1000, 380), (900, 650), (560, 690), (430, 450)]
    pts = [fitz.Point(*p) for p in block]
    page.draw_polyline(pts + [pts[0]], color=(1, 1, 1), width=4, closePath=True)
    page.insert_text((700, 440), "0007", fontsize=22, fontname="hebo", color=(1, 1, 1))
    page.insert_text((1060, 760), "0008", fontsize=22, fontname="hebo", color=(1, 1, 1))
    doc.save(str(path))
    doc.close()

    # add the georeferencing (/VP -> /Measure) the way GIS exports do
    lat0, lat1, lon0, lon1 = CORNER_LATLON
    with pikepdf.open(str(path), allow_overwriting_input=True) as pdf:
        pg = pdf.pages[0]
        # BBox is in PDF space (origin bottom-left)
        bbox = [x0, PAGE_H - y1, x1, PAGE_H - y0]
        measure = pikepdf.Dictionary(
            Type=pikepdf.Name.Measure, Subtype=pikepdf.Name.GEO,
            Bounds=pikepdf.Array([0, 0, 0, 1, 1, 1, 1, 0]),
            GPTS=pikepdf.Array([lat0, lon0, lat1, lon0, lat1, lon1, lat0, lon1]),
            LPTS=pikepdf.Array([0, 0, 0, 1, 1, 1, 1, 0]),
            GCS=pikepdf.Dictionary(Type=pikepdf.Name.GEOGCS,
                                   WKT=pikepdf.String('GEOGCS["WGS 84"]')))
        vp = pikepdf.Dictionary(Type=pikepdf.Name.Viewport,
                                BBox=pikepdf.Array(bbox), Measure=measure)
        pg.obj["/VP"] = pikepdf.Array([vp])
        pdf.save(str(path))
    return path
