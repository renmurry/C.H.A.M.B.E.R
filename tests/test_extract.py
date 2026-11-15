"""The Extract engine on a made-up map: placement, drawn lines, outlines,
squaring, road snapping, find similar, labels, undo and export."""
import numpy as np
import pytest
from shapely.geometry import Point, Polygon, box
from fake_extract import make_pdf, photo, TREES, ROOF, ROAD_Y, GSD, E0, N0, W_PX, H_PX

from chamber.extract.source import open_source
from chamber.extract import gridref, pdfvec, shapes, labels
from chamber.extract.session import Session, Feature
from chamber.extract import sam

needs_model = pytest.mark.skipif(not sam.available(), reason="model files not present")


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    p = tmp_path_factory.mktemp("x") / "fake_sheet.pdf"
    make_pdf(p)
    return p


@pytest.fixture(scope="module")
def src(pdf):
    return open_source(pdf)


def test_placed_from_grid_labels(src):
    assert src.placement.startswith("Grid labels")
    assert src.epsg == 32636
    assert src.gsd == pytest.approx(GSD, rel=0.01)
    X, Y = src.to_map(0, 0)
    assert float(X) == pytest.approx(E0, abs=0.2) and float(Y) == pytest.approx(N0, abs=0.2)


def test_no_labels_means_pixels(tmp_path):
    p = tmp_path / "plain.pdf"; make_pdf(p, labels=False)
    s = open_source(p)
    assert not s.placed and s.placement.startswith("None")
    X, Y = s.to_map(10, 20)
    assert (float(X), float(Y)) == (10.0, -20.0)


def test_labels_without_crs_ask_for_one(tmp_path):
    p = tmp_path / "nocrs.pdf"; make_pdf(p, epsg_text=False)
    s = open_source(p)
    assert s.placed and s.epsg is None and any("pick one" in n for n in s.notes)


def test_world_file_png(tmp_path):
    from PIL import Image
    p = tmp_path / "ortho.png"; Image.fromarray(photo()).save(p)
    (tmp_path / "ortho.pgw").write_text(f"{GSD}\n0\n0\n{-GSD}\n{E0 + GSD / 2}\n{N0 - GSD / 2}\n")
    s = open_source(p)
    assert s.placed and s.placement == "World file"
    assert float(s.to_map(0, 0)[0]) == pytest.approx(E0, abs=0.01)


def test_drawn_lines_grouped_by_style(src):
    st = pdfvec.read_styles(src)
    red = next(s for s in st if s.label.startswith("Red line"))
    g = pdfvec.style_geometries(red, (W_PX, H_PX))[0]
    x0, y0, x1, y1 = ROOF
    assert g.area == pytest.approx((x1 - x0) * (y1 - y0), rel=0.02)
    orange = next(s for s in st if s.label.startswith("Orange line"))
    road = pdfvec.style_geometries(orange, (W_PX, H_PX))[0]
    assert road.length == pytest.approx(W_PX, rel=0.01)
    assert pdfvec.nearest_style(st, 600, sum(ROAD_Y) / 2 + 2, 6) is orange


def test_square_up_makes_a_rectangle():
    rng = np.random.default_rng(1)
    pts = [(x + rng.normal(0, 1.2), y + rng.normal(0, 1.2)) for x, y in
           [(0, 0)] + [(i, 0) for i in range(10, 100, 10)] + [(100, 0), (100, 60), (0, 60)]]
    sq = shapes.square_up(Polygon(pts))
    assert len(sq.exterior.coords) == 5
    assert sq.area == pytest.approx(6000, rel=0.05)


def test_snap_line_stays_on_the_road():
    img = photo()
    yc = sum(ROAD_Y) / 2
    line = shapes.snap_line(img, [(40, yc + 20), (600, yc - 20), (1150, yc + 15)], gsd=GSD)
    ys = np.array(line.coords)[:, 1]
    assert ys.min() >= ROAD_Y[0] - 3 and ys.max() <= ROAD_Y[1] + 3


def test_mask_to_polygon():
    m = np.zeros((100, 100), bool); m[20:60, 30:80] = True
    p = shapes.mask_to_polygon(m, 5, 7)
    assert p.area == pytest.approx(40 * 50, rel=0.06)
    assert p.bounds[0] == pytest.approx(35, abs=2)


def test_text_labels_from_pdf(src):
    found = labels.read_labels(src)
    names = [t for t, *_ in found]
    assert not any(t.endswith(" E") or t.endswith(" N") for t in names)   # grid labels left out


@needs_model
def test_click_outlines_a_tree(src):
    seg = sam.Segmenter(src.image, src.gsd)
    cx, cy, r = TREES[0]
    res = seg.predict([(cx, cy)], [1])
    poly = shapes.mask_to_polygon(res.masks[0], res.window.x0, res.window.y0)
    assert poly.area == pytest.approx(np.pi * r * r, rel=0.25)
    assert poly.contains(Point(cx, cy))


@needs_model
def test_box_outlines_the_roof(src):
    seg = sam.Segmenter(src.image, src.gsd)
    x0, y0, x1, y1 = ROOF
    res = seg.predict(box=(x0 - 10, y0 - 10, x1 + 10, y1 + 10))
    poly = shapes.square_up(shapes.mask_to_polygon(res.masks[0], res.window.x0, res.window.y0))
    assert poly.intersection(box(*ROOF)).area / poly.union(box(*ROOF)).area > 0.8


@needs_model
def test_find_similar_finds_the_other_trees(src):
    from chamber.extract import similar
    seg = sam.Segmenter(src.image, src.gsd)
    cx, cy, _r = TREES[0]
    res = seg.predict([(cx, cy)], [1])
    ex = shapes.mask_to_polygon(res.masks[0], res.window.x0, res.window.y0)
    found = similar.find_similar(seg, [ex], strictness=0.8)
    hits = {i for c in found for i, (x, y, _) in enumerate(TREES[1:], 1) if c.poly.contains(Point(x, y))}
    assert hits == {1, 2}
    assert not any(c.poly.contains(Point((ROOF[0] + ROOF[2]) / 2, (ROOF[1] + ROOF[3]) / 2)) for c in found)


def test_session_undo_and_export(src, tmp_path):
    import pyogrio
    S = Session(src)
    x0, y0, x1, y1 = ROOF
    S.add("Buildings", Feature(box(x0, y0, x1, y1), "box", 0.97))
    S.add("Landmarks", [Feature(Point(100, 100), "label", 1.0, "Hall")])
    S.undo(); assert not S.layers["Landmarks"].features
    S.redo(); assert len(S.layers["Landmarks"].features) == 1
    kind, area, unit = S.measure(S.layers["Buildings"].features[0].geom)
    assert unit == "m²" and area == pytest.approx((x1 - x0) * (y1 - y0) * GSD ** 2, rel=0.01)
    written, notes = S.export(tmp_path, ("gpkg", "kml", "shp", "geojson", "dxf"))
    assert not notes, notes
    df = pyogrio.read_dataframe(next(p for p in written if p.suffix == ".gpkg"), layer="Buildings")
    assert df.crs.to_epsg() == 32636 and df["area_m2"].iloc[0] == pytest.approx(area, rel=0.01)
    kml = next(p for p in written if p.name.endswith("Buildings.kml")).read_text(encoding="utf-8")
    assert "area_m2" in kml and "<SimpleData" in kml


# ---------------------------------------------------------------- roads
def _t_junction_image():
    """Ground with a horizontal road (rows 200-260) and a side road going down
    from it (cols 560-600), plus a big roof that is a similar grey."""
    rng = np.random.default_rng(5)
    a = np.zeros((700, 1100, 3), np.uint8); a[:] = (170, 150, 110)
    a[200:260, :] = (90, 90, 96)
    a[260:700, 560:600] = (92, 92, 98)
    a[420:560, 120:330] = (120, 118, 125)                 # roof: greyish, not road
    return np.clip(a.astype(int) + rng.integers(-5, 6, a.shape), 0, 255).astype(np.uint8)


def test_red_loop_counts_inside():
    from chamber.extract.roads import Stroke
    loop = Stroke("red", [(100, 100), (300, 100), (300, 300), (100, 300), (105, 110)], 5)
    line = Stroke("red", [(100, 100), (300, 100), (300, 300)], 5)
    assert loop.closed() and not line.closed()


def test_road_brush_learns_and_traces_a_t_junction():
    from chamber.extract.roads import RoadLearner, Stroke
    img = _t_junction_image()
    L = RoadLearner(img, gsd=0.1)                          # 0.1 m per pixel
    strokes = [Stroke("road", [(50, 230), (450, 230)], 25),
               Stroke("red", [(110, 410), (340, 410), (340, 570), (110, 570), (115, 415)], 8)]
    prob = L.learn(strokes)
    assert prob is not None
    # the unpainted parts of the roads score high, the roof and the ground low
    cell = lambda x, y: prob[int(y * L.f), int(x * L.f)]
    assert cell(900, 230) > 0.6 and cell(580, 500) > 0.5
    assert cell(220, 490) < 0.4 and cell(800, 500) < 0.4
    # a short dab on the side road too (as you would), then trace
    strokes.append(Stroke("road", [(580, 330), (580, 380)], 15))
    L.learn(strokes)
    segs = L.extract(strokes, scope="grow")
    lines = [s.line for s in segs if not s.painted]
    assert len(lines) >= 3                                 # west arm, east arm, side road
    # they meet at one junction near (580, 230)
    from shapely.geometry import Point
    j = Point(580, 230)
    ends = [Point(l.coords[k]) for l in lines for k in (0, -1)]
    assert sum(e.distance(j) < 40 for e in ends) >= 3
    side = max(lines, key=lambda l: abs(l.coords[0][1] - l.coords[-1][1]))
    seg = next(s for s in segs if s.line is side)
    assert seg.width_m == pytest.approx(4.0, abs=1.2)     # side road is 40 px = 4 m wide
    assert all(abs(x - 580) < 15 for x, y in side.coords if y > 300)   # down the middle of it


def test_road_export_carries_width(src, tmp_path):
    import pyogrio
    from shapely.geometry import LineString
    S = Session(src)
    S.add("Roads", Feature(LineString([(0, 120), (1200, 120)]), "brush", 0.9, attrs={"width_m": 3.0}))
    written, notes = S.export(tmp_path, ("gpkg",))
    df = pyogrio.read_dataframe(written[0], layer="Roads")
    assert df["width_m"].iloc[0] == pytest.approx(3.0)
