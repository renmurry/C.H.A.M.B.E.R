"""Original music and sound effects, synthesised from code (numpy only).

Three looping tracks, written for this app:
  "Paper Lanterns" - bright synth-pop: sparkly arpeggios, bells, airy pads, 122 bpm.
  "Static Hearts"  - heavy and electronic: piano motif, drum machine, palm-muted
                     chugs into a wall of distorted power chords, 100 bpm.
  "Ember Hours"    - lofi piano, 76 bpm: a rolling minor-key piano over a dusty
                     swung beat, a swelling choir-and-pad lift, then a quiet
                     guitar-and-piano section before the beat comes home.
  "Pocket Sunshine" - lively stride piano, 132 bpm: bouncing left hand, a
                     skipping right-hand tune, brushes, snaps and a glockenspiel.
  "Contours"       - the long one, about three minutes in seven parts: a single
                     point, contour lines, the ride, friction, the campfire, the
                     overview, home. Its theme is spelled from letters (see
                     cipher()).

Nothing is sampled or copied: every sound is built here from sine/saw waves and
noise, and every melody is written below. A track is rendered once (a few
seconds), then cached as a WAV in %APPDATA%\\CHAMBER\\music, so later starts are
instant. Change VERSION to re-render after editing.
"""
from __future__ import annotations
import os
import numpy as np

SR = 32000
VERSION = 1
TRACKS = {"lanterns": "Paper Lanterns", "static": "Static Hearts", "ember": "Ember Hours",
          "sunshine": "Pocket Sunshine", "contours": "Contours"}


# ------------------------------------------------------------------ building blocks
def mtof(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


def t_(n):
    return np.arange(n) / SR


def env(n, a=0.005, d=0.1, s=0.7, r=0.1, hold=None):
    """ADSR envelope of length n samples; 'hold' = seconds before release."""
    hold = n / SR - r if hold is None else hold
    t = t_(n)
    e = np.where(t < a, t / max(a, 1e-6), 1.0)
    dec = (t >= a) & (t < a + d)
    e[dec] = 1 - (1 - s) * (t[dec] - a) / max(d, 1e-6)
    e[t >= a + d] = s
    rel = t >= hold
    if rel.any():
        e0 = e[np.argmax(rel)] if rel.any() else s
        e[rel] = e0 * np.clip(1 - (t[rel] - hold) / max(r, 1e-6), 0, 1)
    return e


def saw(f, n, phase=0.0):
    p = (t_(n) * f + phase) % 1.0
    return 2 * p - 1


def tri(f, n):
    p = (t_(n) * f) % 1.0
    return 4 * np.abs(p - 0.5) - 1


def sine(f, n, phase=0.0):
    return np.sin(2 * np.pi * (t_(n) * f + phase))


def spectral(x, fn):
    """Filter by multiplying the spectrum with fn(freqs)."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / SR)
    g = fn(f)
    X *= g[:, None] if X.ndim == 2 else g
    return np.fft.irfft(X, n=x.shape[0], axis=0)


def lowpass(x, fc, order=2):
    return spectral(x, lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * order)))


def highpass(x, fc, order=2):
    return spectral(x, lambda f: 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** (2 * order)))


def bandpass(x, fc, q=1.0):
    return spectral(x, lambda f: 1 / (1 + (q * (f / fc - fc / np.maximum(f, 1e-3))) ** 2))


def reverb(x, seconds=1.8, mix=0.25, seed=0, tone=6000):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    ir = rng.standard_normal((n, 2)) * np.exp(-t_(n) / (seconds / 5))[:, None]
    ir = lowpass(ir, tone)
    ir /= np.sqrt((ir ** 2).sum(axis=0))
    L = x.shape[0] + n
    N = 1 << (L - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(x, N, axis=0) * np.fft.rfft(ir, N, axis=0), N, axis=0)[:x.shape[0] + n]
    out = np.zeros_like(wet); out[:x.shape[0]] = x
    return out * (1 - mix) + wet * mix * 3


def delay(x, seconds, fb=0.35, n=4, pingpong=True):
    d = int(seconds * SR)
    out = np.concatenate([x, np.zeros((d * n, 2))])
    g = 1.0
    for k in range(1, n + 1):
        g *= fb
        seg = x[:, ::-1] if (pingpong and k % 2) else x
        out[d * k:d * k + x.shape[0]] += seg * g
    return out


def stereo(m, pan=0.0):
    l = np.cos((pan + 1) * np.pi / 4); r = np.sin((pan + 1) * np.pi / 4)
    return np.column_stack([m * l, m * r])


class Track:
    """A buffer you drop notes into by time; long notes may run past the end
    (they are folded back to the start so the loop is seamless)."""

    def __init__(self, bpm, bars, tail=4.0):
        self.bpm = bpm; self.beat = 60 / bpm
        self.length = int(round(bars * 4 * self.beat * SR))
        self.buf = np.zeros((self.length + int(tail * SR), 2))

    def at(self, bar, beat=0.0):
        return int(round((bar * 4 + beat) * self.beat * SR))

    def add(self, x, start, gain=1.0):
        if start < 0:
            return
        end = min(start + x.shape[0], self.buf.shape[0])
        self.buf[start:end] += x[:end - start] * gain

    def loop(self):
        out = self.buf[:self.length].copy()
        tail = self.buf[self.length:]
        k = min(tail.shape[0], out.shape[0])
        out[:k] += tail[:k]
        return out


def master(x, drive=1.15, peak=0.89):
    x = x - x.mean(axis=0)
    x = np.tanh(x / np.abs(x).max() * drive) / np.tanh(drive)
    return x * peak


# ------------------------------------------------------------------ instruments
def kick(punch=1.0, length=0.32):
    n = int(length * SR); t = t_(n)
    f = 45 + 95 * punch * np.exp(-t / 0.035)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.11 + 0.05 * punch))
    click = np.random.default_rng(1).standard_normal(n) * np.exp(-t / 0.004) * 0.25
    return stereo(x + click)


def snare(tone=190, length=0.25, bright=4000, seed=2):
    n = int(length * SR); t = t_(n)
    rng = np.random.default_rng(seed)
    noise = bandpass(rng.standard_normal(n), bright, 0.7) * np.exp(-t / 0.07)
    body = np.sin(2 * np.pi * tone * t) * np.exp(-t / 0.05)
    return stereo(noise * 1.4 + body * 0.7)


def clap(seed=3):
    n = int(0.3 * SR); t = t_(n)
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for k, off in enumerate((0, 0.011, 0.022)):
        i = int(off * SR)
        x[i:] += rng.standard_normal(n - i) * np.exp(-(t[:n - i]) / (0.012 if k < 2 else 0.09))
    return stereo(bandpass(x, 1500, 0.9), 0.05)


def hat(length=0.05, seed=4, open_=False):
    n = int((0.35 if open_ else length) * SR); t = t_(n)
    x = highpass(np.random.default_rng(seed).standard_normal(n), 7500, 3) * np.exp(-t / (0.12 if open_ else 0.018))
    return stereo(x)


def crash(seed=5):
    n = int(2.2 * SR); t = t_(n)
    x = highpass(np.random.default_rng(seed).standard_normal(n), 4500, 2) * np.exp(-t / 0.55)
    return np.column_stack([x, np.roll(x, 37)]) * 0.6


def pluck(m, dur, bright=1.0):
    f = float(mtof(m)); n = int((dur + 0.3) * SR); t = t_(n)
    x = (0.6 * tri(f, n) + 0.4 * np.sign(np.sin(2 * np.pi * f * t)) * 0.5) * np.exp(-t / (0.16 * bright))
    return lowpass(x, 2500 + 4000 * bright)


def bell(m, dur=1.2):
    f = float(mtof(m)); n = int((dur + 0.8) * SR); t = t_(n)
    idx = 2.2 * np.exp(-t / 0.25)
    x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * 3.5 * f * t)) * np.exp(-t / 0.7)
    x += 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.3)
    return x


def pad(notes, dur, seed=0, cutoff=2400):
    n = int((dur + 1.2) * SR)
    rng = np.random.default_rng(seed)
    L = np.zeros(n); R = np.zeros(n)
    for m in notes:
        f = float(mtof(m))
        for k, det in enumerate((-0.11, 0.0, 0.13)):
            ph = rng.random()
            w = saw(f * 2 ** (det / 12), n, ph)
            (L if k != 2 else R)[:] += w
            (R if k != 0 else L)[:] += w * 0.6
    e = env(n, a=0.45, d=0.4, s=0.85, r=1.1, hold=dur)
    x = np.column_stack([L, R]) * e[:, None] / (len(notes) * 3)
    return lowpass(x, cutoff, 2)


def bass(m, dur, saw_mix=0.35):
    f = float(mtof(m)); n = int((dur + 0.05) * SR)
    x = sine(f, n) + saw_mix * lowpass(saw(f, n), 600)
    return x * env(n, a=0.004, d=0.08, s=0.8, r=0.04, hold=dur)


def piano(m, dur, vel=1.0):
    f = float(mtof(m)); n = int((dur + 1.5) * SR); t = t_(n)
    x = np.zeros(n)
    for k, a in enumerate((1.0, 0.45, 0.25, 0.12, 0.06), 1):
        x += a * np.sin(2 * np.pi * f * k * 1.0008 ** (k - 1) * t) * np.exp(-t * (1.4 + 0.9 * k))
    ham = np.random.default_rng(int(m)).standard_normal(n) * np.exp(-t / 0.003) * 0.08
    x = (x + ham) * vel
    rel = np.clip(1 - (t - dur) / 0.25, 0, 1); x *= np.where(t > dur, rel, 1)
    return x


def guitar(roots, dur, mute=False, seed=0, gain=9.0):
    """Power chord(s): root, fifth, octave from several detuned saws, driven
    hard and filtered like a speaker cabinet. Returns stereo (double-tracked)."""
    n = int((dur + (0.05 if mute else 0.35)) * SR)
    rng = np.random.default_rng(seed)
    takes = []
    for side in (0, 1):
        x = np.zeros(n)
        for r in roots:
            for iv in (0, 7, 12):
                f = float(mtof(r + iv)) * 2 ** (rng.normal(0, 0.06) / 12)
                x += saw(f, n, rng.random()) * (1.0 if iv != 12 else 0.6)
        x = lowpass(x, 1100 if mute else 3200, 1)
        e = env(n, a=0.003, d=0.06 if mute else 0.2, s=0.25 if mute else 0.9, r=0.05 if mute else 0.3, hold=dur)
        x = np.tanh(gain * x * e / len(roots))
        x = highpass(lowpass(x, 4200 if not mute else 2600, 2), 90)
        takes.append(x)
    return np.column_stack(takes) * 0.5


def riser(seconds, seed=7):
    n = int(seconds * SR); t = t_(n)
    x = np.random.default_rng(seed).standard_normal(n)
    out = np.zeros(n); seg = SR // 8
    for i in range(0, n, seg):
        fc = 400 * (12000 / 400) ** (i / n)
        out[i:i + seg] = bandpass(x[i:i + seg], fc, 2.0)
    return stereo(out * (t / seconds) ** 2)


def scratch(seed=8):
    n = int(0.42 * SR); t = t_(n)
    x = np.random.default_rng(seed).standard_normal(n)
    out = np.zeros(n); seg = SR // 100
    for i in range(0, n, seg):
        fc = 900 + 700 * np.sin(2 * np.pi * 7 * i / SR) ** 2
        out[i:i + seg] = bandpass(x[i:i + seg], fc, 4)
    return stereo(out * np.sin(np.pi * t / t[-1]) ** 0.5, -0.2)


# ------------------------------------------------------------------ track 1
def paper_lanterns():
    T = Track(122, 32)
    D, A, Bm, G, Fs, Em = 62, 57, 59, 55, 54, 52
    prog_a = [(D, (0, 4, 7)), (A, (0, 4, 7)), (Bm, (0, 3, 7)), (G, (0, 4, 7))]
    prog_b = [(G, (0, 4, 7)), (A, (0, 4, 7)), (Fs, (0, 3, 7)), (Bm, (0, 3, 7))]
    pads, arps, bells, bassb, drums = (np.zeros_like(T.buf) for _ in range(5))
    def put(buf, x, s, g=1.0):
        e = min(s + x.shape[0], buf.shape[0]); buf[s:e] += x[:e - s] * g
    chords = []
    for bar in range(32):
        prog = prog_b if 16 <= bar < 24 else prog_a
        chords.append(prog[bar % 4])
    for bar, (root, tri_) in enumerate(chords):
        s = T.at(bar)
        notes = [root + i for i in tri_]
        put(pads, pad(notes + [root + 12], 4 * T.beat, seed=bar), s, 0.55)
        # arpeggio: 16ths over chord tones, up an octave in the chorus
        up = 12 if 16 <= bar < 24 else 0
        pattern = [0, 1, 2, 3, 2, 1, 2, 3] * 2
        tones = [notes[0] + 12, notes[1] + 12, notes[2] + 12, notes[0] + 24]
        for k, p in enumerate(pattern):
            put(arps, stereo(pluck(tones[p] + up, T.beat / 4, 0.8 + 0.4 * (k % 4 == 0)), 0.25 * ((k % 2) * 2 - 1)),
                T.at(bar, k / 4), 0.35 if bar >= 2 else 0.2 * (bar + 1))
        # bass: 8ths on the root, from bar 8, rests in the breakdown
        if bar >= 8 and not (28 <= bar < 30):
            for k in range(8):
                put(bassb, stereo(bass(root - 24, T.beat / 2 * 0.9)), T.at(bar, k / 2), 0.9)
    # bells: an original melody in D major pentatonic, two-bar phrases
    phrase_1 = [(0, 1.5, 81), (1.5, 0.5, 83), (2, 1, 81), (3, 1, 78), (4, 1.5, 76), (5.5, 0.5, 78), (6, 2, 74)]
    phrase_2 = [(0, 1, 78), (1, 1, 81), (2, 1.5, 83), (3.5, 0.5, 86), (4, 1, 83), (5, 1, 81), (6, 2, 78)]
    phrase_3 = [(0, 0.5, 74), (0.5, 0.5, 76), (1, 1, 78), (2, 1, 81), (3, 1, 78), (4, 2, 83), (6, 1, 81), (7, 1, 78)]
    def phrase(bar0, notes, gain):
        for beat, dur, m in notes:
            put(bells, stereo(bell(m, dur * T.beat), 0.15), T.at(bar0, beat), gain)
    for b0 in (4, 12):
        phrase(b0, phrase_1, 0.22)
    for b0, ph in ((16, phrase_1), (18, phrase_2), (20, phrase_1), (22, phrase_3)):
        phrase(b0, ph, 0.32)
    for b0, ph in ((24, phrase_2), (26, phrase_3)):
        phrase(b0, ph, 0.24)
    # drums
    K, C, H, OH = kick(0.8), clap(), hat(), hat(open_=True)
    for bar in range(32):
        breakdown = 28 <= bar < 30
        if bar >= 8 and not breakdown:
            for b in range(4):
                put(drums, K, T.at(bar, b), 0.9)
            for b in (1, 3):
                put(drums, C, T.at(bar, b), 0.5)
            put(drums, OH, T.at(bar, 3.5), 0.12)
        if bar >= 4:
            for k in range(16):
                put(drums, H, T.at(bar, k / 4), (0.16 if k % 2 else 0.09) * (0.6 if breakdown else 1))
        if bar in (15, 23):
            for k in range(8):
                put(drums, snare(220, seed=k), T.at(bar, 2 + k / 4), 0.18 + 0.05 * k)
    put(drums, riser(2 * 4 * T.beat), T.at(30), 0.25)
    # sidechain pump on pads and bass (duck after every kick)
    pump = np.ones(T.buf.shape[0])
    beat_n = int(T.beat * SR); tt = t_(beat_n)
    duck = 1 - 0.45 * np.exp(-tt / 0.09)
    for bar in range(8, 32):
        if 28 <= bar < 30:
            continue
        for b in range(4):
            s = T.at(bar, b); e = min(s + beat_n, pump.shape[0]); pump[s:e] = duck[:e - s]
    mix = pads * pump[:, None] + bassb * pump[:, None] * 0.8 + drums
    arps_d = delay(arps, 0.75 * T.beat, fb=0.32, n=3)
    mix = np.vstack([mix, np.zeros((arps_d.shape[0] - mix.shape[0], 2))]) if arps_d.shape[0] > mix.shape[0] else mix
    mix[:arps_d.shape[0]] += arps_d[:mix.shape[0]]
    mix[:bells.shape[0]] += bells
    wet = reverb(mix[:T.buf.shape[0]], 2.2, 0.22, seed=11, tone=7000)
    T.buf = wet[:T.buf.shape[0]]
    return master(T.loop(), 1.05)


# ------------------------------------------------------------------ track 2
def static_hearts():
    T = Track(100, 28)
    Dm, Bb, F, C = 50, 46, 41, 48                     # roots (drop-D guitar range below)
    prog = [(Dm, (0, 3, 7)), (Bb, (0, 4, 7)), (F, (0, 4, 7)), (C, (0, 4, 7))]
    pianos, gtr, drums, bassb, fx, padb = (np.zeros_like(T.buf) for _ in range(6))
    def put(buf, x, s, g=1.0):
        e = min(s + x.shape[0], buf.shape[0]); buf[s:e] += x[:e - s] * g
    section = lambda b: "intro" if b < 4 else "verse" if b < 12 else "chorus" if b < 20 else "bridge" if b < 24 else "chorus"
    # piano motif (original): broken chord in 8ths, the top note walks down each bar
    tops = [77, 77, 76, 76]
    for bar in range(28):
        root, tri_ = prog[bar % 4]
        r = root + 12 if root < 48 else root
        ch = [r + 12 + i for i in tri_]
        line = [ch[0], ch[2], ch[1] + 12, ch[2], tops[bar % 4], ch[2], ch[1] + 12, ch[2]]
        vel = {"intro": 0.9, "verse": 0.75, "chorus": 0.6, "bridge": 0.95}[section(bar)]
        for k, m in enumerate(line):
            put(pianos, stereo(piano(m, T.beat / 2 * 0.95, vel * (1.1 if k == 0 else 0.85)), 0.1), T.at(bar, k / 2), 0.33)
    for bar in range(28):
        sec = section(bar)
        root, tri_ = prog[bar % 4]
        groot = root - 12 if root > 45 else root            # guitar register
        s = T.at(bar)
        if sec == "verse":
            # palm-muted chugs: 8ths with a push on the "and" of 4
            for k, beat in enumerate((0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 3.75)):
                put(gtr, guitar([groot], T.beat * 0.22, mute=True, seed=bar * 9 + k, gain=7), T.at(bar, beat), 0.45)
        elif sec == "chorus":
            # big open chords: hit on 1, hold, re-hit on the "and" of 2, chug into the next bar
            put(gtr, guitar([groot], T.beat * 1.4, seed=bar), T.at(bar, 0), 0.62)
            put(gtr, guitar([groot], T.beat * 1.9, seed=bar + 50), T.at(bar, 1.5), 0.62)
            for beat in (3.5, 3.75):
                put(gtr, guitar([groot], T.beat * 0.2, mute=True, seed=bar + 99), T.at(bar, beat), 0.5)
            put(padb, pad([root + 12 + i for i in tri_], 4 * T.beat, seed=bar, cutoff=1800), s, 0.35)
        if sec in ("verse", "chorus"):
            for k in range(8):
                put(bassb, stereo(bass(root - 12 if root > 45 else root, T.beat / 2 * 0.9, 0.6)), T.at(bar, k / 2), 0.8)
        # drums
        K, S, H = kick(1.0, 0.3), snare(185, 0.28, 3500), hat(0.04)
        if sec in ("verse", "chorus", "bridge"):
            kicks = (0, 1.5, 2.5) if sec != "chorus" else (0, 0.75, 1.5, 2, 2.5, 3.25)
            for b in kicks:
                put(drums, K, T.at(bar, b), 0.95 if sec != "bridge" else 0.5)
            for b in (1, 3):
                put(drums, S, T.at(bar, b), 0.65 if sec != "bridge" else 0.35)
            for k in range(8 if sec != "chorus" else 16):
                put(drums, H, T.at(bar, k / (2 if sec != "chorus" else 4)), 0.12)
        if sec == "chorus" and bar % 4 == 0:
            put(drums, crash(seed=bar), s, 0.45)
        if sec == "bridge" and bar % 2 == 1:
            put(fx, scratch(seed=bar), T.at(bar, 2.5), 0.35)
        if bar in (11, 19, 27):
            for k in range(8):
                put(drums, snare(200, 0.2, 3800, seed=40 + k), T.at(bar, 2 + k / 4), 0.25 + 0.06 * k)
    put(fx, riser(4 * T.beat), T.at(11), 0.2)
    # bridge: the beat sounds like it's in the next room (low-passed)
    b0, b1 = T.at(20), T.at(24)
    drums[b0:b1] = lowpass(drums[b0:b1], 900)
    mix = gtr + drums + bassb * 0.9 + fx + padb
    mix = reverb(mix, 1.2, 0.12, seed=21, tone=5000)[:T.buf.shape[0]]
    mix += reverb(pianos, 2.0, 0.3, seed=22)[:T.buf.shape[0]]
    T.buf = mix
    return master(T.loop(), 1.25)


# ------------------------------------------------------------------ track 3
def rhodes(m, dur, vel=1.0):
    """Electric-piano tone: FM bell-ish attack, warm body, slow tremolo."""
    f = float(mtof(m)); n = int((dur + 1.2) * SR); t = t_(n)
    idx = 1.6 * vel * np.exp(-t / 0.35) + 0.25
    x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t)) * np.exp(-t / 2.2)
    x *= 1 + 0.12 * np.sin(2 * np.pi * 4.2 * t)
    rel = np.clip(1 - (t - dur) / 0.4, 0, 1)
    return x * np.where(t > dur, rel, 1) * vel


def felt_piano(m, dur, vel=1.0):
    """A soft, close piano (felt-damped: few overtones, quick fade of the top)."""
    return lowpass(piano(m, dur, vel), 2200 + 600 * vel)


def strum(notes, dur, down=True, seed=0):
    """Nylon/steel-ish guitar strum: plucked strings a few ms apart."""
    rng = np.random.default_rng(seed)
    n = int((dur + 1.5) * SR); out = np.zeros(n)
    order = notes if down else notes[::-1]
    for i, m in enumerate(order):
        f = float(mtof(m)) * 2 ** (rng.normal(0, 0.03) / 12)
        s = int(i * 0.012 * SR); k = n - s; t = t_(k)
        x = np.zeros(k)
        for h, a in enumerate((1.0, 0.5, 0.33, 0.22, 0.14, 0.09, 0.05), 1):
            x += a * np.sin(2 * np.pi * f * h * t) * np.exp(-t * (1.2 + 1.6 * h))
        x += rng.standard_normal(k) * np.exp(-t / 0.004) * 0.15
        out[s:] += x * (0.9 if i == 0 else 0.7)
    t = t_(n); out *= np.where(t > dur, np.clip(1 - (t - dur) / 0.3, 0, 1), 1)
    return lowpass(out, 3500) / len(notes)


def choir(notes, dur, seed=0):
    """'Aah' voices: buzzy saws shaped by vowel formants, gentle vibrato, slow swell."""
    n = int((dur + 1.5) * SR); t = t_(n)
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for m in notes:
        for det in (-0.08, 0.07):
            f = float(mtof(m)) * 2 ** (det / 12)
            vib = 1 + 0.006 * np.sin(2 * np.pi * (5.1 + rng.random()) * t + rng.random() * 6)
            x += 2 * ((np.cumsum(f * vib) / SR + rng.random()) % 1) - 1
    v = sum(bandpass(x, fc, q) * g for fc, q, g in ((800, 3, 1.0), (1150, 4, 0.6), (2900, 5, 0.25)))
    e = env(n, a=1.2, d=0.5, s=0.9, r=1.4, hold=dur)
    return v * e / (2 * len(notes))


def vinyl(seconds, seed=9):
    n = int(seconds * SR); rng = np.random.default_rng(seed)
    hiss = lowpass(rng.standard_normal(n), 6000) * 0.012
    pops = np.zeros(n); idx = rng.integers(0, n, int(seconds * 7))
    pops[idx] = rng.uniform(-0.5, 0.5, idx.size)
    pops = lowpass(pops, 3000)
    return np.column_stack([hiss + pops, hiss * 0.9 + np.roll(pops, 13)])


def tape(x, depth=0.0016, rate=0.55):
    """Wow and flutter: the playback speed wobbles a hair, like old tape."""
    n = x.shape[0]; t = t_(n)
    drift = depth * SR * (np.sin(2 * np.pi * rate * t) + 0.35 * np.sin(2 * np.pi * 6.3 * t) * 0.05)
    src = np.clip(np.arange(n) + drift, 0, n - 1)
    return np.column_stack([np.interp(src, np.arange(n), x[:, c]) for c in range(2)])


def ember_hours():
    T = Track(76, 28, tail=6.0)
    Am, F, C, G, Em, Dm = 57, 53, 48, 55, 52, 50
    tri = {"m": (0, 3, 7), "M": (0, 4, 7)}
    loop_a = [(Am, "m"), (F, "M"), (C, "M"), (G, "M")]          # rolling piano section
    lift = [(F, "M"), (G, "M"), (Am, "m"), (Em, "m")]            # the swell
    quiet = [(C, "M"), (G, "M"), (Am, "m"), (F, "M")]            # guitar and piano
    def chord_at(bar):
        if 12 <= bar < 18: return lift[bar % 4]
        if 18 <= bar < 24: return quiet[bar % 4]
        return loop_a[bar % 4]
    sec = lambda b: "intro" if b < 4 else "roll" if b < 12 else "swell" if b < 18 else "quiet" if b < 24 else "home"
    keys, pno, mel, gtr, pads, vox, drums, bassb = (np.zeros_like(T.buf) for _ in range(8))
    def put(buf, x, s, g=1.0):
        e = min(s + x.shape[0], buf.shape[0]); buf[s:e] += x[:e - s] * g
    swing = lambda k8: (k8 // 2) + (0.0 if k8 % 2 == 0 else 0.58)        # swung 8ths, in beats
    for bar in range(28):
        root, q = chord_at(bar); s = T.at(bar); S = sec(bar)
        r = root if root >= 52 else root + 12
        ch = [r + i for i in tri[q]]
        # electric piano: soft chords on 1 and the "and" of 2
        if S in ("intro", "roll", "home", "swell"):
            for beat, v in ((0, 0.8), (1.58, 0.5)):
                for m in ch + [ch[0] + 12]:
                    put(keys, stereo(rhodes(m, T.beat * 1.4, v), -0.25), T.at(bar, beat), 0.16 if S != "swell" else 0.1)
        # the rolling piano: broken chord in straight 8ths, low to high and back
        if S in ("roll", "home") or (S == "swell" and bar >= 16):
            low = ch[0] - 12
            line = [low, ch[0], ch[2], ch[1] + 12, ch[2] + 12, ch[1] + 12, ch[2], ch[0]]
            for k, m in enumerate(line):
                put(pno, stereo(felt_piano(m, T.beat / 2 * 1.6, 0.8 if k % 4 == 0 else 0.6), 0.15), T.at(bar, k / 2), 0.3)
        # guitar strums in the quiet section: down on 1 and 3, up on the "and" of 2 and 4
        if S == "quiet":
            g_notes = [ch[0] - 12, ch[2] - 12, ch[0], ch[1], ch[2], ch[0] + 12]
            for beat, down in ((0, True), (1.5, False), (2, True), (3.5, False)):
                put(gtr, stereo(strum(g_notes, T.beat * (1.4 if down else 0.5), down, seed=bar * 7 + int(beat * 2)), 0.3),
                    T.at(bar, beat), 0.55 if down else 0.32)
        # pads and voices for the swell, carried softly into the quiet section
        if S == "swell":
            put(pads, pad([r - 12 + i for i in tri[q]] + [r], 4 * T.beat, seed=bar, cutoff=1400 + 260 * (bar - 12)), s, 0.5)
            put(vox, stereo(choir([m + 12 for m in ch], 4 * T.beat, seed=bar)), s, 0.55 + 0.08 * (bar - 12))
        if S == "quiet":
            put(pads, pad([r - 12 + i for i in tri[q]], 4 * T.beat, seed=bar + 40, cutoff=1100), s, 0.25)
        # bass: round sub on the root
        if S in ("roll", "home") or (S == "swell" and bar >= 14):
            for beat, d in ((0, 1.4), (1.58, 0.4), (2, 1.4), (3.58, 0.3)):
                put(bassb, stereo(bass(root - 12 if root > 50 else root, T.beat * d, 0.2)), T.at(bar, beat), 0.75)
        # drums: dusty, swung, laid back
        K, Sn, H = kick(0.5, 0.36), snare(170, 0.3, 2400, seed=bar % 3), hat(0.045)
        if S in ("roll", "home") or (S == "swell" and bar >= 14):
            half = S == "swell"
            for b in ((0,) if half else (0, 1.58, 2.5)):
                put(drums, K, T.at(bar, b), 0.75)
            for b in ((2,) if half else (1, 3)):
                put(drums, lowpass(Sn, 3000), T.at(bar, b + 0.03), 0.5)
            for k8 in range(8):
                put(drums, H, T.at(bar, swing(k8)), 0.09 if k8 % 2 == 0 else 0.06)
        if S == "intro":
            put(drums, H, T.at(bar, 3.58), 0.05)
    # an original melody on felt piano: in the rolling section and again at home
    phrase = [(0, 1.5, 76), (1.5, 0.5, 74), (2, 1, 72), (3, 1, 69), (4, 2, 71), (6, 1, 72), (7, 1, 74),
              (8, 1.5, 76), (9.5, 0.5, 79), (10, 1, 76), (11, 1, 74), (12, 3, 72), (15, 1, 71)]
    for b0 in (8, 24):
        for beat, dur, m in phrase:
            put(mel, stereo(felt_piano(m, dur * T.beat, 0.75), -0.1), T.at(b0, beat), 0.32)
    q_phrase = [(0, 2, 72), (2, 1, 71), (3, 1, 67), (4, 3, 69), (8, 2, 72), (10, 1, 74), (11, 1, 76), (12, 4, 74),
                (16, 2, 72), (18, 2, 71), (20, 4, 69)]
    for beat, dur, m in q_phrase:
        put(mel, stereo(felt_piano(m, dur * T.beat, 0.6), 0.1), T.at(18, beat), 0.3)
    # a reversed-cymbal swell into the quiet section and into home
    for b in (17, 23):
        cr = crash(seed=b)[::-1][-int(2 * T.beat * SR):]
        put(drums, lowpass(cr, 5000), T.at(b, 2), 0.35)
    mix = keys + pno + mel * 1.1 + gtr + pads + vox + bassb * 0.9 + drums
    mix = reverb(mix, 2.4, 0.26, seed=31, tone=4500)[:T.buf.shape[0]]
    mix = lowpass(mix, 5200, 1)                      # the warm, dusty top end
    mix = mix / np.abs(mix).max()
    mix = np.tanh(mix * 1.3) / np.tanh(1.3)          # a little tape saturation
    T.buf = tape(mix)
    out = T.loop()
    out = out + vinyl(out.shape[0] / SR) * 0.6       # crackle sits well under the music
    out = out - out.mean(axis=0)
    return out / np.abs(out).max() * 0.85


# ------------------------------------------------------------------ track 4
def bright_piano(m, dur, vel=1.0):
    """A lively upright: the plain piano with a touch more sparkle on top."""
    x = piano(m, dur, vel)
    f = float(mtof(m)); n = x.shape[0]; t = t_(n)
    x += 0.12 * vel * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t * 9)
    return x


def snap(seed=12):
    n = int(0.12 * SR); t = t_(n)
    x = bandpass(np.random.default_rng(seed).standard_normal(n), 2600, 1.5) * np.exp(-t / 0.012)
    return stereo(x, 0.35)


def brush(seed=13, length=0.22):
    n = int(length * SR); t = t_(n)
    x = bandpass(np.random.default_rng(seed).standard_normal(n), 3200, 0.5)
    return stereo(x * np.exp(-t / 0.06) * (1 - np.exp(-t / 0.004)), -0.1)


def pocket_sunshine():
    T = Track(132, 32, tail=3.0)
    # chords as (bass root, chord tones in the middle register)
    C, A7, Dm, G7, E7, F, Fm, D7, C7, Am = (
        (36, (60, 64, 67)), (33, (61, 64, 67)), (38, (62, 65, 69)), (31, (59, 62, 65)),
        (40, (59, 62, 64)), (41, (60, 65, 69)), (41, (60, 65, 68)), (38, (60, 62, 66)),
        (36, (58, 60, 64)), (33, (60, 64, 69)))
    A_prog = [C, A7, Dm, G7, C, E7, F, G7]
    B_prog = [F, Fm, C, A7, D7, G7, C, G7]
    prog = A_prog + A_prog + B_prog + A_prog
    lh, rh, glk, drums, bassb = (np.zeros_like(T.buf) for _ in range(5))
    def put(buf, x, s, g=1.0):
        e = min(s + x.shape[0], buf.shape[0]); buf[s:e] += x[:e - s] * g
    # left hand: stride - bass note on 1 and 3 (octave below on 3), chord on 2 and 4
    for bar, (root, tones) in enumerate(prog):
        for beat, low in ((0, root), (2, root - 12 if root >= 36 else root + 7)):
            put(lh, stereo(bright_piano(low, T.beat * 0.9, 0.95), -0.35), T.at(bar, beat), 0.42)
        for beat in (1, 3):
            for m in tones:
                put(lh, stereo(bright_piano(m, T.beat * 0.45, 0.7), -0.2), T.at(bar, beat), 0.2)
        if bar % 8 == 7:                               # a little walk-up into the next phrase
            for k, m in enumerate((root + 2, root + 4, root + 5)):
                put(lh, stereo(bright_piano(m, T.beat * 0.3, 0.8), -0.35), T.at(bar, 3 + k / 3), 0.3)
    # right hand: an original skipping tune (beat, length, note), two bars per line
    tune_a = [
        [(0, .5, 76), (.5, .5, 79), (1, 1, 84), (2, .5, 83), (2.5, .5, 81), (3, 1, 79),
         (4, .75, 81), (4.75, .25, 82), (5, .5, 81), (5.5, .5, 79), (6, 1.5, 77), (7.5, .5, 76)],
        [(0, .5, 74), (.5, .5, 77), (1, 1, 81), (2, .5, 79), (2.5, .5, 77), (3, 1, 74),
         (4, .5, 79), (4.5, .5, 81), (5, .5, 79), (5.5, .5, 77), (6, 1, 76), (7, .5, 74), (7.5, .5, 71)],
        [(0, .5, 76), (.5, .5, 79), (1, 1, 84), (2, .5, 86), (2.5, .5, 84), (3, 1, 80),
         (4, .5, 81), (4.5, .5, 84), (5, .5, 81), (5.5, .5, 77), (6, 1, 79), (7, .25, 77), (7.25, .25, 76), (7.5, .5, 74)],
        [(0, .5, 72), (.5, .5, 76), (1, .5, 79), (1.5, .5, 84), (2, 1, 83), (3, 1, 79),
         (4, .5, 77), (4.5, .5, 76), (5, .5, 74), (5.5, .5, 71), (6, 1.5, 72), (7.5, .5, 79)],
    ]
    tune_b = [
        [(0, 1, 81), (1, .5, 84), (1.5, .5, 81), (2, 1, 77), (3, 1, 81),
         (4, 1, 80), (5, .5, 84), (5.5, .5, 80), (6, 1, 77), (7, 1, 80)],
        [(0, .5, 79), (.5, .5, 84), (1, .5, 88), (1.5, .5, 84), (2, 1, 79), (3, .5, 81), (3.5, .5, 85),
         (4, .5, 84), (4.5, .5, 81), (5, .5, 78), (5.5, .5, 81), (6, 1, 84), (7, 1, 83)],
        [(0, .5, 79), (.5, .25, 81), (.75, .25, 79), (1, .5, 77), (1.5, .5, 76), (2, .5, 74), (2.5, .5, 72),
         (3, 1, 76), (4, .5, 79), (4.5, .5, 77), (5, .5, 74), (5.5, .5, 71), (6, 1, 74), (7, 1, 79)],
        [(0, .5, 84), (.5, .5, 83), (1, .5, 81), (1.5, .5, 79), (2, .5, 77), (2.5, .5, 76), (3, .5, 74), (3.5, .5, 71),
         (4, 1.5, 72), (5.5, .5, 76), (6, .5, 79), (6.5, .5, 84), (7, 1, 79)],
    ]
    lines = tune_a + tune_a + tune_b + tune_a
    for i, line in enumerate(lines):
        b0 = i * 2
        last = i >= 12
        for beat, dur, m in line:
            vel = 0.95 if beat % 1 == 0 else 0.8
            put(rh, stereo(bright_piano(m, dur * T.beat * 0.95, vel), 0.3), T.at(b0, beat), 0.34)
            if 8 <= i < 12 and beat % 1 == 0:          # B section: octave below for weight
                put(rh, stereo(bright_piano(m - 12, dur * T.beat * 0.9, 0.6), 0.25), T.at(b0, beat), 0.16)
            if last:                                   # last A: a glockenspiel doubles the tune
                put(glk, stereo(bell(m + 12, dur * T.beat), 0.4), T.at(b0, beat), 0.09)
    # a glissando up at the very end, leading back to the top of the loop
    for k, m in enumerate(range(72, 97, 2)):
        put(rh, stereo(bright_piano(m, 0.08, 0.6), 0.3), T.at(31, 2 + k * (2 / 13)), 0.18)
    # rhythm: brushes on 2 and 4, a shuffling shaker, snaps in the B section, soft kick on 1 and 3
    sh, K = hat(0.04, seed=14), kick(0.4, 0.25)
    for bar in range(32):
        if bar >= 4 or bar in (2, 3):
            for b in (1, 3):
                put(drums, brush(seed=bar * 2 + b), T.at(bar, b), 0.32)
        if bar >= 8:
            for b in (0, 2):
                put(drums, K, T.at(bar, b), 0.45)
            for k in range(8):
                put(drums, sh, T.at(bar, k // 2 + (0.0 if k % 2 == 0 else 0.62)), 0.1 if k % 2 == 0 else 0.07)
        if 16 <= bar < 24:
            for b in (1, 3):
                put(drums, snap(seed=bar + b), T.at(bar, b), 0.5)
        if bar in (7, 15, 23, 31):
            put(drums, hat(open_=True, seed=bar), T.at(bar, 3.5), 0.12)
    # walking pizzicato bass under the second A and the B section
    for bar, (root, tones) in enumerate(prog):
        if 8 <= bar < 24:
            r = root + 12 if root < 36 else root
            walk = [r, r + 4, r + 7, r + 9 if bar % 2 == 0 else r + 5]
            for k, m in enumerate(walk):
                x = bass(m - 12, T.beat * 0.6, 0.25) * np.exp(-t_(int((T.beat * 0.6 + 0.05) * SR)) / 0.25)
                put(bassb, stereo(x), T.at(bar, k), 0.5)
    mix = lh + rh + glk + drums * 0.9 + bassb
    mix = reverb(mix, 1.5, 0.18, seed=41, tone=7000)[:T.buf.shape[0]]
    T.buf = mix
    out = T.loop()
    out = out - out.mean(axis=0)
    return np.tanh(out / np.abs(out).max() * 1.2) / np.tanh(1.2) * 0.86


# ------------------------------------------------------------------ track 5
PENTA_D = [62, 64, 66, 69, 71]                     # D E F# A B


def cipher(word, octave=0):
    """Letters -> notes: A=1 ... Z=26, counted round the D major pentatonic.
    REN -> F# B A.  LOVE -> E B E B.  HOME -> F# B F# B."""
    return [PENTA_D[(ord(c) - 65) % 5] + 12 * octave for c in word.upper() if c.isalpha()]


def lead(m, dur, vel=1.0, bright=3000):
    f = float(mtof(m)); n = int((dur + 0.3) * SR); t = t_(n)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.3, 0, 1)
    ph = np.cumsum(f * vib) / SR
    x = (2 * (ph % 1) - 1) + (2 * ((ph * 1.004 + 0.3) % 1) - 1)
    x = lowpass(x, bright) * env(n, 0.01, 0.15, 0.7, 0.2, hold=dur)
    return x * vel * 0.5


def cello(m, dur, vel=1.0):
    """A bowed low string: saw, slow bow swell, gentle vibrato."""
    f = float(mtof(m)); n = int((dur + 0.8) * SR); t = t_(n)
    vib = 1 + 0.005 * np.sin(2 * np.pi * 4.8 * t) * np.clip(t / 0.8, 0, 1)
    x = 2 * ((np.cumsum(f * vib) / SR) % 1) - 1
    x = lowpass(x, 1400, 2) * env(n, 0.5, 0.3, 0.85, 0.7, hold=dur)
    return x * vel


def ping(f=1760.0):
    n = int(1.2 * SR); t = t_(n)
    return stereo(np.sin(2 * np.pi * f * t) * np.exp(-t / 0.25) + 0.3 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.08))


def campfire(seconds, seed=51):
    n = int(seconds * SR); rng = np.random.default_rng(seed)
    roar = lowpass(rng.standard_normal(n), 500) * 0.05 * (1 + 0.4 * np.sin(2 * np.pi * 0.3 * t_(n)))
    pops = np.zeros(n); idx = rng.integers(0, n, int(seconds * 5))
    pops[idx] = rng.uniform(-1, 1, idx.size)
    pops = bandpass(pops, 2200, 0.6) * 0.9
    return np.column_stack([roar + pops, roar + np.roll(pops, 41)])


def crickets(seconds, seed=52):
    n = int(seconds * SR); t = t_(n); rng = np.random.default_rng(seed)
    gate = (np.sin(2 * np.pi * 28 * t) > 0.3) * (np.sin(2 * np.pi * 0.9 * t + rng.random()) > 0.2)
    x = np.sin(2 * np.pi * 4400 * t) * gate * 0.02
    return np.column_stack([x, np.roll(x, 900)])


def contours():
    T = Track(88, 64, tail=6.0)
    D, A, Bm, G, Em, Fsm = 50, 45, 47, 43, 52, 54
    maj, mnr = (0, 4, 7), (0, 3, 7)
    REN, LOVE, HOME = cipher("REN", 1), cipher("LOVE", 1), cipher("HOME", 1)   # F# B A / E B E B / F# B F# B
    chords = {}
    def at(bars, prog):
        for b, c in zip(bars, prog):
            chords[b] = c
    at(range(0, 4), [(D, maj)] * 4)
    at(range(4, 12), [(D, maj), (Bm, mnr), (G, maj), (A, maj), (D, maj), (Bm, mnr), (Em, mnr), (A, maj)])
    at(range(12, 24), [(D, maj), (A, maj), (Bm, mnr), (G, maj)] * 3)
    at(range(24, 32), [(Bm, (0, 2, 7)), (G, (0, 4, 11)), (Em, (0, 3, 10)), (Fsm, (0, 5, 7))] * 2)   # sus2, maj7, m7, sus4
    at(range(32, 40), [(G, maj), (D, maj), (A, maj), (Bm, mnr), (G, maj), (D, maj), (Em, mnr), (A, maj)])
    at(range(40, 52), [(G, maj), (D, maj), (Em, mnr), (D, maj), (G, maj), (A, maj), (Bm, mnr), (G, maj),
                       (Em, mnr), (A, maj), (G, maj), (D, maj)])                                  # ends G -> D: "amen"
    at(range(52, 64), [(D, maj), (A, maj), (Bm, mnr), (G, maj), (D, maj), (A, maj), (G, maj), (D, maj),
                       (D, maj), (G, maj), (D, maj), (D, maj)])
    part = lambda b: ("dot" if b < 4 else "contours" if b < 12 else "ride" if b < 24 else "friction" if b < 32
                      else "fire" if b < 40 else "overview" if b < 52 else "home")
    P, KEYS, LEAD, PAD, VOX, GTR, DR, BAS, FX = (np.zeros_like(T.buf) for _ in range(9))
    def put(buf, x, s, g=1.0):
        e = min(s + x.shape[0], buf.shape[0]); buf[s:e] += x[:e - s] * g
    def melody(buf, notes_beats, b0, inst, gain, pan=0.1):
        for beat, dur, m in notes_beats:
            put(buf, stereo(inst(m, dur * T.beat), pan), T.at(b0, beat), gain)
    # --- 1. a dot: the theme alone on piano, a ping like a GPS fix
    melody(P, [(0, 1, REN[0]), (1, 1, REN[1]), (2, 2, REN[2])], 0, lambda m, d: felt_piano(m, d, 0.8), 0.4)
    melody(P, [(0, 1, REN[0] + 12), (1, 1, REN[1] + 12), (2, 2, REN[2]), ], 2, lambda m, d: felt_piano(m, d, 0.6), 0.3)
    for b in (0, 2):
        put(FX, ping(), T.at(b, 3.5), 0.05)
    for bar in range(64):
        root, q = chords[bar]; s = T.at(bar); p = part(bar)
        r = root + 12 if root < 50 else root
        ch = [r + i for i in q]
        # pads: almost everywhere, colour per part
        if p in ("contours", "ride", "friction", "overview", "home"):
            cut = {"contours": 1200 + 120 * (bar - 4), "ride": 2400, "friction": 900, "overview": 2600, "home": 2200}[p]
            put(PAD, pad([m - 12 for m in ch] + [r], 4 * T.beat, seed=bar, cutoff=cut), s,
                {"contours": 0.35, "ride": 0.3, "friction": 0.5, "overview": 0.6, "home": 0.4}[p])
        # 2. contours: arpeggio layers stacking up like lines on a map, one more every two bars
        if p == "contours":
            layers = 1 + (bar - 4) // 2
            for L in range(layers):
                step = [1, 0.5, 0.25, 0.25][L]
                notes = [ch[0] + 12 * L, ch[1] + 12 * L, ch[2] + 12 * L, ch[0] + 12 * (L + 1)]
                k = 0; beat = 0.0
                while beat < 4:
                    put(KEYS, stereo(pluck(notes[k % 4], step * T.beat * 0.9, 0.6 + 0.2 * L), (-0.4, 0.4, -0.2, 0.2)[L]),
                        T.at(bar, beat), 0.16 / (1 + 0.3 * L)); k += 1; beat += step
            for k in range(16):                                           # a clock ticking: steady work
                put(DR, hat(0.02, seed=k), T.at(bar, k / 4), 0.05 if k % 4 else 0.08)
        # 3. the ride: driving, friends, windows down
        if p == "ride":
            K, S, H = kick(0.9, 0.3), snare(200, 0.25, 4200), hat(0.04)
            for b in (0, 1.5, 2, 3.5) if bar % 2 else (0, 2, 2.5):
                put(DR, K, T.at(bar, b), 0.8)
            for b in (1, 3):
                put(DR, S, T.at(bar, b), 0.55); put(DR, clap(seed=bar), T.at(bar, b), 0.25)
            for k in range(8):
                put(DR, H, T.at(bar, k / 2), 0.12)
            for k in range(8):
                put(BAS, stereo(bass(root - 12 if root > 45 else root, T.beat / 2 * 0.85, 0.5)), T.at(bar, k / 2), 0.7)
            for k, beat in enumerate((0, 0.75, 1.5, 2, 2.75, 3.5)):
                put(GTR, stereo(pluck(ch[k % 3] + 12, T.beat * 0.3, 1.2), 0.3 if k % 2 else -0.3), T.at(bar, beat), 0.2)
            if bar == 12:
                put(DR, crash(seed=12), s, 0.4)
        # 4. friction: suspended chords that don't settle, a low bowed note, a heartbeat
        if p == "friction":
            put(BAS, stereo(cello(root - 12 if root > 45 else root, 4 * T.beat * 0.98, 0.5), -0.1), s, 0.55)
            put(BAS, stereo(cello(ch[2], 4 * T.beat * 0.98, 0.3), 0.2), s, 0.3)
            for b in (0, 0.35):
                put(DR, kick(0.3, 0.3), T.at(bar, b), 0.5 if b == 0 else 0.3)
            frag = REN[:2] if bar % 2 == 0 else [REN[1], REN[1] - 1]       # the theme, but it won't finish
            melody(P, [(1, 1.5, frag[0]), (2.5, 1.5, frag[1])], bar, lambda m, d: felt_piano(m, d, 0.7), 0.3, -0.1)
        # 5. campfire: guitar, fire, crickets, the theme turned warm
        if p == "fire":
            g_notes = [ch[0] - 12, ch[2] - 12, ch[0], ch[1], ch[2]]
            for beat, down in ((0, True), (1.5, False), (2, True), (3, False), (3.5, False)):
                put(GTR, stereo(strum(g_notes, T.beat * (1.3 if down else 0.45), down, seed=bar * 5 + int(beat * 2)), -0.2),
                    T.at(bar, beat), 0.5 if down else 0.3)
        # 6. overview: wide and slow, voices, stars
        if p == "overview":
            put(VOX, stereo(choir([m + 12 for m in ch], 4 * T.beat, seed=bar)), s, 0.5 + 0.03 * (bar - 40))
            for k in range(8):
                star = ch[k % 3] + 24 + (12 if k % 4 == 3 else 0)
                put(KEYS, stereo(bell(star, 0.4), (-0.6, 0.6)[k % 2]), T.at(bar, k / 2 + 0.25), 0.04)
            put(BAS, stereo(cello(root - 12 if root > 45 else root, 4 * T.beat, 0.5)), s, 0.4)
            if bar >= 46:
                put(DR, kick(0.5, 0.5), s, 0.4)
                put(DR, kick(0.5, 0.5), T.at(bar, 2), 0.25)
        # 7. home: everything together, glad
        if p == "home":
            quiet = bar >= 60
            if not quiet:
                K, S, H = kick(0.8, 0.3), snare(190, 0.26, 3800), hat(0.04)
                for b in (0, 2, 2.5):
                    put(DR, K, T.at(bar, b), 0.75)
                for b in (1, 3):
                    put(DR, S, T.at(bar, b), 0.45); put(DR, brush(seed=bar + b), T.at(bar, b), 0.25)
                for k in range(8):
                    put(DR, H, T.at(bar, k // 2 + (0 if k % 2 == 0 else 0.55)), 0.1)
                for k in range(4):
                    put(BAS, stereo(bass(root - 12 if root > 45 else root, T.beat * 0.9, 0.35)), T.at(bar, k), 0.7)
                # piano bouncing between bass note and chord
                put(P, stereo(bright_piano(root - 12 if root > 45 else root, T.beat * 0.9, 0.9), -0.3), T.at(bar, 0), 0.32)
                put(P, stereo(bright_piano(root - 12 if root > 45 else root + 12, T.beat * 0.9, 0.8), -0.3), T.at(bar, 2), 0.28)
                for b in (1, 3):
                    for m in ch:
                        put(P, stereo(bright_piano(m, T.beat * 0.45, 0.65), -0.15), T.at(bar, b), 0.15)
            if bar == 52:
                put(DR, crash(seed=52), s, 0.45)
    # the theme through the parts
    theme_ride = [(0, .5, REN[0]), (.5, .5, REN[1]), (1, 1, REN[2]), (2, .5, LOVE[0]), (2.5, .5, LOVE[1]),
                  (3, .5, LOVE[2]), (3.5, .5, LOVE[3]), (4, 1.5, REN[0]), (5.5, .5, REN[1]), (6, 2, REN[2])]
    for b0 in (14, 18, 22):
        melody(LEAD, theme_ride, b0, lambda m, d: lead(m + 12, d, 0.8), 0.2, 0.15)
    theme_fire = [(0, 2, REN[0]), (2, 1, REN[1]), (3, 1, REN[2]), (4, 3, LOVE[0] + 2), (8, 1, LOVE[1]), (9, 1, LOVE[2] + 2),
                  (10, 2, LOVE[3]), (12, 4, REN[2])]
    for b0 in (32, 36):
        melody(P, theme_fire, b0, lambda m, d: felt_piano(m, d, 0.65), 0.34, 0.1)
    theme_big = [(0, 4, REN[0] + 12), (4, 4, REN[1] + 12), (8, 8, REN[2] + 12)]       # the theme, slowed right down
    for b0 in (40, 44):
        melody(VOX, theme_big, b0, lambda m, d: bell(m, d), 0.12, 0.0)
    melody(LEAD, [(0, 4, LOVE[0] + 12), (4, 4, LOVE[1] + 12), (8, 4, LOVE[2] + 12), (12, 4, LOVE[3] + 12)], 48,
           lambda m, d: lead(m, d, 0.6, 2200), 0.16, -0.1)
    theme_home = [(0, .5, REN[0]), (.5, .5, REN[1]), (1, 1, REN[2]), (2, .5, HOME[0]), (2.5, .5, HOME[1]), (3, 1, HOME[2]),
                  (4, .5, LOVE[0]), (4.5, .5, LOVE[1]), (5, .5, LOVE[2]), (5.5, .5, LOVE[3]), (6, 2, 74)]
    for b0 in (54, 56):
        melody(P, theme_home, b0, lambda m, d: bright_piano(m + 12, d, 0.9), 0.33, 0.25)
        melody(KEYS, theme_home, b0, lambda m, d: bell(m + 24, d), 0.06, 0.4)
    melody(P, [(0, 1, REN[0]), (1, 1, REN[1]), (2, 1, REN[2]), (3, 1, 62)], 60, lambda m, d: felt_piano(m, d, 0.7), 0.36)
    melody(P, [(0, 2, REN[0] + 12), (2, 2, REN[2])], 62, lambda m, d: felt_piano(m, d, 0.55), 0.3)
    # ambience: the fire and crickets under part 5, a ping at the very end
    fire_s, fire_e = T.at(31, 2), T.at(40, 2)
    amb = campfire((fire_e - fire_s) / SR) * 0.5 + crickets((fire_e - fire_s) / SR)
    fade = np.minimum(1, np.minimum(np.arange(amb.shape[0]), amb.shape[0] - np.arange(amb.shape[0])) / SR / 2.0)
    put(FX, amb * fade[:, None], fire_s)
    put(FX, ping(), T.at(63, 3.5), 0.05)
    # mix: each part gets its own space
    mix = P + KEYS * 1.0 + LEAD + PAD + VOX + GTR + DR * 0.9 + BAS * 0.85 + FX
    wet = reverb(mix, 2.6, 0.24, seed=61, tone=6500)[:T.buf.shape[0]]
    T.buf = wet
    out = T.loop()
    out = out - out.mean(axis=0)
    out = out / np.abs(out).max()
    return np.tanh(out * 1.6) / np.tanh(1.6) * 0.86


RENDER = {"lanterns": paper_lanterns, "static": static_hearts, "ember": ember_hours, "sunshine": pocket_sunshine,
          "contours": contours}


# ------------------------------------------------------------------ effects
def _blip(freqs, step=0.06, decay=0.12, wave="tri", gain=0.5, pan=0.0):
    n_total = int((step * len(freqs) + decay * 4) * SR)
    out = np.zeros(n_total)
    for i, f in enumerate(freqs):
        n = int(decay * 4 * SR); t = t_(n)
        w = tri(f, n) if wave == "tri" else sine(f, n)
        w += 0.3 * sine(2 * f, n)
        s = int(i * step * SR)
        out[s:s + n] += w * np.exp(-t / decay)
    return stereo(out * gain, pan)


def effects():
    """Every short sound the app uses, as stereo float arrays."""
    pent = [72, 74, 76, 79, 81, 84, 86, 88, 91, 93, 96]
    fx = {}
    for i in range(len(pent) - 1):                       # keep: pitch climbs with the combo
        fx[f"keep{i}"] = _blip([float(mtof(pent[i])), float(mtof(pent[i + 1]))], 0.045, 0.09, gain=0.42)
    n = int(0.35 * SR); t = t_(n)
    drop = np.sin(2 * np.pi * np.cumsum(220 * np.exp(-t / 0.12) + 70) / SR) * np.exp(-t / 0.1)
    fx["drop"] = stereo(drop * 0.5)
    fx["combo"] = _blip([float(mtof(m)) for m in (84, 88, 91, 96, 100)], 0.05, 0.12, gain=0.38)
    fx["badge"] = _blip([float(mtof(m)) for m in (72, 76, 79, 84)], 0.11, 0.3, wave="sine", gain=0.5)
    # look switch: a short glitch (bit-crushed noise sweep)
    n = int(0.28 * SR); t = t_(n)
    g = np.sign(np.sin(2 * np.pi * np.cumsum(1800 * np.exp(-t / 0.08) + 200) / SR))
    g = np.repeat(g[::12], 12)[:n] * np.exp(-t / 0.08)
    fx["glitch"] = np.column_stack([g, np.roll(g, 90)]) * 0.18
    # sonar ping when look-alikes are found
    n = int(0.9 * SR); t = t_(n)
    ping = sine(1318.5, n) * np.exp(-t / 0.18) + 0.4 * sine(1975.5, n) * np.exp(-t / 0.08)
    fx["found"] = delay(stereo(ping * 0.32), 0.16, 0.4, 3)
    fx["tick"] = _blip([2637.0], 0.0, 0.015, wave="sine", gain=0.15)
    fx["thinking"] = _blip([float(mtof(m)) for m in (84, 91)], 0.07, 0.05, wave="sine", gain=0.12)
    return {k: v.astype(np.float32) for k, v in fx.items()}


# ------------------------------------------------------------------ cache
def music_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "CHAMBER", "music")
    os.makedirs(d, exist_ok=True)
    return d


def write_wav(path, x):
    import wave
    a = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(a.tobytes())


def read_wav(path):
    import wave
    with wave.open(path, "rb") as w:
        a = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, w.getnchannels())
    return (a.astype(np.float32) / 32767)


def track(key):
    """The track as a stereo float32 array; rendered on first use, then cached."""
    path = os.path.join(music_dir(), f"{key}-v{VERSION}.wav")
    if os.path.exists(path):
        try:
            return read_wav(path)
        except Exception:
            pass
    x = RENDER[key]().astype(np.float32)
    try:
        write_wav(path, x)
    except Exception:
        pass
    return x
