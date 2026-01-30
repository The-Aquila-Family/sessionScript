from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import mss
import pyautogui
from PIL import Image


@dataclass(frozen = True)
class CropRect:
    x: int = 0
    y: int = 0
    w: int = 800
    h: int = 450

def key_down(key: str) -> None:
    pyautogui.keyDown(key)

def key_up(key: str) -> None:
    pyautogui.keyUp(key)

def screenshot_monitor(monitor_index: int = 1) -> Image.Image:
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index < 1 or monitor_index >= len(monitors):
            raise ValueError(f"monitor_index must be between 1 and {len(monitors) - 1}")

        mon = monitors[monitor_index]
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def crop_image(img: Image.Image, rect: CropRect) -> Image.Image:
    if rect.w <= 0 or rect.h <= 0:
        raise ValueError("Crop width/height must be > 0")
    if rect.x < 0 or rect.y < 0:
        raise ValueError("Crop x/y must be >= 0")

    return img.crop((rect.x, rect.y, rect.x + rect.w, rect.y + rect.h))


def image_convert(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def capture_cropped(monitor_index: int, rect: CropRect) -> bytes:
    img = screenshot_monitor(monitor_index)
    cropped = crop_image(img, rect)
    return image_convert(cropped)
