from __future__ import annotations

from typing import List

import pygetwindow as gw


def list_window_titles() -> List[str]:
    titles: List[str] = []
    for w in gw.getAllWindows():
        try:
            t = (w.title or "").strip()
        except Exception:
            continue
        if t:
            titles.append(t)

    seen = set()
    out: List[str] = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def get_active_window_title() -> str:
    try:
        w = gw.getActiveWindow()
        if not w:
            return ""
        return (w.title or "").strip()
    except Exception:
        return ""
