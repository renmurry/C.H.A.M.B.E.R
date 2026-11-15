"""Read: map labels become feature names. Every name and place here is invented."""
import pytest
from shapely.geometry import LineString, Point, box

from chamber.extract.labels import Label, from_pdf
from chamber.extract.bind import match, merge_stacked
from chamber.extract.session import Session, Feature
from chamber.extract.source import open_source


def L(text, x, y, angle=0.0, h=10.0, w=None, conf=0.95):
    return Label(text, x, y, conf, angle, h, w if w is not None else 6.0 * len(text))


def names(hits):
    return {f.fid: name for _layer, f, name, _idx, _s in hits.values()}


def test_label_along_a_road_names_it():
    road = Feature(LineString([(0, 100), (500, 100)]), "line")
    hits = match([L("Pine Road", 250, 91)], [("Roads", "line", road)])
    assert names(hits) == {road.fid: "Pine Road"}


def test_label_crossing_a_road_is_not_its_name():
    road = Feature(LineString([(0, 100), (500, 100)]), "line")
    assert match([L("Oak Lane", 250, 96, angle=90)], [("Roads", "line", road)]) == {}


def test_slanted_road_and_slanted_label():
    road = Feature(LineString([(0, 0), (400, 300)]), "line")          # about 37 degrees
    hits = match([L("Ridge Way", 200, 142, angle=36.9)], [("Roads", "line", road)])
    assert names(hits) == {road.fid: "Ridge Way"}


def test_name_inside_an_area():
    pond = Feature(box(300, 200, 400, 300), "click")
    far = L("Hill View", 900, 900)
    hits = match([L("Mill Pond", 350, 250), far], [("Water", "polygon", pond)])
    assert names(hits) == {pond.fid: "Mill Pond"}


def test_text_much_bigger_than_the_shape_is_not_its_name():
    hut = Feature(box(100, 100, 104, 104), "click")
    assert match([L("Long Valley District", 102, 102, h=20)], [("Buildings", "polygon", hut)]) == {}


def test_road_label_inside_a_village_goes_to_the_road():
    village = Feature(box(0, 0, 600, 400), "click")
    road = Feature(LineString([(0, 200), (600, 200)]), "line")
    hits = match([L("Bazaar Street", 300, 192), L("Green Hollow", 120, 60)],
                 [("Villages", "polygon", village), ("Roads", "line", road)])
    assert names(hits) == {road.fid: "Bazaar Street", village.fid: "Green Hollow"}


def test_road_named_twice_takes_the_majority():
    road = Feature(LineString([(0, 100), (900, 100)]), "line")
    labs = [L("Pine Road", 150, 92), L("Pine Road", 750, 92), L("Pine Rd", 450, 92, conf=0.7)]
    hits = match(labs, [("Roads", "line", road)])
    _layer, _f, name, used, _s = hits[road.fid]
    assert name == "Pine Road" and sorted(used) == [0, 1]       # "Pine Rd" stays a landmark


def test_pin_takes_the_label_beside_it():
    well = Feature(Point(600, 600), "point")
    hits = match([L("Old Well", 618, 594)], [("Landmarks", "point", well)])
    assert names(hits) == {well.fid: "Old Well"}


def test_notes_and_titles_are_not_names():
    road = Feature(LineString([(0, 100), (900, 100)]), "line")
    note = L("Prepared from field survey and checked by the district office", 450, 92)
    assert match([note, L("--", 300, 92)], [("Roads", "line", road)]) == {}


def test_two_line_name_is_joined():
    got = merge_stacked([L("Green", 100, 100, w=40), L("Valley", 100, 113, w=44), L("Pine Road", 400, 300)])
    texts = sorted(g.text for g in got)
    assert texts == ["Green Valley", "Pine Road"]
    joined = next(g for g in got if g.text == "Green Valley")
    assert sorted(joined.parts) == [0, 1]


def test_side_by_side_words_are_not_joined():
    got = merge_stacked([L("North", 100, 100, w=40), L("Gate", 160, 100, w=30)])
    assert len(got) == 2


# ---------------------------------------------------------------- straight from a PDF
def test_pdf_labels_carry_angle_and_size(tmp_path):
    import pymupdf
    p = tmp_path / "streets.pdf"
    doc = pymupdf.open(); page = doc.new_page(width=600, height=400)
    page.draw_line((50, 200), (550, 200), color=(0.4, 0.4, 0.4), width=4)
    page.insert_text((250, 194), "Cedar Avenue", fontsize=9)
    page.draw_line((400, 40), (400, 360), color=(0.4, 0.4, 0.4), width=4)
    page.insert_text((394, 120), "Quarry Road", fontsize=9, rotate=90)
    doc.save(str(p))
    src = open_source(p)
    labs = from_pdf(src)
    by = {l.text: l for l in labs}
    assert set(by) >= {"Cedar Avenue", "Quarry Road"}
    assert by["Cedar Avenue"].angle % 180 == pytest.approx(0, abs=1)
    assert by["Quarry Road"].angle % 180 == pytest.approx(90, abs=1)
    assert by["Cedar Avenue"].height > 0 and by["Cedar Avenue"].width > by["Cedar Avenue"].height
    # the two drawn streets, in image pixels
    to_px = src.page_to_px
    h = Feature(LineString([to_px(50, 200), to_px(550, 200)]), "pdf")
    v = Feature(LineString([to_px(400, 40), to_px(400, 360)]), "pdf")
    hits = match(labs, [("Roads", "line", h), ("Roads", "line", v)])
    assert names(hits) == {h.fid: "Cedar Avenue", v.fid: "Quarry Road"}


# ---------------------------------------------------------------- session: names, undo, export
@pytest.fixture
def placed(tmp_path):
    from fake_extract import make_pdf
    p = tmp_path / "fake_sheet.pdf"
    make_pdf(p)
    return open_source(p)


def test_rename_undo_redo_and_grouped_steps(placed):
    S = Session(placed)
    road = Feature(LineString([(0, 120), (1200, 120)]), "line")
    lab = Feature(Point(600, 110), "label", 0.9, "Pine Road")
    S.add("Roads", road); S.add("Landmarks", lab)
    with S.group():
        S.rename("Roads", road, "Pine Road")
        S.remove("Landmarks", lab)
    assert road.name == "Pine Road" and not S.layers["Landmarks"].features
    S.undo()                                   # one step undoes both
    assert road.name == "" and S.layers["Landmarks"].features == [lab]
    S.redo()
    assert road.name == "Pine Road" and not S.layers["Landmarks"].features


def test_export_has_a_name_column(placed, tmp_path):
    import pyogrio
    S = Session(placed)
    road = Feature(LineString([(0, 120), (1200, 120)]), "line"); road.name = "Pine Road"
    S.add("Roads", road)
    written, notes = S.export(tmp_path / "out", ("gpkg", "shp", "kml"))
    assert not notes, notes
    df = pyogrio.read_dataframe(next(p for p in written if p.suffix == ".gpkg"), layer="Roads")
    assert df["name"].iloc[0] == "Pine Road"
    shp = pyogrio.read_dataframe(next(p for p in written if p.suffix == ".shp"))
    assert shp["name"].iloc[0] == "Pine Road"
    kml = next(p for p in written if p.suffix == ".kml").read_text(encoding="utf-8")
    assert "Pine Road" in kml
