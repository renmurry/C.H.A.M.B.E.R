"""Which glass each Windows build gets, and that other systems never try."""
import sys
from chamber import winglass as G


def test_mode_by_build():
    assert G.mode_for_build(26100) == "acrylic"      # Windows 11 24H2
    assert G.mode_for_build(22621) == "acrylic"      # Windows 11 22H2 (first with the backdrop API)
    assert G.mode_for_build(22000) == "blur"         # Windows 11 21H2
    assert G.mode_for_build(19045) == "blur"         # Windows 10 22H2
    assert G.mode_for_build(15063) == "none"         # very old Windows 10
    assert G.mode_for_build(0) == "none"


def test_non_windows_never_applies():
    if sys.platform != "win32":
        assert G.windows_build() == 0
        assert G.apply(12345) is False
