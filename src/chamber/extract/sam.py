"""Click -> outline, with MobileSAM (Apache-2.0) run through onnxruntime.

The image is split into overlapping square windows. A window is "encoded"
once (about a second on a laptop CPU) and kept in a small cache, so every
further click, extra point or box inside it answers in a fraction of a second.

Window size follows the ground: about 60 m across when the image is placed,
so a click sees the whole building, not one roof sheet.
"""
from __future__ import annotations
import os, sys, threading
from collections import OrderedDict
from dataclasses import dataclass
import numpy as np

SIDE = 1024
MEAN = np.array([123.675, 116.28, 103.53], np.float32)
STD = np.array([58.395, 57.12, 57.375], np.float32)
WINDOW_M = 60.0


def model_dir():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "assets", "models")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", "assets", "models"))


def available():
    d = model_dir()
    return all(os.path.exists(os.path.join(d, f)) for f in ("sam_encoder.onnx", "sam_decoder.onnx"))


@dataclass
class Window:
    x0: int; y0: int; size: int          # square window in image pixels
    scale: float                         # window px -> 1024 model px
    emb: np.ndarray                      # (1, 256, 64, 64)


@dataclass
class Result:
    masks: np.ndarray        # (k, size, size) bool, window space, best first
    scores: np.ndarray       # (k,)
    window: Window
    low_res: np.ndarray      # (k, 1, 256, 256) logits, for refining with more clicks


class Segmenter:
    def __init__(self, image, gsd=None, cache=8, threads=None, window_px=None):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        d = model_dir()
        self.enc = ort.InferenceSession(os.path.join(d, "sam_encoder.onnx"), so, providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(os.path.join(d, "sam_decoder.onnx"), so, providers=["CPUExecutionProvider"])
        self.image = image
        h, w = image.shape[:2]
        if gsd:
            size = int(np.clip(WINDOW_M / gsd, SIDE, max(h, w)))
        else:
            size = min(2048, max(h, w))
        if window_px:
            size = window_px
        self.size = int(min(size, max(h, w)))
        self.cache = OrderedDict(); self.cache_n = cache
        self.lock = threading.Lock()

    # ---------- windows ----------
    def _grid(self, n_total):
        step = max(1, self.size // 2)
        return list(range(0, max(n_total - self.size, 0) + 1, step)) + ([max(n_total - self.size, 0)] if n_total > self.size else [])

    def window_pos(self, xs, ys):
        """Top-left of the window (on a half-overlap grid) that best centres these points."""
        h, w = self.image.shape[:2]
        cx, cy = float(np.mean(xs)), float(np.mean(ys))
        gx = min(set(self._grid(w)), key=lambda g: abs(g + self.size / 2 - cx))
        gy = min(set(self._grid(h)), key=lambda g: abs(g + self.size / 2 - cy))
        return gx, gy

    def window_for(self, xs, ys):
        return self.encode(*self.window_pos(xs, ys))

    def is_encoded(self, x0, y0):
        return (x0, y0) in self.cache

    def windows_all(self):
        h, w = self.image.shape[:2]
        return [(x, y) for y in sorted(set(self._grid(h))) for x in sorted(set(self._grid(w)))]

    def encode(self, x0, y0):
        import cv2
        key = (x0, y0)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        crop = self.image[y0:y0 + self.size, x0:x0 + self.size]
        ch, cw = crop.shape[:2]
        scale = SIDE / max(ch, cw)
        r = cv2.resize(crop, (int(round(cw * scale)), int(round(ch * scale))), interpolation=cv2.INTER_AREA)
        x = np.zeros((SIDE, SIDE, 3), np.float32)
        x[:r.shape[0], :r.shape[1]] = (r.astype(np.float32) - MEAN) / STD
        emb = self.enc.run(None, {"image": x.transpose(2, 0, 1)[None]})[0]
        win = Window(x0, y0, max(ch, cw), scale, emb)
        with self.lock:
            self.cache[key] = win
            while len(self.cache) > self.cache_n:
                self.cache.popitem(last=False)
        return win

    # ---------- prompts ----------
    def predict(self, points=(), labels=(), box=None, prev=None, window=None):
        """points: [(x, y)] image px; labels: 1 keep / 0 cut; box: (x0, y0, x1, y1) image px.
        prev: a Result from the same window to refine (its best low-res mask)."""
        xs = [p[0] for p in points] + ([box[0], box[2]] if box else [])
        ys = [p[1] for p in points] + ([box[1], box[3]] if box else [])
        win = window or (prev.window if prev else self.window_for(xs, ys))
        pc, pl = [], []
        for (x, y), l in zip(points, labels):
            pc.append(((x - win.x0) * win.scale, (y - win.y0) * win.scale)); pl.append(float(l))
        if box:
            pc += [((box[0] - win.x0) * win.scale, (box[1] - win.y0) * win.scale),
                   ((box[2] - win.x0) * win.scale, (box[3] - win.y0) * win.scale)]
            pl += [2.0, 3.0]
        else:
            pc.append((0.0, 0.0)); pl.append(-1.0)
        mask_in = np.zeros((1, 1, 256, 256), np.float32); has = np.zeros(1, np.float32)
        if prev is not None and prev.window is win:
            mask_in = prev.low_res[:1].astype(np.float32); has[:] = 1
        masks, iou, low = self.dec.run(None, {
            "image_embeddings": win.emb,
            "point_coords": np.array([pc], np.float32), "point_labels": np.array([pl], np.float32),
            "mask_input": mask_in, "has_mask_input": has,
            "orig_im_size": np.array([win.size, win.size], np.float32)})
        masks, iou, low = masks[0] > 0, iou[0], low[0][:, None]
        # one click is ambiguous: offer the three multimask choices, best first.
        # more clicks / a box: the single-mask head (index 0) is the one to trust.
        single = len(points) == 1 and not box and prev is None
        idx = [1, 2, 3] if single else [0, 1, 2, 3]
        idx = sorted(idx, key=lambda i: -iou[i])
        if not single:
            idx = [0] + [i for i in idx if i != 0]
        keep = [i for i in idx if masks[i].any()]
        return Result(masks[keep], iou[keep], win, low[keep])

    # ---------- for "find similar" ----------
    def embedding_grid(self, win):
        """(64, 64, 256) unit vectors and the window px size of one cell."""
        e = win.emb[0].transpose(1, 2, 0)
        e = e / (np.linalg.norm(e, axis=2, keepdims=True) + 1e-6)
        return e, (SIDE / 64) / win.scale
