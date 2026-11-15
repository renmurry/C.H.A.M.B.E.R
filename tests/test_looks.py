"""Six looks, the title-click switch, and the layout waiting for Keep / Drop."""
import os, random
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from chamber import themes as TM


def test_next_look_never_repeats():
    rng = random.Random(1)
    i = 0
    for _ in range(200):
        n = TM.next_look(i, rng=rng)
        assert n != i and 0 <= n < len(TM.LOOKS)
        i = n
    assert TM.next_look(5, order="in turn") == 0


def test_every_style_builds_a_stylesheet():
    for t in TM.THEMES.values():
        q = TM.qss(t)
        assert t.text in q and "QFrame#float" in q


def test_badges_for_looks(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from chamber import achievements as A
    got = []
    for i in range(6):
        got += A.record_event(f"look:{i}")
    assert [b for b, *_ in got] == ["shape_shifter"]
    assert [b for b, *_ in A.record_event("features", 1)] == ["first_outline"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    qa = QApplication.instance() or QApplication([])
    from chamber import gui
    w = gui.App(); w.show(); qa.processEvents()
    yield qa, w
    w.close()


def test_title_click_switches_look(app):
    qa, w = app
    before = w.look
    w._next_look()
    assert w.look != before
    assert TM.current().key == TM.LOOKS[w.look][0]


def test_layout_waits_for_keep_or_drop(app):
    qa, w = app
    from shapely.geometry import box
    from chamber.gui_extract import Pending
    E = w.extract
    w.apply_look(0, announce=False)                       # Frost, side panels
    E.pending = Pending("Buildings", [box(0, 0, 10, 10)], [0.9], "click")
    w.apply_look(3, announce=False)                       # Focus + Frost
    assert TM.current().key == "frost" and E.layout_mode == "cols" and w._layout_wait == "focus"
    E.pending = None; E._settle()
    assert E.layout_mode == "focus" and w._layout_wait is None


def test_extract_page_opens_and_takes_drawn_lines(app, tmp_path):
    import time
    from fake_extract import make_pdf
    qa, w = app
    p = tmp_path / "fake_sheet.pdf"; make_pdf(p)
    E = w.extract
    E.open_files([str(p)])
    t = time.time()
    while (E._job or not E.files) and time.time() - t < 30:
        qa.processEvents(); time.sleep(0.02)
    assert E.cur and E.cur.src.placed
    i = next(k for k, s in enumerate(E.cur.styles) if s.label.startswith("Orange line"))
    E.active_layer = "Roads"
    E.style_list.setCurrentRow(i); E._take_style()
    assert len(E.cur.session.layers["Roads"].features) == 1
    E.undo()
    assert len(E.cur.session.layers["Roads"].features) == 0


def test_close_files_and_unsaved_guard(app, tmp_path, monkeypatch):
    import time
    from PySide6.QtWidgets import QMessageBox
    from shapely.geometry import box
    from fake_extract import make_pdf
    from chamber.extract.session import Feature
    qa, w = app
    E = w.extract
    paths = []
    for n in ("a", "b"):
        p = tmp_path / f"{n}.pdf"; make_pdf(p); paths.append(str(p))
    E.open_files(paths)
    t = time.time()
    while (E._job or len(E.files) < 2) and time.time() - t < 30:
        qa.processEvents(); time.sleep(0.02)
    E.cur.session.add("Buildings", Feature(box(0, 0, 10, 10), "box"))
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(1), QMessageBox.No)[1])
    E.close_current()                                     # unsaved: asks, answer No
    assert asked and len(E.files) == 2
    E.cur.session.export(tmp_path / "out", ("gpkg",))     # exported: closes without asking
    asked.clear(); E.close_current()
    assert not asked and len(E.files) == 1 and E.cur is E.files[0]
    E.close_files([0])
    assert not E.files and E.cur is None and E.map.pix is None


def test_road_brush_end_to_end(app, tmp_path):
    import time
    from fake_extract import make_pdf, ROAD_Y
    qa, w = app
    E = w.extract
    p = tmp_path / "roads.pdf"; make_pdf(p)
    E.open_files([str(p)])
    def wait(cond, s=60):
        t = time.time()
        while not cond() and time.time() - t < s:
            qa.processEvents(); time.sleep(0.02)
    wait(lambda: E.files and not E._job)
    E.set_tool("brush")
    yc = sum(ROAD_Y) / 2
    E.map.brush_px = 25
    E._on_painted([(60, yc), (300, yc), (500, yc)])
    wait(lambda: not E._job)
    assert E.cur.roads is not None and E.cur.roads.prob is not None
    E.find_roads(); wait(lambda: not E._job)
    assert E.pending is not None and E.pending.surface is not None
    E.accept_all()
    roads = E.cur.session.layers["Roads"].features
    assert roads and "width_m" in roads[0].attrs
    assert E.cur.session.layers["Roads surface"].features
