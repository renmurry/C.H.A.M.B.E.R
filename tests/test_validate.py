from pathlib import Path
import pytest
from chamber.validate import validate_one

SAMPLE = Path(__file__).parent.parent / "samples" / "sample_A.pdf"


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample PDF missing")
def test_validate_metrics():
    r = validate_one(str(SAMPLE), "32636")
    # projected vs geodesic area must agree closely -> CRS handling sound
    assert r["crs_check_pct"] < 1.0, r["crs_check_pct"]
    # inner < centre < outer ordering holds
    assert r["area_lo_ha"] <= r["area_ha"] <= r["area_hi_ha"]
    assert r["uncertainty_pct"] >= 0
