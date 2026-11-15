"""Music and sound effects: rendered from code, loop cleanly, mix without clipping."""
import numpy as np
import pytest
from chamber import music as M
from chamber.audio import Mixer, Audio


def test_effects_are_short_and_clean():
    fx = M.effects()
    assert {"drop", "combo", "badge", "glitch", "found", "tick", "keep0", "keep9"} <= set(fx)
    for k, x in fx.items():
        assert x.ndim == 2 and x.shape[1] == 2 and x.shape[0] < 2 * M.SR, k
        assert np.isfinite(x).all() and np.abs(x).max() <= 1.0, k


@pytest.mark.parametrize("key", list(M.TRACKS))
def test_tracks_render_and_loop(key, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    x = M.track(key)                                  # renders and caches
    assert 55 < x.shape[0] / M.SR < 200
    assert np.isfinite(x).all() and np.abs(x).max() <= 0.9
    assert np.abs(x[-1] - x[0]).max() < 0.1          # the seam doesn't click
    y = M.track(key)                                  # second time: from the cache
    assert np.allclose(x, y, atol=1e-4)


def test_cipher_spells_the_theme():
    names = {62: "D", 64: "E", 66: "F#", 69: "A", 71: "B"}
    assert [names[m] for m in M.cipher("REN")] == ["F#", "B", "A"]
    assert [names[m] for m in M.cipher("LOVE")] == ["E", "B", "E", "B"]


def test_mixer_fades_music_and_plays_effects():
    m = Mixer()
    m.set_music(np.full((M.SR * 2, 2), 0.5, np.float32)); m.music_vol = 1.0; m.music_target = 1.0
    first = m.block(512)
    assert 0 <= first[0, 0] < first[-1, 0] < 0.5     # fades in, no jump
    m.add(np.ones((100, 2), np.float32), gain=2.0)
    out = m.block(256)
    assert np.abs(out).max() <= 1.0                  # never clips past full scale
    m.block(256)
    assert not m.voices                              # finished effects are dropped


def test_audio_without_a_device_stays_silent(monkeypatch):
    import builtins
    real = builtins.__import__
    def no_sd(name, *a, **k):
        if name == "sounddevice":
            raise OSError("no PortAudio")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_sd)
    a = Audio(); a.set_mode("all"); a.play("tick")
    assert a.stream is None and not a.available
