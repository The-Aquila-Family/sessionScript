from __future__ import annotations

import time
from dataclasses import dataclass

from utils.capture import CropRect, press_key, capture_cropped
from utils.discord_webhook import discordwebhook, probe_webhook


@dataclass(frozen = True)
class JobParams:
    webhook_url: str
    message: str
    key: str
    delay_s: float
    monitor_index: int
    crop: CropRect


def run_once(params: JobParams) -> None:
    if params.delay_s < 0:
        raise ValueError("delay_s must be >= 0")
    if params.monitor_index < 1:
        raise ValueError("monitor_index must be >= 1")

    probe_webhook(params.webhook_url)

    press_key(params.key)
    time.sleep(params.delay_s)

    png = capture_cropped(params.monitor_index, params.crop)

    discordwebhook(webhook_url = params.webhook_url, image_bytes = png, filename = "crop.png", content = params.message)
