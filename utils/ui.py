from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
import json

from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Any, cast
from pathlib import Path

from utils.capture import CropRect
from utils.workflow import JobParams, run_once
from utils.idle_keypress import IdleKeyPresser, IdleKeypressConfig
from utils.window_picker import list_window_titles, get_active_window_title


@dataclass(frozen=True)
class UiDefaults:
    crop_w: str = "450"
    crop_h: str = "800"
    crop_x: str = "0"
    crop_y: str = "0"
    delay_s: str = "0.15"
    interval_s: str = "30"
    monitor_index: str = "1"
    key: str = "z"
    message: str = "Current session list"


class App(tk.Tk):
    def __init__(self, defaults: UiDefaults | None = None):
        super().__init__()
        self.title("Session Screenshot to Discord")
        self.resizable(False, False)

        d = defaults or UiDefaults()

        env_webhook = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
        self.webhook_var = tk.StringVar(value = env_webhook if env_webhook else "")

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

        self.idle_enabled_var = tk.BooleanVar(value = False)
        self.idle_keys_var = tk.StringVar(value = "wasd")
        self.idle_min_var = tk.StringVar(value = "1")
        self.idle_max_var = tk.StringVar(value = "60")

        self.window_select_var = tk.StringVar(value = "")
        self._window_titles: list[str] = []

        self.bind_window_var = tk.BooleanVar(value = False)

        self.idle_target_title_var = tk.StringVar(value = "")
        self.idle_force_focus_var = tk.BooleanVar(value = False)

        self._capture_in_progress = threading.Event()
        self._idle_presser: IdleKeyPresser | None = None

        app_dir = Path(os.getenv("APPDATA", ".")) / "SessionScreenshotDiscord"
        app_dir.mkdir(parents = True, exist_ok = True)
        self._webhooks_path = app_dir / "webhooks.json"


        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._webhooks: dict[str, str] = {}

        self.channel_name_var = tk.StringVar(value = "")
        self.channel_select_var = tk.StringVar(value = "")

        self._load_webhooks()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)


    def _get_webhook_value(self) -> str:
        v = (self.webhook_var.get() or "").strip()
        if not v:
            raise ValueError("Webhook URL is required.")
        return v

    def _ps_escape_for_double_quotes(self, s: str) -> str:
        return s.replace('"', '`"')

    def on_set_env_current_app(self) -> None:
        try:
            url = self._get_webhook_value()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        os.environ["DISCORD_WEBHOOK_URL"] = url
        self.status_var.set("Set DISCORD_WEBHOOK_URL for this app session.")

    def on_persist_env_setx(self) -> None:
        if os.name != "nt":
            messagebox.showerror("Not supported", "setx is Windows-only.")
            return

        try:
            url = self._get_webhook_value()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        url_escaped = self._ps_escape_for_double_quotes(url)
        cmd = f'setx DISCORD_WEBHOOK_URL "{url_escaped}"'

        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output = True,
                text = True,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run PowerShell.\n{e}")
            return

        if res.returncode != 0:
            msg = (res.stderr or res.stdout or "").strip()
            messagebox.showerror("setx failed", msg if msg else f"Return code: {res.returncode}")
            return

        os.environ["DISCORD_WEBHOOK_URL"] = url
        self.status_var.set("Persisted DISCORD_WEBHOOK_URL using setx. New terminals will see it.")
        messagebox.showinfo(
            "Done",
            "Saved DISCORD_WEBHOOK_URL using setx.\n"
            "Open a new terminal/session for it to appear there.\n"
            "This app will use it immediately.",
        )

    def on_load_webhook_from_env(self) -> None:
        v = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
        if not v:
            messagebox.showinfo("Not found", "DISCORD_WEBHOOK_URL is not set.")
            return
        self.webhook_var.set(v)
        self.status_var.set("Loaded webhook from DISCORD_WEBHOOK_URL.")

    def _load_webhooks(self) -> None:
        try:
            if self._webhooks_path.exists():
                data = json.loads(self._webhooks_path.read_text(encoding = "utf-8"))
                if isinstance(data, dict) and isinstance(data.get("channels"), dict):
                    self._webhooks = {
                        str(k): str(v) for k, v in data["channels"].items()
                        if isinstance(k, str) and isinstance(v, str)
                    }
                else:
                    self._webhooks = {}
            else:
                self._webhooks = {}
        except Exception:
            self._webhooks = {}

    def _save_webhooks(self) -> None:
        payload = {"channels": self._webhooks}
        self._webhooks_path.write_text(json.dumps(payload, indent = 2), encoding = "utf-8")

    def _refresh_channel_dropdown(self) -> None:
        if not hasattr(self, "channel_combo"):
            return
        names = sorted(self._webhooks.keys())
        self.channel_combo["values"] = names

        cur = (self.channel_select_var.get() or "").strip()
        if cur and cur not in self._webhooks:
            self.channel_select_var.set("")

    def on_select_channel(self, _event: object = None) -> None:
        name = (self.channel_select_var.get() or "").strip()
        if not name:
            return
        url = self._webhooks.get(name, "").strip()
        if url:
            self.webhook_var.set(url)
            self.status_var.set(f"Selected channel: {name}")

    def on_save_channel(self) -> None:
        name = (self.channel_name_var.get() or "").strip()
        if not name:
            messagebox.showerror("Invalid input", "Enter a channel name to save (e.g. screenshots).")
            return

        try:
            url = self._get_webhook_value()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._webhooks[name] = url
        try:
            self._save_webhooks()
        except Exception as e:
            messagebox.showerror("Error", f"Failed saving webhooks.json\n{e}")
            return

        self.channel_select_var.set(name)
        self._refresh_channel_dropdown()
        self.status_var.set(f"Saved channel: {name}")

    def on_delete_channel(self) -> None:
        name = (self.channel_select_var.get() or "").strip()
        if not name:
            messagebox.showerror("Invalid input", "Select a channel to delete.")
            return

        if name not in self._webhooks:
            messagebox.showinfo("Not found", "Selected channel name not found.")
            return

        ok = messagebox.askyesno("Confirm delete", f'Delete saved channel "{name}"?')
        if not ok:
            return

        del self._webhooks[name]
        try:
            self._save_webhooks()
        except Exception as e:
            messagebox.showerror("Error", f"Failed saving webhooks.json\n{e}")
            return

        self.channel_select_var.set("")
        self._refresh_channel_dropdown()
        self.status_var.set(f"Deleted channel: {name}")
    
    def _start_idle_presser_if_enabled(self) -> None:
        if not self.idle_enabled_var.get():
            self._idle_presser = None
            return

        keys = (self.idle_keys_var.get() or "").strip()
        if not keys:
            raise ValueError("Idle keys cannot be empty if idle presser is enabled.")

        try:
            min_s = int(float(self.idle_min_var.get().strip()))
            max_s = int(float(self.idle_max_var.get().strip()))
        except Exception as e:
            raise ValueError("Idle min/max must be numbers (seconds).") from e

        if min_s < 1:
            min_s = 1
        if max_s < min_s:
            max_s = min_s

        if self.bind_window_var.get() and not (self.idle_target_title_var.get() or "").strip():
            raise ValueError("Bind is enabled but no target application is selected.")

        cfg = IdleKeypressConfig(
            keys = keys,
            min_seconds = min_s,
            max_seconds = max_s,
            bind_to_target = bool(self.bind_window_var.get()),
            target_title = (self.idle_target_title_var.get() or "").strip(),
            force_focus = bool(self.idle_force_focus_var.get()),
        )

        self._idle_presser = IdleKeyPresser(cfg, self._capture_in_progress)
        self._idle_presser.start()

    def _stop_idle_presser(self) -> None:
        if self._idle_presser:
            self._idle_presser.stop()
            self._idle_presser = None

    def _refresh_window_list(self) -> None:
        self._window_titles = list_window_titles()

        if hasattr(self, "window_combo"):
            self.window_combo["values"] = self._window_titles

        if not self._window_titles:
            self.status_var.set("No windows detected (or titles are empty).")

    def on_refresh_windows(self) -> None:
        self._refresh_window_list()
        self.status_var.set("Refreshed window list.")

    def on_use_active_window(self) -> None:
        title = get_active_window_title()
        if not title:
            messagebox.showerror("Error", "Could not detect active window title.")
            return

        self.window_select_var.set(title)
        self.idle_target_title_var.set(title)
        self.status_var.set("Set target to active window.")

    def on_window_selected(self, _event: object = None) -> None:
        title = (self.window_select_var.get() or "").strip()
        if not title:
            return

        self.idle_target_title_var.set(title)
        self.status_var.set("Selected target window.")

    def _set_window_picker_enabled(self) -> None:
        enabled = bool(self.bind_window_var.get())

        state = "readonly" if enabled else "disabled"
        if hasattr(self, "window_combo"):
            self.window_combo.config(state = state)

        if hasattr(self, "btn_refresh_windows"):
            self.btn_refresh_windows.config(state = "normal" if enabled else "disabled")

        if hasattr(self, "btn_use_active_window"):
            self.btn_use_active_window.config(state = "normal" if enabled else "disabled")



    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self)
        cast(Any, frm).grid(row = 0, column = 0, **pad)

        r = 0

        channel_row = ttk.Frame(frm)
        channel_row.grid(row = r, column = 1, sticky = "w", pady = (4, 0))

        r += 1

        ttk.Label(channel_row, text = "Channel:").grid(row = 0, column = 0, sticky = "w")

        self.channel_combo = ttk.Combobox(
            channel_row,
            textvariable = self.channel_select_var,
            state = "readonly",
            width = 24,
        )
        self.channel_combo.grid(row = 0, column = 1, sticky = "w", padx = (6, 8))
        self.channel_combo.bind("<<ComboboxSelected>>", self.on_select_channel)

        ttk.Button(channel_row, text = "Delete", command = self.on_delete_channel).grid(
            row = 0, column = 2, sticky = "w", padx = (0, 8)
        )

        ttk.Label(channel_row, text = "Save as:").grid(row = 0, column = 3, sticky = "w")
        ttk.Entry(channel_row, textvariable = self.channel_name_var, width = 18).grid(
            row = 0, column = 4, sticky = "w", padx = (6, 8)
        )
        ttk.Button(channel_row, text = "Save/Update", command = self.on_save_channel).grid(
            row = 0, column = 5, sticky = "w"
        )

        self._refresh_channel_dropdown()

        r += 2

        ttk.Label(frm, text = "Discord Webhook URL:").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.webhook_var, width = 64).grid(row = r, column = 1, sticky = "w")


        btn_row = ttk.Frame(frm)
        btn_row.grid(row = r + 1, column = 1, sticky = "w", pady = (4, 0))

        ttk.Button(btn_row, text = "Set for this app", command = self.on_set_env_current_app).grid(
            row = 0, column = 0, padx = (0, 8)
        )
        ttk.Button(btn_row, text = "Persist (setx)", command = self.on_persist_env_setx).grid(
            row = 0, column = 1, padx = (0, 8)
        )
        ttk.Button(btn_row, text = "Load from env", command = self.on_load_webhook_from_env).grid(
            row = 0, column = 2
        )

        r += 2

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

        ttk.Label(frm, text = "Loop interval (minutes):").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.interval_var, width = 10).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Label(frm, text = "Discord message (optional):").grid(row = r, column = 0, sticky = "w")
        ttk.Entry(frm, textvariable = self.message_var, width = 64).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Label(frm, text="Idle key presser:").grid(row = r, column = 0, sticky = "w")

        idle_row1 = ttk.Frame(frm)
        idle_row1.grid(row = r, column = 1, sticky = "w")

        ttk.Checkbutton(
            idle_row1,
            text = "Enable random keypress between captures",
            variable = self.idle_enabled_var,
        ).grid(row = 0, column = 0, sticky = "w")

        r += 1

        idle_row2 = ttk.Frame(frm)
        idle_row2.grid(row = r, column = 1, sticky = "w")

        ttk.Label(idle_row2, text = "Keys:").grid(row = 0, column = 0, sticky = "w")
        ttk.Entry(idle_row2, textvariable = self.idle_keys_var, width = 12).grid(row = 0, column = 1, padx = (6, 12))

        ttk.Label(idle_row2, text = "Min sec:").grid(row = 0, column = 2, sticky = "w")
        ttk.Entry(idle_row2, textvariable = self.idle_min_var, width = 6).grid(row = 0, column = 3, padx = (6, 12))

        ttk.Label(idle_row2, text = "Max sec:").grid(row = 0, column = 4, sticky = "w")
        ttk.Entry(idle_row2, textvariable = self.idle_max_var, width = 6).grid(row = 0, column = 5, padx = (6, 0))

        r += 1

        ttk.Checkbutton(frm, text = "Bind keypresses to selected application", variable = self.bind_window_var, command = self._set_window_picker_enabled).grid(row = r, column = 1, sticky = "w")
        r += 1

        ttk.Label(idle_row2, text = "Target title contains:").grid(row = 1, column = 0, sticky = "w", pady = (6, 0))
        ttk.Entry(idle_row2, textvariable = self.idle_target_title_var, width = 24).grid(row = 1, column = 1, padx = (6, 12), pady = (6, 0))

        ttk.Checkbutton(
            idle_row2,
            text = "Force focus",
            variable = self.idle_force_focus_var
        ).grid(row = 1, column = 2, columnspan = 2, sticky = "w", pady = (6, 0))
        r += 1

        ttk.Label(frm, text="Select application:").grid(row = r, column = 0, sticky = "w")

        win_row = ttk.Frame(frm)
        win_row.grid(row = r, column = 1, sticky="w")

        self.window_combo = ttk.Combobox(
            win_row,
            textvariable = self.window_select_var,
            state = "readonly",
            width = 52,
        )
        self.window_combo.grid(row = 0, column = 0, padx = (0, 8))
        self.window_combo.bind("<<ComboboxSelected>>", self.on_window_selected)

        self.btn_refresh_windows = ttk.Button(win_row, text = "Refresh", command = self.on_refresh_windows)
        self.btn_refresh_windows.grid(row = 0, column = 1, padx = (0, 8))

        self.btn_use_active_window = ttk.Button(win_row, text = "Use active", command = self.on_use_active_window)
        self.btn_use_active_window.grid(row = 0, column = 2)

        r += 1

        self._refresh_window_list()
        self._set_window_picker_enabled()

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
                self._capture_in_progress.set()
                try:
                    run_once(params)
                finally:
                    self._capture_in_progress.clear()
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
            interval_m = float(self.interval_var.get().strip())
            interval_s = interval_m * 60.0
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        if interval_m <= 0:
            messagebox.showerror("Invalid input", "Interval must be > 0 to start loop.")
            return

        self._stop_event.clear()
        self._set_running_ui(True)
        self.status_var.set("Loop running...")

        try:
            self._start_idle_presser_if_enabled()
        except Exception as e:
            self._set_running_ui(False)
            messagebox.showerror("Invalid idle key presser settings", str(e))
            return

        def loop_worker():
            while not self._stop_event.is_set():
                try:
                    self._capture_in_progress.set()
                    try:
                        run_once(params)
                    finally:
                        self._capture_in_progress.clear()
                    self.after(0, lambda: self.status_var.set("Loop running (last post ok)."))
                except Exception as e:
                    self.after(0, lambda: self.status_var.set("Loop running (last post error)."))
                    self.after(0, lambda: messagebox.showerror("Error", str(e)))

                if self._stop_event.wait(timeout = interval_s):
                    break

            self._stop_idle_presser()
            self.after(0, lambda: self._set_running_ui(False))
            self.after(0, lambda: self.status_var.set("Stopped."))

        self._thread = threading.Thread(target = loop_worker, daemon = True)
        self._thread.start()

    def on_stop_loop(self) -> None:
        self._stop_event.set()
        self._stop_idle_presser()
        self.status_var.set("Stopping...")

    def on_close(self) -> None:
        self._stop_event.set()
        self._stop_idle_presser()
        self.destroy()
