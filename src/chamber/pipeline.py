"""Do one PDF start to finish: read coords, trace, reproject, write files.
Kept picklable so it can run in parallel workers."""
from __future__ import annotations
from pathlib import Path
import fitz
from pyproj import Transformer
from shapely.geometry import Polygon, mapping

from . import georef as G
from . import trace as T
from .qc import compute_flags
from . import writers as W


def _valid(poly):
    return poly if poly.is_valid else poly.buffer(0)


def process_one(pdf_path: str, params: dict) -> dict:
    """Process one PDF. Returns a picklable result dict (no shapely objects)."""
    pdf_path = Path(pdf_path)
    sheet_id = pdf_path.stem
    res = {"sheet_id": sheet_id, "file": pdf_path.name, "qc": "", "error": None,
           "geometry": None, "props": None}
    try:
        gref = G.read_georef(pdf_path)
        doc = fitz.open(pdf_path)
        page = doc[gref.page_index]

        epsg = params["epsg"]
        if epsg in (None, "auto"):
            epsg = G.utm_epsg(*gref.centroid_lonlat)
        epsg = int(epsg)

        tp = T.TraceParams(dpi=params["dpi"], simplify=params["simplify"],
                           white_min=params["white_min"], vector=params["vector"])

        method = "raster"
        pixel_pts = None
        img = T.render_neatline(page, gref.bbox, tp.dpi)

        vec = T.try_vector_boundary(page, gref.bbox) if tp.vector else None
        if vec is not None:
            method = "vector"
            lonlat = [gref.affine(x, y) for x, y in vec]
            qc_area = None
            n_pts = len(vec)
        else:
            pixel_pts, qc = T.trace_raster(img, tp)
            qc_area = qc["area_frac"]
            n_pts = len(pixel_pts)
            H, Wd = img.shape[:2]
            lonlat = [gref.affine(*G.pixel_to_page(px, py, Wd, H, gref.bbox))
                      for px, py in pixel_pts]

        tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        proj = [tr.transform(lo, la) for lo, la in lonlat]
        poly = _valid(Polygon(proj))

        flags = compute_flags(pixel_pts if pixel_pts is not None else _np_dummy(),
                              img.shape, qc_area, n_pts, method)
        qc_str = ";".join(flags) or "ok"
        props = {"sheet_id": sheet_id, "method": method, "crs": f"EPSG:{epsg}",
                 "vertices": int(n_pts), "area_m2": round(poly.area, 1),
                 "area_ha": round(poly.area / 1e4, 3),
                 "perimeter_m": round(poly.length, 1),
                 "source_crs_wkt": gref.wkt[:80], "qc": qc_str}

        if params.get("ocr"):
            from . import ocr as OCR
            for k in OCR.OCR_FIELDS:                # keep columns consistent
                props.setdefault(k, 0.0 if k == "label_conf"
                                 else (False if k == "id_match" else ""))
            props["meta_missing"] = ""
            try:
                import re as _re
                if pixel_pts is not None:
                    info = OCR.read_labels(img, _valid(Polygon(pixel_pts)), sheet_id)
                    if info:
                        props.update(info)
                meta = OCR.read_panel(page, gref, props.get("block_label", ""))
                if meta:
                    meta.pop("meta_missing", None)
                    props.update(meta)
                panel_no = props.get("block_no", "")
                map_no = props.get("block_label", "")
                file_codes = OCR.codes_from_sheet_id(sheet_id)
                if file_codes.get("block_no"):
                    # standard filename: codes are exact, OCR only double-checks
                    props.update(file_codes)
                    reads = [r for r in (panel_no, map_no) if r]
                    props["id_match"] = any(OCR.same_number(r, file_codes["block_no"])
                                            for r in reads)
                    # flag only when BOTH readers saw a number and NEITHER agrees:
                    # that's a sheet that really doesn't match its filename
                    if len(reads) == 2 and not props["id_match"]:
                        flags.append("ID_MISMATCH")
                else:
                    # no ID layout for this filename: best OCR guess, checked loosely
                    props.update(file_codes)
                    best_id = panel_no or map_no or ""
                    props["block_no"] = best_id
                    props["id_match"] = bool(best_id) and best_id in _re.sub(r"\D", "", str(sheet_id))
                    if best_id and not props["id_match"]:
                        flags.append("ID_MISMATCH")
                props["meta_missing"] = ",".join(k for k in OCR.PANEL_FIELDS
                                                 if not props.get(k))
                if not OCR.available():
                    flags.append("OCR_UNAVAILABLE")
                props["qc"] = ";".join(flags) or "ok"
            except Exception as e:
                flags.append(f"OCR_FAILED:{type(e).__name__}")
                props["qc"] = ";".join(flags)

        outdir = Path(params["output_dir"])
        formats = params.get("formats") or ["geojson", "kml"]
        if "geojson" in formats:
            W.write_geojson(outdir / f"{sheet_id}_block.geojson", poly, epsg, props)
        if "kml" in formats:
            W.write_kml(outdir / f"{sheet_id}_block.kml", lonlat, sheet_id, props)
        for fmt in ("shp", "gpkg", "dxf"):
            if fmt in formats:
                _, ext = W.OGR_FORMATS[fmt]
                try:
                    W.write_vector(outdir / f"{sheet_id}_block{ext}", [poly], [props],
                                   epsg, W.OGR_FORMATS[fmt][0])
                except Exception as e:
                    flags.append(f"{fmt.upper()}_FAILED:{type(e).__name__}")
                    props["qc"] = ";".join(flags)
        if params["tif"]:
            try:
                W.write_geotiff(outdir / f"{sheet_id}_georef.tif", img, gref.bbox, gref.affine, epsg)
            except Exception as e:
                flags.append(f"TIF_FAILED:{type(e).__name__}")
                props["qc"] = ";".join(flags)
        if pixel_pts is not None:
            W.write_debug(outdir / f"{sheet_id}_debug.png", img, pixel_pts)

        res.update(qc=props["qc"], geometry=mapping(poly), props=props)
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {e}"
        res["qc"] = f"ERROR:{res['error']}"
    return res


def _np_dummy():
    import numpy as np
    return np.zeros((1, 2), dtype=int)
