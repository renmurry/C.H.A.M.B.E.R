"""The neon title: the acronym's initials, and click -> glitch -> acronym ->
(6 s) -> back to the subtitle."""
import os
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from chamber import gui as G  # noqa: E402


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def test_initials_spell_the_name():
    idx = G.acronym_initials(G.ACRONYM)
    assert "".join(G.ACRONYM[i] for i in idx) == "CHAMBER"
    assert len(idx) == 7                      # "for" and "&" are skipped


def test_click_glitches_shows_acronym_then_returns_by_itself():
    app = QApplication.instance() or QApplication([])
    clk = Clock()
    w = G.NeonTitle(G.APP, G.SUBTITLE, G.ACRONYM, clock=clk)
    assert w._sub_text() == (G.SUBTITLE, False)
    w.trigger()
    assert w.mode == "glitch_in"
    for dt, expect in ((0.41, "decode_in"), (0.76, "shown"), (5.9, "shown"), (0.2, "glitch_out"),
                       (0.31, "decode_out"), (0.51, "sub")):
        clk.t += dt; w.step()
        assert w.mode == expect, (dt, w.mode)
    assert w._sub_text() == (G.SUBTITLE, False)


def test_click_while_showing_hides_it_now():
    app = QApplication.instance() or QApplication([])
    clk = Clock()
    w = G.NeonTitle(G.APP, G.SUBTITLE, G.ACRONYM, clock=clk)
    w.trigger(); clk.t += 0.41; w.step(); clk.t += 0.76; w.step()
    assert w.mode == "shown" and w._sub_text() == (G.ACRONYM, True)
    w.trigger()
    assert w.mode == "glitch_out"


def test_hover_lights_only_that_letter():
    app = QApplication.instance() or QApplication([])
    w = G.NeonTitle(G.APP, G.SUBTITLE, G.ACRONYM, clock=Clock())
    w.resize(600, 60); w.grab()                # paint once so letter positions exist
    w.hover = 2                                # the 'H'
    for _ in range(40):
        w.step()
    assert w.glow[2] == 1.0 and all(g == 0.0 for i, g in enumerate(w.glow) if i != 2)
