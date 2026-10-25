import json
from pathlib import Path
import pytest
from chamber.pipeline import process_one

SAMPLE = Path(__file__).parent.parent / "samples" / "sample_A.pdf"


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample PDF missing")
def test_sample_block_area(tmp_path):
    params = {"output_dir": str(tmp_path), "epsg": "32636", "dpi": 300,
              "simplify": 0.0010, "white_min": 175, "vector": True, "tif": False}
    r = process_one(str(SAMPLE), params)
    assert r["error"] is None, r["error"]
    props = r["props"]
    assert props["crs"] == "EPSG:32636"
    assert props["qc"] == "ok"
    # golden: the traced block is ~26.3 ha (true area 26.564 ha, see
    # samples/ground_truth.csv); guard against silent geometry drift
    assert 25.5 <= props["area_ha"] <= 27.5, props["area_ha"]
    stem = SAMPLE.stem
    assert (tmp_path / f"{stem}_block.geojson").exists()
    assert (tmp_path / f"{stem}_block.kml").exists()
    gj = json.loads((tmp_path / f"{stem}_block.geojson").read_text())
    assert gj["features"][0]["geometry"]["type"] == "Polygon"


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample PDF missing")
def test_auto_epsg_picks_36n(tmp_path):
    params = {"output_dir": str(tmp_path), "epsg": "auto", "dpi": 200,
              "simplify": 0.0010, "white_min": 175, "vector": True, "tif": False}
    r = process_one(str(SAMPLE), params)
    assert r["error"] is None
    assert r["props"]["crs"] == "EPSG:32636"   # auto must resolve to UTM 36N here
