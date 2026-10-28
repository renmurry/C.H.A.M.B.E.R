"""Real glass (blur behind the window) on Windows, with no extra dependencies.

  Windows 11 22H2+ (build 22621+): the documented system backdrop,
      DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE=38, DWMSBT_TRANSIENTWINDOW=3),
      i.e. Desktop Acrylic behind the whole window.
  Windows 10 1803+ / early Windows 11: blur-behind through the (undocumented but
      long-standing) SetWindowCompositionAttribute(WCA_ACCENT_POLICY=19,
      ACCENT_ENABLE_BLURBEHIND=3).
Anything else, or any call that fails, returns False and the app paints its own
dark glass instead, so text always stays readable.
"""
from __future__ import annotations
import sys

WIN11_BACKDROP_BUILD = 22621
WIN10_BLUR_BUILD = 17134


def windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def mode_for_build(build: int) -> str:
    """Which glass a Windows build gets: 'acrylic', 'blur' or 'none'."""
    if build >= WIN11_BACKDROP_BUILD:
        return "acrylic"
    if build >= WIN10_BLUR_BUILD:
        return "blur"
    return "none"


def apply(hwnd: int) -> bool:
    """Turn on the glass for a top-level window handle. True if it took."""
    mode = mode_for_build(windows_build())
    if mode == "none" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        dwm = ctypes.windll.dwmapi
        hwnd = wintypes.HWND(hwnd)

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]

        def set_attr(attr, value):
            v = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(hwnd, ctypes.c_uint(attr), ctypes.byref(v), ctypes.sizeof(v))

        set_attr(20, 1)                                  # DWMWA_USE_IMMERSIVE_DARK_MODE: dark title bar
        if mode == "acrylic":
            if dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(-1, -1, -1, -1))) != 0:
                return False
            return set_attr(38, 3) == 0                  # DWMWA_SYSTEMBACKDROP_TYPE = DWMSBT_TRANSIENTWINDOW

        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]

        accent = ACCENT_POLICY(3, 0, 0, 0)               # ACCENT_ENABLE_BLURBEHIND
        data = WINCOMPATTRDATA(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent))
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        return bool(fn(hwnd, ctypes.byref(data)))
    except Exception:
        return False
