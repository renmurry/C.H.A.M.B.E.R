"""Badges / achievements, saved to %APPDATA%\\CHAMBER\\stats.json.

Pure logic + storage, kept out of the GUI so it can be tested on its own.
A run "scores" only the sheets that succeeded; a fully clean run (nothing failed
or flagged) also counts toward streak-based badges.
"""
from __future__ import annotations
import json, os
from pathlib import Path

# badge id, display name, one-line description, and a test over the stats dict
BADGES = [
    ("first_light", "First Light",   "Trace your first sheet.",
     lambda s: s["total_blocks"] >= 1),
    ("regular",     "Regular",       "Finish 10 runs.",
     lambda s: s["total_runs"] >= 10),
    ("centurion",   "Centurion",     "Trace 100 sheets in total.",
     lambda s: s["total_blocks"] >= 100),
    ("cartographer","Cartographer",  "Trace 1,000 sheets in total.",
     lambda s: s["total_blocks"] >= 1000),
    ("spotless",    "Spotless",      "Finish a run with zero issues.",
     lambda s: s["clean_runs"] >= 1),
    ("on_a_roll",   "On a Roll",     "10 clean runs in a row.",
     lambda s: s["best_streak"] >= 10),
    ("heavy_lifter","Heavy Lifter",  "Process 25+ sheets in one run.",
     lambda s: s["max_batch"] >= 25),
    ("polyglot",    "Polyglot",      "Export in all five formats.",
     lambda s: len(set(s["formats_used"]) & {"geojson","kml","shp","gpkg","dxf"}) == 5),
]

_DEFAULT = {"total_blocks": 0, "total_runs": 0, "clean_runs": 0,
            "clean_streak": 0, "best_streak": 0, "max_batch": 0,
            "formats_used": [], "unlocked": []}


def stats_path() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "CHAMBER"
    d.mkdir(parents=True, exist_ok=True)
    return d / "stats.json"


def load_stats() -> dict:
    try:
        s = json.loads(stats_path().read_text(encoding="utf-8"))
    except Exception:
        s = {}
    return {**_DEFAULT, **s}


def save_stats(stats: dict) -> None:
    try:
        stats_path().write_text(json.dumps(stats, indent=2), encoding="utf-8")
    except Exception:
        pass   # never let a stats write break a run


def badge_name(bid: str) -> str:
    for i, name, *_ in BADGES:
        if i == bid:
            return name
    return bid


def record_run(summary: dict, formats) -> tuple[dict, list]:
    """Update lifetime stats from a finished run; return (stats, newly_unlocked).
    newly_unlocked is a list of (id, name, description) tuples."""
    s = load_stats()
    ok = int(summary.get("ok", 0))
    flagged = int(summary.get("flagged", 0))
    failed = int(summary.get("failed", 0))
    clean = failed == 0 and flagged == 0 and ok > 0

    s["total_blocks"] += ok
    s["total_runs"] += 1
    s["clean_streak"] = s["clean_streak"] + 1 if clean else 0
    if clean:
        s["clean_runs"] += 1
    s["best_streak"] = max(s["best_streak"], s["clean_streak"])
    s["max_batch"] = max(s["max_batch"], ok)
    s["formats_used"] = sorted(set(s["formats_used"]) | set(formats or []))

    unlocked = set(s["unlocked"])
    newly = []
    for bid, name, desc, test in BADGES:
        if bid not in unlocked and test(s):
            unlocked.add(bid)
            newly.append((bid, name, desc))
    s["unlocked"] = sorted(unlocked)
    save_stats(s)
    return s, newly
