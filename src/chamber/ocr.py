"""Read text off the sheet with offline OCR (RapidOCR / ONNX Runtime).

Two readers, both optional and fully offline:
  * read_labels  - the block number painted INSIDE the map, guided by the traced
                   polygon (neighbour numbers fall outside and are ignored).
  * read_panel   - the header panel in the left margin: State / District /
                   Sub-district / Town-Village names and codes, Ward, block
                   number, and the created / modified / generated timestamps.
                   Read in sharp overlapping tiles so small digits aren't lost.

Sheet-specific details live in an optional, private *sheet profile* (a small
JSON file kept outside the code, see sheet_profile.example.json):
  * id_layout    - how a numeric sheet-ID filename splits into codes. When the
                   filename matches, every code comes from it (exact) and OCR
                   only double-checks the block number.
  * label_words  - extra words printed on your sheets that are labels, not
                   names, so they are never mistaken for a place name.
Without a profile the readers still work; codes then come from OCR alone.
Names and dates always come from OCR. Blank fields are listed in meta_missing
so a reviewer knows what to double-check."""
from __future__ import annotations
import json, os, re
from pathlib import Path

# fields the map reader adds, and the panel reader adds
MAP_FIELDS = ["block_label", "place_label", "label_conf", "id_match"]
PANEL_FIELDS = ["state", "state_code", "district", "district_code",
                "subdistrict", "subdistrict_code", "town_village", "town_code",
                "ward_no", "block_no", "created_on", "modified_on", "generated_on"]
OCR_FIELDS = MAP_FIELDS + PANEL_FIELDS

# short (<=10 char) names for shapefile columns
SHP_NAMES = {
    "block_label": "blk_id", "place_label": "place", "label_conf": "id_conf",
    "id_match": "id_ok", "state": "state", "state_code": "st_code",
    "district": "district", "district_code": "di_code", "subdistrict": "subdist",
    "subdistrict_code": "sd_code", "town_village": "town", "town_code": "tn_code",
    "ward_no": "ward", "block_no": "block_no", "created_on": "created",
    "modified_on": "modified", "generated_on": "generated",
}

# generic form words that are labels, never names
_BASE_STOP = {"name", "of", "state", "district", "sub", "subdistrict", "town",
              "village", "code", "no", "ward", "block", "legend", "note", "boundary",
              "boundry", "landmark", "with", "map", "generated", "created", "modified",
              "numbers", "shown", "inside", "area", "indicate", "the", "on", "for"}
_BASE_PREFIXES = ("nameof", "codeno", "wardno", "blockno", "subdistrict", "townvillage")


# ---------- private sheet profile ----------
PROFILE_NAME = "sheet_profile.json"
_PROFILE = None


def profile_path():
    """Where the private profile is looked for: the CHAMBER_PROFILE environment
    variable if set, otherwise %APPDATA%\\CHAMBER\\sheet_profile.json."""
    env = os.environ.get("CHAMBER_PROFILE")
    if env:
        return Path(env)
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / "CHAMBER" / PROFILE_NAME


def load_profile(path=None) -> dict:
    """Read the profile (cached). A missing or broken file means 'no profile'."""
    global _PROFILE
    if path is None and _PROFILE is not None:
        return _PROFILE
    prof = {}
    try:
        f = Path(path) if path else profile_path()
        if f.is_file():
            prof = json.loads(f.read_text(encoding="utf-8")) or {}
    except Exception:
        prof = {}
    if path is None:
        _PROFILE = prof
    return prof


def reset_profile():
    """Forget the cached profile (tests, or after editing the file)."""
    global _PROFILE
    _PROFILE = None


def _stop_words():
    extra = {str(w).lower() for w in load_profile().get("label_words", [])}
    return _BASE_STOP | extra


def _label_prefixes():
    extra = tuple(str(w).lower() for w in load_profile().get("label_prefixes", []))
    return _BASE_PREFIXES + extra


_ENGINE = None
_TRIED = False


def _clean(txt) -> str:
    """Keep plain Latin text only. The OCR model knows Chinese too, so on a
    smudge it sometimes 'reads' a character like 川. The sheets are English, so
    those are always misreads: drop them (fullwidth digits become normal)."""
    import unicodedata
    t = unicodedata.normalize("NFKC", str(txt))
    t = "".join(ch for ch in t if 32 <= ord(ch) < 127)
    return re.sub(r"\s+", " ", t).strip()


def _engine():
    global _ENGINE, _TRIED
    if _ENGINE is None and not _TRIED:
        _TRIED = True
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ENGINE = RapidOCR()
        except Exception:
            _ENGINE = None
    return _ENGINE


def available() -> bool:
    return _engine() is not None


# ---------- in-map block label ----------
def _box_centre(box):
    xs = [p[0] for p in box]; ys = [p[1] for p in box]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def read_labels(img, poly, sheet_id):
    """The numeric label inside the traced block, plus the biggest place word."""
    eng = _engine()
    if eng is None:
        return {}
    from shapely.geometry import Point
    try:
        result, _ = eng(img)
    except Exception:
        return {}
    nums, words = [], []
    for box, txt, conf in (result or []):
        txt = _clean(txt)
        if not txt:
            continue
        cx, cy = _box_centre(box)
        inside = poly.contains(Point(cx, cy))
        digits = re.sub(r"\D", "", txt)
        if len(digits) >= 2:
            nums.append((digits, float(conf), inside, cx, cy))
        elif re.search(r"[A-Za-z]", txt):
            words.append((txt.strip(), inside, cx, cy))
    inside_nums = [n for n in nums if n[2]]
    # the block's own number sits near the block centre; a number far out toward
    # the edge is a neighbour's label bleeding in, so reject it rather than report
    # the wrong id (the panel's block number is the authoritative source anyway)
    pick = None
    if inside_nums:
        c = poly.centroid
        radius = (poly.area / 3.141592653589793) ** 0.5

        def dist(n):
            return ((n[3] - c.x) ** 2 + (n[4] - c.y) ** 2) ** 0.5
        near = [n for n in inside_nums if dist(n) <= 0.7 * radius]
        # a block can hold more than one number (e.g. its own 0011 plus a stray
        # 0040). If one of them is the block number from the filename, use it.
        want = codes_from_sheet_id(sheet_id).get("block_no")
        same = [n for n in near if want and same_number(n[0], want)]
        if same:
            pick = max(same, key=lambda n: n[1])
        elif near:
            pick = min(near, key=dist)
    block_label = pick[0] if pick else ""
    label_conf = round(pick[1], 3) if pick else 0.0
    inside_words = [w for w in words if w[1]]
    place = max(inside_words, key=lambda w: len(w[0]))[0] if inside_words else ""
    id_match = bool(block_label) and block_label in re.sub(r"\D", "", str(sheet_id))
    return {"block_label": block_label, "label_conf": label_conf,
            "place_label": place, "id_match": id_match}


# ---------- codes straight from the filename ----------
# If the profile has an id_layout, a filename that is exactly id_length digits
# is split into codes, e.g. {"id_length": 8, "id_layout": [["district_code", 0, 2],
# ["block_no", 2, 6]]}. The filename is exact, OCR is not, so when the name has
# this shape the codes come from it. No layout = no codes from the filename.
def _id_layout():
    prof = load_profile()
    parts = prof.get("id_layout") or []
    n = prof.get("id_length")
    try:
        parts = [(str(k), int(a), int(b)) for k, a, b in parts]
        n = int(n) if n else (max(b for _, _, b in parts) if parts else 0)
    except Exception:
        return 0, []
    return n, parts


def codes_from_sheet_id(sheet_id) -> dict:
    n, parts = _id_layout()
    g = str(sheet_id)
    if not parts or not re.fullmatch(r"\d{%d}" % n, g):
        return {}
    return {k: g[a:b] for k, a, b in parts}


def same_number(a, b) -> bool:
    """'13' == '0013'; blanks never match."""
    da, db = re.sub(r"\D", "", str(a)), re.sub(r"\D", "", str(b))
    return bool(da) and bool(db) and int(da) == int(db)


# ---------- header panel ----------
_TILE, _OVERLAP, _DPI = 900, 200, 300


def _panel_items(page, x0):
    """OCR the left panel in overlapping horizontal tiles.

    The OCR engine shrinks any image taller than 2000 px. The whole panel is
    ~3500 px at 300 dpi, so read in one go it gets squashed and small things
    (single boxed digits, a short name like 'Elm') vanish. Tiles stay sharp.
    Each tile only 'owns' its middle part, so text in an overlap is kept once."""
    import numpy as np, fitz
    eng = _engine()
    z = _DPI / 72.0
    H = page.rect.height * z
    items, y = [], 0.0
    while True:
        y1 = min(y + _TILE, H)
        pix = page.get_pixmap(matrix=fitz.Matrix(z, z),
                              clip=fitz.Rect(0, y / z, x0, y1 / z))
        img = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width, pix.n)[:, :, :3]
        try:
            result, _ = eng(img)
        except Exception:
            result = None
        lo = y + (_OVERLAP / 2 if y > 0 else -1)
        hi = y1 - (_OVERLAP / 2 if y1 < H else -1)
        for box, txt, conf in (result or []):
            t = _clean(txt)
            if not t:
                continue
            xs = [p[0] for p in box]; ys = [p[1] + y for p in box]
            cy = sum(ys) / 4
            if lo <= cy < hi:
                items.append({"t": t, "x0": min(xs), "cx": sum(xs) / 4, "cy": cy})
        if y1 >= H:
            break
        y = y1 - _OVERLAP
    return items


# zoom levels for the second look: (dpi, white margin in px). A thin '1' in a
# box that one zoom misses is usually caught by another.
_RESCUE_ZOOMS = [(300, 0), (200, 0), (600, 40)]


def _row_items(page, x0, cy, half=50, dpi=300, pad=0):
    """Second look: OCR just one row strip centred on cy. Coordinates are
    returned in the same 300-dpi pixel frame as the tile pass."""
    import numpy as np, fitz
    z = _DPI / 72.0
    zz = dpi / 72.0
    k = _DPI / dpi                                  # this zoom's px -> 300-dpi px
    top = max(cy - half, 0)
    pix = page.get_pixmap(matrix=fitz.Matrix(zz, zz),
                          clip=fitz.Rect(0, top / z, x0, (cy + half) / z))
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    if pad:
        img = np.pad(img, ((pad, pad), (pad, pad), (0, 0)), constant_values=255)
    try:
        result, _ = _engine()(np.ascontiguousarray(img))
    except Exception:
        return []
    out = []
    for box, txt, conf in (result or []):
        t = _clean(txt)
        if t:
            xs = [(p[0] - pad) * k for p in box]; ys = [(p[1] - pad) * k + top for p in box]
            out.append({"t": t, "x0": min(xs), "cx": sum(xs) / 4, "cy": sum(ys) / 4})
    return out


def _digit_chars(t):
    """Digits in a token. In a short digit-ish token, O/o means 0 and I/l/| means 1
    (the boxed code digits are often read as letters)."""
    if re.fullmatch(r"[0-9OoIl|]{1,6}", t):
        t = t.translate(str.maketrans("OoIl|", "00111"))
    return re.findall(r"\d", t)


def _is_label_word(wl):
    return wl in _stop_words() or wl.startswith(_label_prefixes())


def read_panel(page, gref, block_label=""):
    """Read the header panel in the left margin and parse its fields."""
    if _engine() is None:
        return {}
    x0 = gref.bbox[0]
    if x0 < 60:                                    # no real side panel
        return {}
    it = _panel_items(page, x0)

    def _digits(items, anchor, tol=55):
        ds = [(x["cx"], ch) for x in items if abs(x["cy"] - anchor["cy"]) < tol
              and x["cx"] >= anchor["x0"] - 5 for ch in _digit_chars(x["t"])]
        ds.sort()
        return "".join(ch for _, ch in ds)

    def digits_row(anchor, want=None):
        """Boxed digits on the label's row. If we got the wrong number of digits,
        take a zoomed second look at just that row."""
        got = _digits(it, anchor)
        if want and len(got) != want:
            for dpi, pad in _RESCUE_ZOOMS:
                again = _digits(_row_items(page, x0, anchor["cy"], dpi=dpi, pad=pad), anchor)
                if abs(len(again) - want) < abs(len(got) - want):
                    got = again
                if len(got) == want:
                    break
        return got

    def name_row(anchor, tol=55):
        """The value is the right-most text on the label's row, minus label words.
        Multi-word names ('North Ridge') are kept whole."""
        best = None
        for x in it:
            if abs(x["cy"] - anchor["cy"]) < tol:
                words = [w for w in re.findall(r"[A-Za-z]{3,}", x["t"])
                         if not _is_label_word(w.lower())]
                if words and (best is None or x["cx"] > best[0]):
                    best = (x["cx"], " ".join(words))
        return best[1] if best else ""

    def date_row(anchor):
        got = _date(it, anchor)
        for dpi, pad in _RESCUE_ZOOMS:
            if got:
                break
            got = _date(_row_items(page, x0, anchor["cy"], dpi=dpi, pad=pad), anchor)
        return got

    def _date(items, anchor, tol=55):
        for x in items:
            if abs(x["cy"] - anchor["cy"]) < tol:
                # the day's leading 0 sometimes melts into the dotted line
                # ("..1-06-2026"), so accept a 1-digit day and pad it back
                m = re.search(r"(?<!\d)(\d{1,2})-(\d{2})-(\d{4})", x["t"])
                if m:
                    date = f"{int(m.group(1)):02d}-{m.group(2)}-{m.group(3)}"
                    tail = re.search(r"\d{2}:\d{2}(:\d{2})?", x["t"][m.end():])
                    return date + ((" " + tail.group(0)) if tail else "")
        return ""

    out = {}

    def put(k, v):                                 # never overwrite a value with a blank
        if v or k not in out:
            out[k] = v

    code_anchors = []
    date_cy = {}                                   # where each date label was seen
    for x in it:
        low = x["t"].lower().replace(" ", "")
        for key, word in (("created_on", "createdon"), ("modified_on", "modifiedon"),
                          ("generated_on", "generatedon")):
            if word in low:
                date_cy[key] = x["cy"]
        if "nameofstate" in low:
            put("state", name_row(x))
        elif "nameofsub" in low:
            put("subdistrict", name_row(x))
        elif "nameofdistrict" in low:
            put("district", name_row(x))
        elif "nameoftown" in low or "village" in low:
            put("town_village", name_row(x))
        elif "wardno" in low:
            put("ward_no", digits_row(x, 4))
        elif "blockno" in low:                     # NOT "block boundary"
            put("block_no", digits_row(x, 4))
        elif "codeno" in low:
            code_anchors.append(x)
        elif "createdon" in low:
            put("created_on", date_row(x))
        elif "modifiedon" in low:
            put("modified_on", date_row(x))
        elif "generatedon" in low or "mapgenerated" in low:
            put("generated_on", date_row(x))

    code_anchors.sort(key=lambda a: a["cy"])
    for (k, n), a in zip([("state_code", 2), ("district_code", 2),
                          ("subdistrict_code", 3), ("town_code", 4)], code_anchors):
        put(k, digits_row(a, n))

    # A date LABEL itself can be missed (the last line sits right at the page
    # edge). The three date lines are evenly spaced, so look where it should be.
    order = ["created_on", "modified_on", "generated_on"]
    seen = [(order.index(k), cy) for k, cy in date_cy.items()]
    if seen:
        if len(seen) >= 2:
            (i0, y0), (i1, y1) = min(seen), max(seen)
            step = (y1 - y0) / (i1 - i0) if i1 != i0 else 100
        else:
            step = 100
        i0, y0 = min(seen)
        for i, key in enumerate(order):
            if key not in date_cy:
                put(key, date_row({"cy": y0 + (i - i0) * step, "x0": 0}))

    # (the pipeline decides the final block number: filename, then panel, then map)
    missing = [k for k in PANEL_FIELDS if not out.get(k)]
    out = {k: out.get(k, "") for k in PANEL_FIELDS}
    out["meta_missing"] = ",".join(missing)
    return out
