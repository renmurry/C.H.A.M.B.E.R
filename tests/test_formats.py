from pathlib import Path
import pytest
from chamber.pipeline import process_one

SAMPLE = Path(__file__).parent.parent / "samples" / "sample_A.pdf"
pyogrio = pytest.importorskip("pyogrio")


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample PDF missing")
def test_shapefile_geopackage_dxf(tmp_path):
    params = {"output_dir": str(tmp_path), "epsg": "32636", "dpi": 200,
              "simplify": 0.0010, "white_min": 175, "vector": True, "tif": False,
              "formats": ["geojson", "shp", "gpkg", "dxf"]}
    r = process_one(str(SAMPLE), params)
    assert r["error"] is None, r["error"]
    stem = SAMPLE.stem
    for ext in (".geojson", ".shp", ".gpkg", ".dxf", ".shx", ".dbf", ".prj"):
        assert (tmp_path / f"{stem}_block{ext}").exists(), ext
    # shapefile + geopackage are readable and carry the CRS + a feature
    for ext in (".shp", ".gpkg"):
        info = pyogrio.read_info(str(tmp_path / f"{stem}_block{ext}"))
        assert info["features"] == 1
        assert "32636" in str(info["crs"])
