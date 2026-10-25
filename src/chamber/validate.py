"""How good is the output? This checks it.

Per sheet, with no outside data needed:
  area_ha          best guess (line centre)
  uncertainty_pct  how much wiggle the line's own thickness gives
  crs_check_pct    projected area vs real ellipsoid area; tiny = coords are sane
Drop a ground_truth.csv (sheet_id,true_area_ha) next to the PDFs and it also gives
the real error vs the official numbers. Writes a CSV and an HTML report.
"""
from __future__ import annotations
import argparse, csv
from pathlib import Path

import fitz
from pyproj import Transformer, Geod
from shapely.geometry import Polygon

from . import georef as G
from . import trace as T

GEOD = Geod(ellps="WGS84")


def _poly_areas(pixel_pts, img_shape, bbox, affine, epsg):
    """Return (planar_area_m2, geodesic_area_m2) for a pixel polygon."""
    H, W = img_shape[:2]
    lonlat = [affine(*G.pixel_to_page(px, py, W, H, bbox)) for px, py in pixel_pts]
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    proj = [tr.transform(lo, la) for lo, la in lonlat]
    planar = Polygon(proj).buffer(0).area
    lons = [p[0] for p in lonlat]; lats = [p[1] for p in lonlat]
    geo, _ = GEOD.polygon_area_perimeter(lons, lats)
    return planar, abs(geo)


def validate_one(pdf_path, epsg_opt, dpi=300, simplify=0.0010):
    gref = G.read_georef(pdf_path)
    page = fitz.open(pdf_path)[gref.page_index]
    epsg = G.utm_epsg(*gref.centroid_lonlat) if epsg_opt in (None, "auto") else int(epsg_opt)
    tp = T.TraceParams(dpi=dpi, simplify=simplify)
    img = T.render_neatline(page, gref.bbox, tp.dpi)
    blk, _, white_mask = T.enclosed_block(img, tp)
    half = T.estimate_halfwidth(white_mask, blk)
    g = T.grow_for(tp, half)
    inner = T.contour_at_grow(blk, 0, simplify)        # inner edge of the line
    center = T.contour_at_grow(blk, g, simplify)       # centreline (best estimate)
    outer = T.contour_at_grow(blk, 2 * g, simplify)    # outer edge

    a_in, _ = _poly_areas(inner, img.shape, gref.bbox, gref.affine, epsg)
    a_ce, geo_ce = _poly_areas(center, img.shape, gref.bbox, gref.affine, epsg)
    a_ou, _ = _poly_areas(outer, img.shape, gref.bbox, gref.affine, epsg)

    unc_pct = (a_ou - a_in) / (2 * a_ce) * 100 if a_ce else float("nan")
    crs_pct = abs(a_ce - geo_ce) / geo_ce * 100 if geo_ce else float("nan")
    return {"sheet_id": Path(pdf_path).stem, "crs": f"EPSG:{epsg}",
            "area_ha": round(a_ce / 1e4, 3),
            "area_lo_ha": round(a_in / 1e4, 3),
            "area_hi_ha": round(a_ou / 1e4, 3),
            "uncertainty_pct": round(unc_pct, 2),
            "crs_check_pct": round(crs_pct, 3)}


def _load_truth(input_dir):
    f = Path(input_dir) / "ground_truth.csv"
    if not f.exists():
        return {}
    truth = {}
    for row in csv.DictReader(open(f, encoding="utf-8-sig")):
        try:
            truth[row["sheet_id"]] = float(row["true_area_ha"])
        except (KeyError, ValueError):
            pass
    return truth


def _html(rows, has_truth, out):
    head = ["Sheet ID", "CRS", "Area (ha)", "Uncertainty", "CRS check"]
    if has_truth:
        head += ["Official (ha)", "Error"]
    th = "".join(f"<th>{h}</th>" for h in head)
    trs = []
    for r in rows:
        cells = [r["sheet_id"], r["crs"], f"{r['area_ha']:.3f}",
                 f"&plusmn;{r['uncertainty_pct']:.2f}%", f"{r['crs_check_pct']:.3f}%"]
        if has_truth:
            err = r.get("error_pct")
            cells += [f"{r.get('true_area_ha','')}",
                      ("&mdash;" if err is None else f"{err:+.2f}%")]
        trs.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    Path(out).write_text(f"""<!doctype html><meta charset=utf-8>
<title>C.H.A.M.B.E.R - validation</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}}
h1{{font-size:20px}}table{{border-collapse:collapse;font-size:14px}}
th,td{{border:1px solid #ddd;padding:6px 10px;text-align:right}}
th{{background:#f5f5f5}}td:first-child,th:first-child{{text-align:left}}
.note{{color:#666;font-size:13px;max-width:760px;line-height:1.6}}</style>
<h1>C.H.A.M.B.E.R &mdash; accuracy validation</h1>
<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>
<p class=note><b>Uncertainty</b> is the area band implied by the boundary line's
own thickness (inner edge vs outer edge); the best estimate is the centreline.
<b>CRS check</b> compares the projected (planar) area to the geodesic area on the
WGS84 ellipsoid &mdash; a small value confirms the projection and georeferencing
are sound, independent of the trace.{' <b>Error</b> is the centreline area versus the supplied official area.' if has_truth else ''}</p>""",
                       encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chamber-validate",
        description="Validate the accuracy of extracted block boundaries.")
    ap.add_argument("input_dir")
    ap.add_argument("-o", "--output_dir", default=None)
    ap.add_argument("--epsg", default="auto")
    args = ap.parse_args(argv)

    indir = Path(args.input_dir)
    outdir = Path(args.output_dir) if args.output_dir else indir
    outdir.mkdir(parents=True, exist_ok=True)
    truth = _load_truth(indir)
    pdfs = sorted(indir.rglob("*.pdf"))
    if not pdfs:
        print("no PDFs found in", indir); return 1

    rows = []
    for p in pdfs:
        try:
            r = validate_one(str(p), args.epsg)
            if r["sheet_id"] in truth:
                r["true_area_ha"] = round(truth[r["sheet_id"]], 3)
                r["error_pct"] = round((r["area_ha"] - truth[r["sheet_id"]]) / truth[r["sheet_id"]] * 100, 2)
            rows.append(r)
            extra = f"  error {r['error_pct']:+.2f}%" if "error_pct" in r else ""
            print(f"  {r['sheet_id']:28s} {r['area_ha']:8.3f} ha  +/-{r['uncertainty_pct']:.2f}%"
                  f"  crs {r['crs_check_pct']:.3f}%{extra}")
        except Exception as e:
            print(f"  FAIL {p.name}: {e}")

    keys = ["sheet_id", "crs", "area_ha", "area_lo_ha", "area_hi_ha",
            "uncertainty_pct", "crs_check_pct", "true_area_ha", "error_pct"]
    with open(outdir / "validation_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader(); [w.writerow(r) for r in rows]
    _html(rows, bool(truth), outdir / "validation_report.html")
    print(f"\nWrote validation_report.csv + .html to {outdir}")
    if truth:
        errs = [abs(r["error_pct"]) for r in rows if "error_pct" in r]
        if errs:
            print(f"Mean absolute error vs ground truth: {sum(errs)/len(errs):.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
