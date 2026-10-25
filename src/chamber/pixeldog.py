"""A progress bar with a pixel-art dog that runs along it. Pure tkinter.

The dog trots toward the current progress, leaving paw prints on the path.
A bone waits at the finish line; when the run ends the dog grabs it and hops
(with hearts if every sheet came out clean). Idle = standing, tail wagging.
"""
from __future__ import annotations
import tkinter as tk

S = 4                      # one art pixel = 4x4 screen pixels

PALETTE = {
    "b": "#c07a3a",        # body (warm brown)
    "d": "#6b3f1d",        # dark brown (ears, paws, tail)
    "k": "#1f1a17",        # eye / nose
    "w": "#f4e6cf",        # cream belly / muzzle
    "r": "#d93b3b",        # collar
    "t": "#f08aa0",        # tongue
    "o": "#8a7a64",        # bone outline
    "c": "#fbf6ec",        # bone fill
    "h": "#e8455a",        # heart
}

# body rows 0-8, facing right; tail lives in columns 0-2 (drawn per frame)
_BODY = [
    "...........dd.....",
    "..........dbbd....",
    ".........dbbbbbb..",
    ".........bbkbbbbbk",
    ".........bbbbbwwww",
    ".........rrbbbwt..",
    "...bbbbbbrrbbb....",
    "...bbbbbbbbbbb....",
    "...bwwwwwwwwbb....",
]
_TAIL_UP = {3: "d..", 4: ".d.", 5: "..d"}
_TAIL_DOWN = {5: "d..", 6: ".dd"}
_LEGS = {
    "stretch": ["..bb.......bb.....",
                ".bb.........bb....",
                "dd...........dd..."],
    "tuck":    ["...bb.....bb......",
                "....bb...bb.......",
                "....dd...dd......."],
    "stand":   ["...b.b....b.b.....",
                "...b.b....b.b.....",
                "...d.d....d.d....."],
}
BONE = [".oo....oo.",
        "occoooocco",
        ".occcccco.",
        "occoooocco",
        ".oo....oo."]
HEART = [".hh.hh.",
         "hhhhhhh",
         ".hhhhh.",
         "..hhh..",
         "...h..."]


def dog_frame(legs="stand", tail_up=True):
    """Return the dog as a list of 12 strings (18 wide)."""
    rows = [list(r) for r in _BODY] + [list(r) for r in _LEGS[legs]]
    for r, s in (_TAIL_UP if tail_up else _TAIL_DOWN).items():
        for c, ch in enumerate(s):
            if ch != ".":
                rows[r][c] = ch
    return ["".join(r) for r in rows]


# run cycle: stretch, stand, tuck, stand (tail bounces along)
RUN_CYCLE = [("stretch", True), ("stand", False), ("tuck", True), ("stand", False)]
DOG_W, DOG_H = 18 * S, 12 * S


class DogProgress(tk.Canvas):
    HEIGHT = 76

    def __init__(self, master, **kw):
        bg = kw.pop("bg", None) or master.winfo_toplevel().cget("bg")
        super().__init__(master, height=self.HEIGHT, bg=bg, highlightthickness=0, **kw)
        self.total, self.done = 1, 0
        self.x = 8.0                        # dog's current left edge (eased)
        self.tick = 0
        self.state = "idle"                 # idle | running | finished
        self.hop = 0                        # remaining hop frames on finish
        self.hearts = []                    # [x, y, life]
        self.clean = False
        self.bind("<Configure>", lambda e: self._draw())
        self.after(90, self._loop)

    # ---------- public API ----------
    def reset(self):
        self.total, self.done, self.x = 1, 0, float(self._track()[0])
        self.state, self.hop, self.hearts = "idle", 0, []
        self._draw()

    def start(self, total):
        self.reset(); self.total = max(1, int(total)); self.state = "running"

    def set_progress(self, done, total=None):
        if total:
            self.total = max(1, int(total))
        self.done = max(0, min(int(done), self.total))

    def finish(self, clean=True):
        self.done = self.total; self.state = "finished"
        self.clean = clean; self.hop = 24
        if clean:
            self.hearts = [[0, 0, 0]]       # spawned near the dog in _loop

    # ---------- geometry ----------
    def _track(self):
        w = max(self.winfo_width(), 200)
        return 8, w - 8, self.HEIGHT - 12           # x0, x1, ground y

    def _target_x(self):
        x0, x1, _ = self._track()
        if self.state == "finished":
            return x1 - DOG_W - 4                   # trot up to where the bone was
        span =(x1 - len(BONE[0]) * S - 6) - x0 - DOG_W
        return x0 + span * (self.done / self.total)

    # ---------- animation ----------
    def _loop(self):
        try:
            self.tick += 1
            tx = self._target_x()
            self.x += (tx - self.x) * 0.18
            if abs(tx - self.x) < 0.5:
                self.x = tx
            if self.hop:
                self.hop -= 1
            if self.state == "finished" and self.clean and self.tick % 6 == 0 and self.hop:
                self.hearts.append([self.x + DOG_W - 10, self.HEIGHT - 12 - DOG_H, 0])
            self.hearts = [[hx, hy - 2, life + 1] for hx, hy, life in self.hearts
                           if life < 14 and hy > 0]
            self._draw()
            self.after(90, self._loop)
        except tk.TclError:
            pass                                    # window closed

    def _px(self, grid, x, y, scale=S):
        for r, row in enumerate(grid):
            for c, ch in enumerate(row):
                if ch != ".":
                    self.create_rectangle(x + c * scale, y + r * scale,
                                          x + (c + 1) * scale, y + (r + 1) * scale,
                                          fill=PALETTE[ch], outline="")

    def _draw(self):
        self.delete("all")
        x0, x1, gy = self._track()
        # track: grey dashes ahead, green path behind with paw prints
        for x in range(x0, x1, 6):
            self.create_rectangle(x, gy, x + 3, gy + 3, fill="#c9c9c9", outline="")
        walked = x1 if self.state == "finished" else int(self.x + DOG_W * 0.4)
        if self.state != "idle" and walked > x0 + 2:
            self.create_rectangle(x0, gy - 1, walked, gy + 5, fill="#6aa84f", outline="")
            self.create_rectangle(x0, gy + 5, walked, gy + 8, fill="#4e8a37", outline="")
            for i, px in enumerate(range(x0 + 8, walked - 10, 18)):
                oy = 0 if i % 2 else 2                     # paw prints on the path
                for dx, dy in ((0, 0), (4, 0), (2, 2)):
                    self.create_rectangle(px + dx, gy + oy + dy, px + dx + 2,
                                          gy + oy + dy + 2, fill="#9fd07f", outline="")
        # bone at the finish (in the mouth once finished)
        bx = x1 - len(BONE[0]) * S
        if self.state != "finished":
            self._px(BONE, bx, gy - len(BONE) * S - 2)
        # the dog
        moving = self.state == "running" and (self.done < self.total
                                              or abs(self._target_x() - self.x) > 0.5)
        if moving:
            legs, tail = RUN_CYCLE[self.tick % 4]
            bob = -S if legs == "tuck" else 0
        else:
            legs, tail = "stand", (self.tick // 3) % 2 == 0     # happy tail wag
            bob = 0
        if self.hop:
            legs = "tuck"
            bob = -[0, 3, 6, 8, 9, 8, 6, 3][self.hop % 8]
        dy = gy - DOG_H + bob
        self._px(dog_frame(legs, tail), self.x, dy)
        if self.state == "finished":
            self._px(BONE, self.x + DOG_W - 12, dy + 4 * S, scale=2)
        for hx, hy, _life in self.hearts:
            self._px(HEART, hx, hy, scale=2)
        # percentage label
        pct = int(round(100 * self.done / self.total)) if self.state != "idle" else 0
        if self.state != "idle":
            self.create_text(x1, 4, text=f"{pct}%", anchor="ne", fill="#555",
                             font=("Segoe UI", 9, "bold"))
