"""Filename codes, number matching and digit clean-up."""
import json
import pytest
from chamber import ocr as OCR


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A made-up private profile: 10-digit IDs = 2 region + 4 area + 4 block."""
    f = tmp_path / "sheet_profile.json"
    f.write_text(json.dumps({
        "id_length": 10,
        "id_layout": [["district_code", 0, 2], ["town_code", 2, 6], ["block_no", 6, 10]],
        "label_words": ["survey", "department"],
        "label_prefixes": ["surveyof"]}), encoding="utf-8")
    monkeypatch.setenv("CHAMBER_PROFILE", str(f))
    OCR.reset_profile()
    yield f
    OCR.reset_profile()


@pytest.fixture
def no_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAMBER_PROFILE", str(tmp_path / "missing.json"))
    OCR.reset_profile()
    yield
    OCR.reset_profile()


def test_codes_from_a_standard_filename(profile):
    c = OCR.codes_from_sheet_id("0712340013")
    assert c == {"district_code": "07", "town_code": "1234", "block_no": "0013"}


@pytest.mark.parametrize("bad", ["", "sheet_01", "071234001", "07123400130"])
def test_non_standard_filenames_give_no_codes(profile, bad):
    assert OCR.codes_from_sheet_id(bad) == {}


def test_without_a_profile_filenames_give_no_codes(no_profile):
    assert OCR.codes_from_sheet_id("0712340013") == {}


def test_broken_profile_is_ignored(tmp_path, monkeypatch):
    f = tmp_path / "sheet_profile.json"
    f.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CHAMBER_PROFILE", str(f))
    OCR.reset_profile()
    assert OCR.codes_from_sheet_id("0712340013") == {}
    OCR.reset_profile()


def test_same_number():
    assert OCR.same_number("13", "0013")
    assert OCR.same_number("0015", "0015")
    assert not OCR.same_number("003", "0013")      # the old dropped-'1' misread
    assert not OCR.same_number("0075", "0015")     # the old 1-read-as-7 misread
    assert not OCR.same_number("", "0013")


def test_boxed_letters_become_digits():
    assert OCR._digit_chars("O") == ["0"]
    assert OCR._digit_chars("0O13") == ["0", "0", "1", "3"]
    assert OCR._digit_chars("l") == ["1"]
    assert OCR._digit_chars("Code No") == []        # real words are left alone


def test_label_words_are_not_names(no_profile):
    for w in ("name", "nameofsub", "nameofdistrict", "district", "village", "blockno"):
        assert OCR._is_label_word(w)
    for w in ("elm", "oakdale", "north", "ridge", "riverside", "maple"):
        assert not OCR._is_label_word(w)


def test_profile_adds_label_words(profile):
    assert OCR._is_label_word("survey") and OCR._is_label_word("surveyofland")
    assert not OCR._is_label_word("riverside")
