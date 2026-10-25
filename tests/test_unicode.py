"""Regression: a stray non-Latin OCR character (e.g. 川) used to crash the
KML write on Windows with UnicodeEncodeError ('charmap' codec)."""
from chamber import writers as W
from chamber.ocr import _clean


def test_kml_and_geojson_are_utf8_even_with_odd_characters(tmp_path):
    from shapely.geometry import Polygon
    props = {"sheet_id": "1", "place_label": "Elm 川 Farm"}
    kml = tmp_path / "x.kml"
    W.write_kml(kml, [(31.0, 26.0), (31.1, 26.0), (31.1, 26.1)], "1", props)
    assert "川" in kml.read_bytes().decode("utf-8")
    gj = tmp_path / "x.geojson"
    W.write_geojson(gj, Polygon([(0, 0), (1, 0), (1, 1)]), 32636, props)
    gj.read_bytes().decode("utf-8")


def test_ocr_text_is_cleaned_to_latin():
    assert _clean("Elm 川 Farm") == "Elm Farm"
    assert _clean("００１") == "001"          # fullwidth digits -> normal
    assert _clean("川") == ""
    assert _clean("  Oakdale ") == "Oakdale"


def test_kml_name_with_ampersand_stays_valid(tmp_path):
    import xml.etree.ElementTree as ET
    kml = tmp_path / "x.kml"
    W.write_kml(kml, [(31.0, 26.0), (31.1, 26.0), (31.1, 26.1)], "Ward 3 & 4 <east>", {})
    root = ET.parse(kml).getroot()                     # raises if the XML is broken
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    assert root.find(".//k:Placemark/k:name", ns).text == "Ward 3 & 4 <east>"
