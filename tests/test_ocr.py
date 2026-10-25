"""OCR on a made-up sheet (see fake_sheet.py): the header panel, the number
inside the block, and the check against the sheet ID in the filename."""
import json
import pytest
from chamber.pipeline import process_one
from chamber import ocr as OCR

pytest.importorskip("rapidocr_onnxruntime")
from fake_sheet import make_sheet  # noqa: E402

PARAMS = {"epsg": "auto", "dpi": 300, "simplify": 0.0010, "white_min": 175,
          "vector": False, "tif": False, "formats": ["geojson"], "ocr": True}


@pytest.fixture
def use_profile(tmp_path, monkeypatch):
    """Point the tool at a profile file (or at nothing) for one test."""
    def _set(data=None):
        f = tmp_path / "sheet_profile.json"
        if data is not None:
            f.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setenv("CHAMBER_PROFILE", str(f))
        OCR.reset_profile()
    yield _set
    OCR.reset_profile()


PROFILE = {"id_length": 10,
           "id_layout": [["district_code", 0, 2], ["town_code", 2, 6], ["block_no", 6, 10]]}


def _run(tmp_path, name):
    sheet = make_sheet(tmp_path / f"{name}.pdf")
    out = tmp_path / "out"; out.mkdir(exist_ok=True)
    r = process_one(str(sheet), dict(PARAMS, output_dir=str(out)))
    assert r["error"] is None, r["error"]
    return r["props"]


def test_reads_panel_and_block_number_without_a_profile(tmp_path, use_profile):
    use_profile(None)
    p = _run(tmp_path, "0300420007")
    # the block's own number (the neighbour's 0008 sits outside and is ignored)
    assert p["block_label"] == "0007", p["block_label"]
    assert p["label_conf"] > 0.8
    assert (p["state"], p["district"], p["subdistrict"], p["town_village"]) == \
        ("Avalon", "Brookfield", "Cedar Vale", "Dunmore")
    assert (p["state_code"], p["district_code"], p["subdistrict_code"],
            p["town_code"], p["ward_no"], p["block_no"]) == \
        ("17", "03", "005", "0042", "0000", "0007")
    assert p["created_on"] == "22-05-2026 13:35:02"
    assert p["modified_on"] == "24-06-2026 13:35:36"
    assert p["generated_on"] == "25-06-2026 00:58"
    assert p["meta_missing"] == "", p["meta_missing"]
    assert p["id_match"] is True and p["qc"] == "ok", p["qc"]


def test_profile_takes_codes_from_the_filename(tmp_path, use_profile):
    use_profile(PROFILE)
    p = _run(tmp_path, "0300420007")
    assert (p["district_code"], p["town_code"], p["block_no"]) == ("03", "0042", "0007")
    assert p["id_match"] is True and p["qc"] == "ok", p["qc"]


def test_misnamed_sheet_is_flagged(tmp_path, use_profile):
    use_profile(PROFILE)
    p = _run(tmp_path, "0300420009")          # filename says block 0009, sheet says 0007
    assert p["id_match"] is False
    assert "ID_MISMATCH" in p["qc"], p["qc"]
