import shutil, zipfile
from pathlib import Path
import pytest
from chamber.batch import run_batch

SAMPLE = Path(__file__).parent.parent / "samples" / "sample_A.pdf"
pyogrio = pytest.importorskip("pyogrio")


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample PDF missing")
def test_merge_zip_keeps_individuals_and_makes_gee_zip(tmp_path):
    indir = tmp_path / "Testarea"; indir.mkdir()
    shutil.copy(SAMPLE, indir / "a.pdf")
    out = tmp_path / "out"
    params = {"epsg": "32636", "dpi": 200, "simplify": 0.0010, "white_min": 175,
              "vector": True, "tif": False, "formats": ["shp"], "merge_zip": True}
    summary = run_batch(indir, out, params)
    assert summary["ok"] == 1

    # individual shapefile is still there (merge is additive)
    assert (out / "a_block.shp").exists()

    # merged + wgs84 zips were made, named from the folder
    mz = out / "Testarea_merged.zip"
    mz84 = out / "Testarea_merged_wgs84.zip"
    assert mz.exists() and mz84.exists()

    # GEE-friendly: sidecars at the zip root, readable, correct CRS
    with zipfile.ZipFile(mz84) as zf:
        names = zf.namelist()
        assert all("/" not in n for n in names)
        assert any(n.endswith(".shp") for n in names)
    info = pyogrio.read_info(str(out / "Testarea_merged_wgs84.shp"))
    assert info["features"] == 1 and "4326" in str(info["crs"])
