from __future__ import annotations

import requests

def discordwebhook(webhook_url: str, image_bytes: bytes, filename: str = "crop.png", content: str = "", timeout_s: int = 20,) -> None:
    webhook_url = (webhook_url or "").strip()
    if not webhook_url:
        raise ValueError("webhook_url is required")

    files = {"file": (filename, image_bytes, "image/png")}
    data = {}
    if content and content.strip():
        data["content"] = content.strip()

    resp = requests.post(webhook_url, data = data, files = files, timeout = timeout_s)
    if resp.status_code >= 300:
        raise RuntimeError(f"Discord webhook failed: {resp.status_code} {resp.text[:300]}")
