"""The stage's clip chaining: seamless order, random throws, a clean finish."""
import random
import pytest

pytest.importorskip("PySide6")
from chamber.gui import ClipPlan  # noqa: E402

CLIPS = {"throws": ["s", "m", "l"], "pet": "pet", "finish": "finish"}


def test_running_alternates_throw_and_pet_without_repeating_a_throw():
    plan = ClipPlan(CLIPS, random.Random(1))
    seq = [plan.next(running=True, finishing=False) for _ in range(40)]
    throws, pets = seq[0::2], seq[1::2]
    assert all(t in CLIPS["throws"] for t in throws)
    assert all(p == "pet" for p in pets)
    assert all(a != b for a, b in zip(throws, throws[1:]))      # never the same distance twice
    assert set(throws) == set(CLIPS["throws"])                   # all distances get used


def test_finish_after_a_throw_goes_through_pet_then_finish():
    plan = ClipPlan(CLIPS, random.Random(2))
    plan.next(True, False)                         # a throw is playing when the run ends
    assert plan.next(False, True) == "pet"
    assert plan.next(False, True) == "finish"
    assert plan.next(False, True) is None          # rest on the last frame
    assert plan.next(True, False) is None          # 'done' until reset


def test_finish_after_pet_goes_straight_to_finish():
    plan = ClipPlan(CLIPS, random.Random(3))
    plan.next(True, False); plan.next(True, False)  # throw, pet -> back at the hub
    assert plan.next(False, True) == "finish"


def test_reset_starts_again_from_the_hub():
    plan = ClipPlan(CLIPS, random.Random(4))
    plan.next(True, False); plan.next(False, True); plan.next(False, True)
    plan.reset()
    assert plan.next(True, False) in CLIPS["throws"]


def test_missing_clips_do_not_crash():
    assert ClipPlan({}).next(True, False) is None
    only = ClipPlan({"throws": ["m"]})
    assert only.next(True, False) == "m"
    assert only.next(True, False) is None            # no pet clip: just stop
    assert ClipPlan({"throws": ["m"]}).next(False, True) is None
