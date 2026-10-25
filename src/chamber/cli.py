"""The command-line front end. Logging, parallel jobs, a progress bar."""
from __future__ import annotations
import argparse, logging, multiprocessing as mp, sys
from pathlib import Path

from . import __version__
from .batch import run_batch

log = logging.getLogger("chamber")


def _setup_logging(outdir: Path, verbose: bool):
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    log.handlers.clear()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(sh)
    fh = logging.FileHandler(outdir / "run.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)


def build_parser():
    p = argparse.ArgumentParser(
        prog="chamber",
        description="Extract block-boundary polygons from georeferenced (Geo)PDF sheets.")
    p.add_argument("input_dir", help="folder containing *.pdf sheets")
    p.add_argument("-o", "--output_dir", default=None,
                   help="output folder (default: INPUT_DIR/converted)")
    p.add_argument("--epsg", default="auto",
                   help="target CRS EPSG code, or 'auto' to pick the UTM zone per sheet "
                        "(default: auto)")
    p.add_argument("--dpi", type=int, default=300, help="render DPI for the trace")
    p.add_argument("--simplify", type=float, default=0.0010,
                   help="polygon simplification (lower = more vertices)")
    p.add_argument("--white-min", type=int, default=175,
                   help="white threshold for the boundary line (0-255)")
    p.add_argument("--no-vector", action="store_true",
                   help="disable vector-boundary detection (force raster trace)")
    p.add_argument("--formats", default="geojson,kml",
                   help="comma-separated vector outputs from geojson,kml,shp,gpkg,dxf "
                        "(default: geojson,kml)")
    p.add_argument("--no-tif", action="store_true", help="skip GeoTIFF output")
    p.add_argument("--merge-zip", action="store_true",
                   help="also write one merged, zipped shapefile (+ WGS84) for GEE; "
                        "individual files are kept")
    p.add_argument("--ocr", action="store_true",
                   help="read the block ID and place name off the map (offline OCR) "
                        "and add them as attributes, checked against the sheet ID in the filename")
    p.add_argument("--jobs", type=int, default=1,
                   help="parallel worker processes (default 1)")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    indir = Path(args.input_dir)
    if not indir.is_dir():
        print(f"error: input dir not found: {indir}", file=sys.stderr)
        return 2
    outdir = Path(args.output_dir) if args.output_dir else indir / "converted"
    outdir.mkdir(parents=True, exist_ok=True)
    _setup_logging(outdir, args.verbose)

    pdfs = sorted(indir.rglob("*.pdf"))
    if not pdfs:
        log.error("no PDFs found in %s", indir)
        return 1

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    valid = {"geojson", "kml", "shp", "gpkg", "dxf"}
    bad = [f for f in formats if f not in valid]
    if bad:
        log.error("unknown format(s): %s. choose from %s", ", ".join(bad), ", ".join(sorted(valid)))
        return 2
    params = {"output_dir": str(outdir), "epsg": args.epsg, "dpi": args.dpi,
              "simplify": args.simplify, "white_min": args.white_min,
              "vector": not args.no_vector, "tif": not args.no_tif, "formats": formats,
              "merge_zip": args.merge_zip, "ocr": args.ocr}

    log.info("Processing %d PDF(s) -> %s  (EPSG:%s, jobs=%d)",
             len(pdfs), outdir, args.epsg, args.jobs)

    try:
        from tqdm import tqdm
        bar = tqdm(total=len(pdfs), desc="sheets", unit="pdf")
    except Exception:
        bar = None

    def on_log(r):
        if r["error"]:
            log.warning("  FAIL %-36s %s", r["file"], r["error"])
        else:
            log.info("  ok   %-36s %8s ha  [%s]",
                     r["file"], r["props"]["area_ha"], r["props"]["qc"])

    def on_progress(done, total):
        if bar is not None:
            bar.update(1)

    summary = run_batch(indir, outdir, params, jobs=args.jobs,
                        on_progress=on_progress, on_log=on_log)
    if bar is not None:
        bar.close()

    log.info("\nSummary: %d ok, %d flagged, %d failed.  Outputs + _report.csv in %s",
             summary["ok"], summary["flagged"], summary["failed"], summary["output_dir"])
    flagged = [r for r in summary["results"]
               if r["error"] is None and r["props"] and r["props"]["qc"] != "ok"]
    if flagged:
        log.info("Review the debug overlays for: %s",
                 ", ".join(r["sheet_id"] for r in flagged[:10]))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
