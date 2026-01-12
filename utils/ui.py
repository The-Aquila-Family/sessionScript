from __future__ import annotations

import threading
import tkinter as tk

from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Any, cast

from utils.capture import CropRect
from utils.workflow import JobParams, run_once


@dataclass(frozen=True)
class UiDefaults:
    crop_w: str = "800"
    crop_h: str = "450"
    crop_x: str = "0"
    crop_y: str = "0"
    delay_s: str = "0.15"
    interval_s: str = "30"
    monitor_index: str = "1"
    key: str = "z"
    message: str = ""


class App(tk.Tk):
    def __init__(self, defaults: UiDefaults | None = None):
        super().__init__()
        self.title("Session Screenshot to Discord")
        self.resizable(False, False)

        d = defaults or UiDefaults()

        self.webhook_var = tk.StringVar(value = "")
        self.message_var = tk.StringVar(value = d.message)
        self.key_var = tk.StringVar(value = d.key)

        self.crop_x_var = tk.StringVar(value = d.crop_x)
        self.crop_y_var = tk.StringVar(value = d.crop_y)
        self.crop_w_var = tk.StringVar(value = d.crop_w)
        self.crop_h_var = tk.StringVar(value = d.crop_h)

        self.delay_var = tk.StringVar(value = d.delay_s)
        self.interval_var = tk.StringVar(value = d.interval_s)
        self.monitor_var = tk.StringVar(value = d.monitor_index)

        self.status_var = tk.StringVar(value = "Idle")

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self)
        cast(Any, frm).grid(row = 0, column = 0, **pad)

        r = 0

        ttk.Label(frm, text = "Discord Webhook URL:").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.webhook_var, width = 64).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Label(frm, text = "Key to press:").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.key_var, width = 10).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Label(frm, text = "Delay after keypress (seconds):").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.delay_var, width = 10).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Separator(frm).grid(row = r, column = 0, columnspan = 2, sticky = "ew", pady = 8)
        r += 1

        ttk.Label(frm, text = "Crop rectangle (pixels):").grid(row = r, column = 0, sticky = "w")
        r += 1

        crop_row = ttk.Frame(frm)
        crop_row.grid(row = r, column = 0, columnspan = 2, sticky = "w")

        ttk.Label(crop_row, text = "x").grid(row = 0, column = 0, sticky = "w")
        ttk.Entry(crop_row, textvariable = self.crop_x_var, width = 6).grid(row = 0, column = 1, padx = (4, 10))
        ttk.Label(crop_row, text = "y").grid(row = 0, column = 2, sticky = "w")
        ttk.Entry(crop_row, textvariable = self.crop_y_var, width = 6).grid(row = 0, column = 3, padx = (4, 10))
        ttk.Label(crop_row, text = "w").grid(row = 0, column = 4, sticky = "w")
        ttk.Entry(crop_row, textvariable = self.crop_w_var, width = 6).grid(row = 0, column = 5, padx = (4, 10))
        ttk.Label(crop_row, text = "h").grid(row = 0, column = 6, sticky = "w")
        ttk.Entry(crop_row, textvariable = self.crop_h_var, width = 6).grid(row = 0, column = 7, padx = (4, 0))
        r += 1

        ttk.Label(frm, text = "Monitor index (1 = primary):").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.monitor_var, width = 10).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Separator(frm).grid(row = r, column = 0, columnspan = 2, sticky = "ew", pady = 8)
        r += 1

        ttk.Label(frm, text = "Loop interval (seconds):").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.interval_var, width = 10).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Label(frm, text = "Discord message (optional):").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.message_var, width = 64).grid(row = r, column = 1, sticky = "w")
        r += 1

        btns = ttk.Frame(frm)
        btns.grid(row = r, column = 0, columnspan = 2, sticky = "w", pady = (8, 0))

        self.btn_once = ttk.Button(btns, text = "Send Once", command = self.on_send_once)
        self.btn_once.grid(row = 0, column = 0, padx = (0, 8))

        self.btn_start = ttk.Button(btns, text = "Start Loop", command = self.on_start_loop)
        self.btn_start.grid(row = 0, column = 1, padx = (0, 8))

        self.btn_stop = ttk.Button(btns, text = "Stop", command = self.on_stop_loop, state = "disabled")
        self.btn_stop.grid(row = 0, column = 2)

        r += 1

        ttk.Separator(frm).grid(row = r, column = 0, columnspan = 2, sticky = "ew", pady = 10)
        r += 1

        ttk.Label(frm, text = "Status:").grid(row = r, column = 0, sticky = "w")
        ttk.Label(frm, textvariable = self.status_var).grid(row = r, column = 1, sticky = "w")

    def _set_running_ui(self, running: bool) -> None:
        self.btn_once.config(state = "disabled" if running else "normal")
        self.btn_start.config(state = "disabled" if running else "normal")
        self.btn_stop.config(state = "normal" if running else "disabled")

    def _read_params(self) -> JobParams:
        webhook = self.webhook_var.get().strip()
        if not webhook:
            raise ValueError("Webhook URL is required.")

        key = self.key_var.get().strip()
        if not key:
            raise ValueError("Key is required.")

        try:
            delay_s = float(self.delay_var.get().strip())
        except ValueError as e:
            raise ValueError("Delay must be a number.") from e

        try:
            interval_s = float(self.interval_var.get().strip())
        except ValueError as e:
            raise ValueError("Interval must be a number.") from e

        try:
            monitor_index = int(self.monitor_var.get().strip())
        except ValueError as e:
            raise ValueError("Monitor index must be an integer.") from e

        try:
            crop_x = int(self.crop_x_var.get().strip())
            crop_y = int(self.crop_y_var.get().strip())
            crop_w = int(self.crop_w_var.get().strip())
            crop_h = int(self.crop_h_var.get().strip())
        except ValueError as e:
            raise ValueError("Crop x/y/w/h must be integers.") from e

        if monitor_index < 1:
            raise ValueError("Monitor index must be >= 1.")
        if delay_s < 0:
            raise ValueError("Delay must be >= 0.")
        if interval_s < 0:
            raise ValueError("Interval must be >= 0.")
        if crop_x < 0 or crop_y < 0:
            raise ValueError("Crop x/y must be >= 0.")
        if crop_w <= 0 or crop_h <= 0:
            raise ValueError("Crop w/h must be > 0.")

        return JobParams(
            webhook_url = webhook,
            message = self.message_var.get(),
            key = key,
            delay_s = delay_s,
            monitor_index = monitor_index,
            crop = CropRect(x = crop_x, y = crop_y, w = crop_w, h = crop_h),
        )

    def on_send_once(self) -> None:
        try:
            params = self._read_params()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        def worker():
            try:
                self.status_var.set("Working (single capture)...")
                run_once(params)
                self.status_var.set("Done (posted).")
            except Exception as e:
                self.status_var.set("Error.")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target = worker, daemon = True).start()

    def on_start_loop(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        try:
            params = self._read_params()
            interval_s = float(self.interval_var.get().strip())
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        if interval_s <= 0:
            messagebox.showerror("Invalid input", "Interval must be > 0 to start loop.")
            return

        self._stop_event.clear()
        self._set_running_ui(True)
        self.status_var.set("Loop running...")

        def loop_worker():
            while not self._stop_event.is_set():
                try:
                    run_once(params)
                    self.after(0, lambda: self.status_var.set("Loop running (last post ok)."))
                except Exception as e:
                    self.after(0, lambda: self.status_var.set("Loop running (last post error)."))
                    self.after(0, lambda: messagebox.showerror("Error", str(e)))

                if self._stop_event.wait(timeout = interval_s):
                    break

            self.after(0, lambda: self._set_running_ui(False))
            self.after(0, lambda: self.status_var.set("Stopped."))

        self._thread = threading.Thread(target = loop_worker, daemon = True)
        self._thread.start()

    def on_stop_loop(self) -> None:
        self._stop_event.set()
        self.status_var.set("Stopping...")

    def on_close(self) -> None:
        self._stop_event.set()
        self.destroy()
