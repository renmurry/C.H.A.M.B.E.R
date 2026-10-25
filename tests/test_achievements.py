import importlib
from chamber import achievements as A


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    importlib.reload(A)
    return A


def test_unlocks_and_streak(tmp_path, monkeypatch):
    a = _fresh(tmp_path, monkeypatch)
    s, newly = a.record_run({"ok": 5, "flagged": 0, "failed": 0},
                            ["geojson", "kml", "shp", "gpkg", "dxf"])
    names = {n for _, n, _ in newly}
    assert {"First Light", "Spotless", "Polyglot"} <= names
    assert s["clean_streak"] == 1

    # a failure breaks the streak and earns no clean badge
    s, newly = a.record_run({"ok": 2, "flagged": 0, "failed": 1}, ["geojson"])
    assert s["clean_streak"] == 0
    assert newly == []


def test_no_double_unlock_and_persist(tmp_path, monkeypatch):
    a = _fresh(tmp_path, monkeypatch)
    a.record_run({"ok": 1, "flagged": 0, "failed": 0}, ["geojson"])
    _, newly = a.record_run({"ok": 1, "flagged": 0, "failed": 0}, ["geojson"])
    assert all(n != "First Light" for _, n, _ in newly)   # already earned
    assert a.load_stats()["total_blocks"] == 2            # persisted across calls
