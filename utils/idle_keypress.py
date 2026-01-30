from __future__ import annotations

import random
import threading
import time
import pyautogui

from dataclasses import dataclass
from utils.window_target import is_window_active, activate_window

@dataclass(frozen = True)
class IdleKeypressConfig:
    keys: str = "wasd"
    min_seconds: int = 1
    max_seconds: int = 60

    bind_to_target: bool = False
    target_title: str = ""
    force_focus: bool = False

class IdleKeyPresser:
    def __init__(self, config: IdleKeypressConfig, capture_in_progress_event: threading.Event):
        self._config = config
        self._capture_event = capture_in_progress_event
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        pyautogui.FAILSAFE = True

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target = self._run, daemon = True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        keys = (self._config.keys or "").strip()
        if not keys:
            return

        min_s = int(self._config.min_seconds)
        max_s = int(self._config.max_seconds)
        if min_s < 1:
            min_s = 1
        if max_s < min_s:
            max_s = min_s

        while not self._stop_event.is_set():
            while self._capture_event.is_set() and not self._stop_event.is_set():
                time.sleep(0.05)

            if self._stop_event.is_set():
                break

            wait_s = random.randint(min_s, max_s)
            if self._stop_event.wait(timeout = wait_s):
                break

            if self._capture_event.is_set():
                continue

            target = (self._config.target_title or "").strip()

            if self._config.bind_to_target and target:
                if not is_window_active(target):
                    if self._config.force_focus:
                        ok = activate_window(target)
                        if not ok:
                            continue
                        if not is_window_active(target):
                            continue
                    else:
                        continue

            ch = random.choice(list(keys))
            try:
                pyautogui.press(ch)
            except Exception:
                break

