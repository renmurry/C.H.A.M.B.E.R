"""The loop that runs a whole folder. Both the app and the command line call
this, so they can't drift apart."""
from __future__ import annotations
import csv, json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .pipeline import process_one


def run_batch(input_dir, output_dir, params, jobs=1,
              on_progress=None, on_log=None):
    """Process every *.pdf in input_dir. Returns a summary dict.

    on_progress(done, total)   called after each file
    on_log(result_dict)        called after each file with its result
    `params` must contain output_dir, epsg, dpi, simplify, white_min, vector, tif.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    params = dict(params); params["output_dir"] = str(output_dir)

    pdfs = sorted(input_dir.rglob("*.pdf"))
    total = len(pdfs)
    results = []

    if total == 0:
        return {"ok": 0, "flagged": 0, "failed": 0, "total": 0,
                "output_dir": str(output_dir), "results": []}

    if jobs and jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = {ex.submit(process_one, str(p), params): p for p in pdfs}
            done = 0
            for f in as_completed(futs):
                r = f.result(); results.append(r); done += 1
                if on_log: on_log(r)
                if on_progress: on_progress(done, total)
    else:
        for i, p in enumerate(pdfs, 1):
            r = process_one(str(p), params); results.append(r)
            if on_log: on_log(r)
            if on_progress: on_progress(i, total)

    results.sort(key=lambda r: r["sheet_id"])
    ok = [r for r in results if r["error"] is None]
    bad = [r for r in results if r["error"] is not None]
    flagged = [r for r in ok if r["props"] and r["props"]["qc"] != "ok"]

    if ok:
        idx = {"type": "FeatureCollection",
               "crs": {"type": "name",
                       "properties": {"name": f"urn:ogc:def:crs:EPSG::{params['epsg']}"}},
               "features": [{"type": "Feature", "properties": r["props"],
                             "geometry": r["geometry"]} for r in ok]}
        (output_dir / "_index_blocks.geojson").write_text(json.dumps(idx, indent=2),
                                                          encoding="utf-8")

        # combined index in the extra vector formats (only if every block shares
        # one CRS, e.g. a fixed --epsg; under "auto" zones can differ so we skip)
        formats = params.get("formats") or []
        crs_set = {r["props"]["crs"] for r in ok}
        if len(crs_set) == 1 and any(f in formats for f in ("shp", "gpkg")):
            from shapely.geometry import shape
            from . import writers as W
            epsg = next(iter(crs_set)).split(":")[1]
            polys = [shape(r["geometry"]) for r in ok]
            props_list = [r["props"] for r in ok]
            for fmt in ("shp", "gpkg"):
                if fmt in formats:
                    ext = W.OGR_FORMATS[fmt][1]
                    try:
                        W.write_vector(output_dir / f"_index_blocks{ext}", polys,
                                       props_list, epsg, W.OGR_FORMATS[fmt][0])
                    except Exception:
                        pass

    keys = ["sheet_id", "method", "crs", "vertices", "area_m2", "area_ha", "perimeter_m", "qc"]
    if any(r["props"] and "block_label" in r["props"] for r in results):
        from . import ocr as OCR
        keys += OCR.OCR_FIELDS + ["meta_missing"]
    # utf-8-sig = UTF-8 that Excel also opens correctly
    with open(output_dir / "_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r["props"] if r["props"] else {"sheet_id": r["sheet_id"], "qc": r["qc"]})

    # optional: one merged, zipped, GEE-friendly shapefile (individuals untouched)
    if params.get("merge_zip") and ok:
        try:
            district = input_dir.name.replace("_converted", "").replace("_", " ").strip() or "merged"
            _merge_and_zip(output_dir, ok, district)
        except Exception:
            pass   # never let the optional merge break a finished run

    return {"ok": len(ok), "flagged": len(flagged), "failed": len(bad),
            "total": total, "output_dir": str(output_dir), "results": results}


def _merge_and_zip(output_dir, ok, district):
    """Merge all successful blocks into one shapefile (native CRS if every block
    shares one) plus a WGS84 version, each zipped with the sidecars at the zip
    root so Google Earth Engine accepts it. Returns the list of zip paths."""
    import os, zipfile
    import numpy as np
    import shapely
    from shapely.geometry import shape
    from shapely.ops import transform as shp_transform
    from pyproj import Transformer
    from pyogrio.raw import write

    polys, crs_list, sheet_ids, areas, perims, qcs = [], [], [], [], [], []
    has_ocr = bool(ok) and "block_label" in ok[0]["props"]
    # curated identity fields for the merged file (folder "district" already present)
    ocr_extra = [("blk_id", "block_label"), ("block_no", "block_no"), ("state", "state"),
                 ("subdist", "subdistrict"), ("town", "town_village")]
    ocr_cols = {short: [] for short, _ in ocr_extra}
    for r in ok:
        p = r["props"]
        polys.append(shape(r["geometry"]))
        crs_list.append(p["crs"]); sheet_ids.append(str(p["sheet_id"]))
        areas.append(float(p["area_ha"])); perims.append(float(p["perimeter_m"]))
        qcs.append(str(p["qc"]))
        for short, key in ocr_extra:
            ocr_cols[short].append(str(p.get(key, "")))
    n = len(polys)
    if n == 0:
        return []

    def fields():
        names = ["district", "sheet_id", "area_ha", "perim_m", "qc"]
        data = [np.array([district] * n, dtype=object),
                np.array(sheet_ids, dtype=object),
                np.array(areas, dtype="f8"),
                np.array(perims, dtype="f8"),
                np.array(qcs, dtype=object)]
        if has_ocr:
            for short, _ in ocr_extra:
                names.append(short); data.append(np.array(ocr_cols[short], dtype=object))
        return names, data

    def zip_set(base):
        z = str(base) + ".zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                fp = str(base) + ext
                if os.path.exists(fp):
                    zf.write(fp, os.path.basename(fp))
        return z

    name = district.replace(" ", "_") + "_merged"
    made = []

    if len(set(crs_list)) == 1:           # native-CRS merge only if all share one
        epsg = crs_list[0].split(":")[1]
        wkb = np.array([shapely.to_wkb(g) for g in polys], dtype=object)
        names, data = fields()
        write(str(output_dir / (name + ".shp")), geometry=wkb, field_data=data,
              fields=names, driver="ESRI Shapefile", geometry_type="MultiPolygon",
              crs=f"EPSG:{epsg}", promote_to_multi=True)
        made.append(zip_set(output_dir / name))

    trs, g84 = {}, []                     # WGS84 merge (works across zones)
    for g, crs in zip(polys, crs_list):
        if crs not in trs:
            trs[crs] = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        tr = trs[crs]
        g84.append(shapely.to_wkb(
            shp_transform(lambda x, y, z=None, tr=tr: tr.transform(x, y), g)))
    names, data = fields()
    write(str(output_dir / (name + "_wgs84.shp")), geometry=np.array(g84, dtype=object),
          field_data=data, fields=names, driver="ESRI Shapefile",
          geometry_type="MultiPolygon", crs="EPSG:4326", promote_to_multi=True)
    made.append(zip_set(output_dir / (name + "_wgs84")))
    return made
