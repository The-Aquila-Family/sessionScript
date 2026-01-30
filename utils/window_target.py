from __future__ import annotations

from typing import Optional

import pygetwindow as gw


def find_window_by_title_substring(title_substring: str) -> Optional[gw.Win32Window]:
    needle = (title_substring or "").strip().lower()
    if not needle:
        return None

    for w in gw.getAllWindows():
        try:
            t = (w.title or "").lower()
        except Exception:
            continue
        if needle in t:
            return w
    return None

def is_window_active(title_substring: str) -> bool:
    needle = (title_substring or "").strip().lower()
    if not needle:
        return False

    try:
        active = gw.getActiveWindow()
        if not active:
            return False
        return needle in (active.title or "").lower()
    except Exception:
        return False

def activate_window(title_substring: str) -> bool:
    w = find_window_by_title_substring(title_substring)
    if not w:
        return False

    try:
        if w.isMinimized:
            w.restore()
        w.activate()
        return True
    except Exception:
        return False
