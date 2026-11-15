"""Sound: a tiny mixer that plays one looping music track plus short effects.

Modes: "off" (nothing, the sound device isn't even opened), "fx" (effects
only) and "all" (effects and music). If no sound device or library is
available everything simply stays silent; the app never fails because of sound.
"""
from __future__ import annotations
import random, threading
import numpy as np
from . import music as M

MODES = ["off", "fx", "all"]


class Mixer:
    """Pure mixing logic, no device: easy to test."""

    def __init__(self):
        self.lock = threading.Lock()
        self.voices = []                  # [array, position, gain]
        self.music = None; self.mpos = 0
        self.music_gain = 0.0; self.music_target = 0.0
        self.music_vol = 0.55; self.fx_vol = 0.8
        self.next_music = None            # called when the loop ends (shuffle)

    def add(self, x, gain=1.0):
        with self.lock:
            if len(self.voices) > 12:
                self.voices.pop(0)
            self.voices.append([x, 0, gain])

    def set_music(self, x):
        with self.lock:
            self.music, self.mpos = x, 0

    def block(self, frames):
        out = np.zeros((frames, 2), np.float32)
        with self.lock:
            m = self.music
            if m is not None and (self.music_gain > 0 or self.music_target > 0):
                # gain glides toward the target: fades in/out, no clicks
                g0 = self.music_gain
                step = np.sign(self.music_target - g0) * min(abs(self.music_target - g0), frames / M.SR / 1.5)
                g1 = g0 + step
                ramp = np.linspace(g0, g1, frames, dtype=np.float32)[:, None]
                idx = (self.mpos + np.arange(frames)) % m.shape[0]
                out += m[idx] * ramp * self.music_vol
                wrapped = self.mpos + frames >= m.shape[0]
                self.mpos = (self.mpos + frames) % m.shape[0]
                self.music_gain = g1
                if wrapped and self.next_music:
                    nxt = self.next_music()
                    if nxt is not None:
                        self.music, self.mpos = nxt, 0
            keep = []
            for v in self.voices:
                x, p, g = v
                n = min(frames, x.shape[0] - p)
                out[:n] += x[p:p + n] * g * self.fx_vol
                v[1] = p + n
                if v[1] < x.shape[0]:
                    keep.append(v)
            self.voices = keep
        np.clip(out, -1, 1, out=out)
        return out


class Audio:
    def __init__(self):
        self.mixer = Mixer()
        self.mode = "off"
        self.stream = None
        self.fx = None
        self.track_key = "lanterns"
        self.available = True
        self._loading = False
        self._tracks = {}

    # ---------- device ----------
    def _open(self):
        if self.stream is not None or not self.available:
            return self.stream is not None
        try:
            import sounddevice as sd
            self.stream = sd.OutputStream(samplerate=M.SR, channels=2, dtype="float32",
                                          callback=lambda out, frames, t, st: out.__setitem__(slice(None), self.mixer.block(frames)))
            self.stream.start()
            return True
        except Exception:
            self.available = False; self.stream = None
            return False

    def _close(self):
        if self.stream is not None:
            try:
                self.stream.stop(); self.stream.close()
            except Exception:
                pass
            self.stream = None

    # ---------- controls ----------
    def set_mode(self, mode):
        self.mode = mode if mode in MODES else "off"
        if self.mode == "off":
            self.mixer.music_target = 0.0
            self._close(); return
        if self.fx is None:
            self.fx = M.effects()
        if not self._open():
            return
        if self.mode == "all":
            self._start_music()
        else:
            self.mixer.music_target = 0.0

    def set_track(self, key):
        """'lanterns', 'static', 'ember', 'sunshine', 'contours' or 'shuffle'."""
        self.track_key = key
        if self.mode == "all":
            self._start_music(restart=True)

    def set_volumes(self, music=None, fx=None):
        if music is not None:
            self.mixer.music_vol = float(music)
        if fx is not None:
            self.mixer.fx_vol = float(fx)

    def _get(self, key):
        if key not in self._tracks:
            self._tracks[key] = M.track(key)
        return self._tracks[key]

    def _start_music(self, restart=False):
        if self._loading:
            return
        keys = list(M.TRACKS)
        first = random.choice(keys) if self.track_key == "shuffle" else self.track_key
        if self.mixer.music is not None and not restart:
            self.mixer.music_target = 1.0; return
        def load():
            self._loading = True
            try:
                x = self._get(first)
                self.mixer.set_music(x)
                if self.track_key == "shuffle":
                    state = {"k": first}
                    def nxt():                  # next track in turn when the loop ends
                        state["k"] = keys[(keys.index(state["k"]) + 1) % len(keys)]
                        return self._tracks.get(state["k"])
                    for k in keys:              # render the other one in the background
                        self._get(k)
                    self.mixer.next_music = nxt
                else:
                    self.mixer.next_music = None
                self.mixer.music_gain = 0.0
                self.mixer.music_target = 1.0 if self.mode == "all" else 0.0
            finally:
                self._loading = False
        threading.Thread(target=load, daemon=True).start()

    def play(self, name, gain=1.0):
        if self.mode == "off" or self.stream is None or not self.fx:
            return
        x = self.fx.get(name)
        if x is not None:
            self.mixer.add(x, gain)

    def shutdown(self):
        self._close()
