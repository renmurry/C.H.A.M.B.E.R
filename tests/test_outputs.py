"""Only the files you asked for: GeoTIFF is opt-in, debug images follow the
debug_images setting (flagged sheets only by default)."""
from pathlib import Path
import pytest
from chamber.pipeline import process_one
from chamber.cli import build_parser

SAMPLE = Path(__file__).parent.parent / "samples" / "sample_A.pdf"
BASE = {"epsg": "auto", "dpi": 200, "simplify": 0.0010, "white_min": 175,
        "vector": False, "formats": ["geojson"]}


def _run(tmp_path, **extra):
    r = process_one(str(SAMPLE), dict(BASE, output_dir=str(tmp_path), **extra))
    assert r["error"] is None, r["error"]
    return r, sorted(p.name for p in tmp_path.iterdir())


def test_defaults_give_no_geotiff_and_no_debug_for_a_clean_sheet(tmp_path):
    r, files = _run(tmp_path)
    assert r["qc"] == "ok"
    assert files == ["sample_A_block.geojson"], files


def test_geotiff_only_when_asked(tmp_path):
    _, files = _run(tmp_path, tif=True)
    assert "sample_A_georef.tif" in files


@pytest.mark.parametrize("mode, expect_png", [("all", True), ("none", False),
                                              ("flagged", False)])
def test_debug_image_modes_on_a_clean_sheet(tmp_path, mode, expect_png):
    _, files = _run(tmp_path, debug_images=mode)
    assert ("sample_A_debug.png" in files) is expect_png, files


def test_flagged_sheet_gets_its_debug_image(tmp_path, monkeypatch):
    # force a QC flag on an otherwise clean sheet
    import chamber.pipeline as P
    monkeypatch.setattr(P, "compute_flags", lambda *a, **k: ["AREA_TOO_SMALL"])
    r, files = _run(tmp_path, debug_images="flagged")
    assert r["qc"] == "AREA_TOO_SMALL"
    assert "sample_A_debug.png" in files, files


def test_command_line_defaults():
    a = build_parser().parse_args(["in"])
    assert a.tif is False and a.debug_images == "flagged" and a.epsg == "auto"
    a = build_parser().parse_args(["in", "--tif", "--debug-images", "all"])
    assert a.tif is True and a.debug_images == "all"
