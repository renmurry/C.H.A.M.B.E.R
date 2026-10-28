"""End to end through the desktop app: pick folders, press Run on the sample
sheets, and check the window reports the finished run and the files exist."""
import os, shutil, time
from pathlib import Path
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CHAMBER_GLASS"] = "off"

SAMPLES = Path(__file__).parent.parent / "samples"


def test_run_button_processes_the_samples(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    from chamber import gui as G
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "qsettings"))
    app = QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(G.Finished, "exec", lambda self: shown.append(self) or 0)   # don't block on the dialog

    indir = tmp_path / "in"; indir.mkdir()
    for p in SAMPLES.glob("*.pdf"):
        shutil.copy(p, indir / p.name)
    out = tmp_path / "out"
    w = G.App()
    w.in_edit.setText(str(indir)); w.out_edit.setText(str(out))
    w.jobs.setValue(1)
    w._run()
    assert not w.run_btn.isEnabled()                  # busy while it works
    t0 = time.time()
    while not shown and time.time() - t0 < 180:
        app.processEvents(); time.sleep(0.05)
    assert shown, "the run never finished"
    assert w.run_btn.isEnabled()
    assert w.bar._v == 1.0
    log = w.log.toPlainText()
    assert "Done: 3 ok, 0 flagged, 0 failed." in log, log
    files = sorted(p.name for p in out.iterdir())
    assert "sample_A_block.geojson" in files and "sample_A_block.kml" in files
    assert not any(f.endswith("_georef.tif") for f in files)     # GeoTIFF off by default
    assert not any(f.endswith("_debug.png") for f in files)      # clean sheets: no debug images
    w.close()
