"""TriggerGUI — CustomTkinter window, three tabs (Controls / Settings / Logs).

Composition (not inheritance):

- `BackendController`   owns DualSense / UDP listener / loop thread.
- `LogTextbox`          owns the log widget, drain timer, and ring buffer.
- `build_*_tab`         own the per-tab widget construction.

TriggerGUI itself only does what's left:

- builds the chrome (top bar / bottom bar / tabs / keybindings),
- wires the log handler in/out,
- relays UI events to the backend,
- manages the window lifecycle and shutdown order.

The shutdown order matters and matches the old TUI:
  detach log handler → stop log drain → stop backend (sets stop_event,
  joins thread, closes HID) → destroy window.
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from modules import preferences
from modules.gui.backend import BackendController
from modules.gui.labels import STARTUP_HINT
from modules.gui.tabs import build_controls_tab, build_settings_tab, coerce_clamp
from modules.gui.widgets import LogHandler, LogTextbox, safe_after_cancel, safe_destroy
from modules.preferences import _version
from modules.settings import Settings
from modules.update_check import log_latest_commit_age

log = logging.getLogger("fhds")

LOG_LEVELS = ("WARNING", "INFO", "DEBUG")
DEFAULT_LOG_LEVEL = "INFO"

STATUS_REFRESH_MS = 1000
BACKEND_START_DELAY_MS = 50

WINDOW_TITLE = "FH DualSense"
# Base geometry in "logical" 96-DPI pixels — `_apply_geometry` scales these
# for the active monitor's DPI and clamps to fit on small screens.
BASE_WIDTH = 820
BASE_HEIGHT = 680
BASE_MIN_WIDTH = 720
BASE_MIN_HEIGHT = 560
SCREEN_FIT_FRACTION = 0.9   # never exceed this much of screen on either axis

# Tk widget classes that should "absorb" the single-letter shortcuts so the
# user can type q/p/l/c inside an entry without quitting the app.
_TEXT_INPUT_CLASSES = ("Entry", "Text", "TEntry", "TCombobox")


class TriggerGUI:
    """Top-level window. One instance per process; call `run()` once."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = BackendController(settings)
        self.backend.on_loop_exit = self._on_loop_exit

        self._paused = False
        self._level_idx = LOG_LEVELS.index(DEFAULT_LOG_LEVEL)
        self._log_handler: LogHandler | None = None
        self._status_timer: str | None = None
        self._teardown_done = False

        # Tk variables backing each input — passed to the reset action so it
        # can refresh every widget after `preferences.reset()`.
        self._switch_vars: dict[str, tk.BooleanVar] = {}
        self._entry_vars: dict[str, tk.StringVar] = {}

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.title(WINDOW_TITLE)
        self._apply_geometry()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

    # MARK: Geometry ----------------------------------------------------------
    def _apply_geometry(self) -> None:
        """Pick a DPI-scaled window size that fits on the active monitor."""
        scale = self._effective_dpi_scale()
        screen_w = max(self.root.winfo_screenwidth(), 1)
        screen_h = max(self.root.winfo_screenheight(), 1)
        max_w = int(screen_w * SCREEN_FIT_FRACTION)
        max_h = int(screen_h * SCREEN_FIT_FRACTION)
        w = min(int(BASE_WIDTH * scale), max_w)
        h = min(int(BASE_HEIGHT * scale), max_h)
        min_w = min(int(BASE_MIN_WIDTH * scale), max_w)
        min_h = min(int(BASE_MIN_HEIGHT * scale), max_h)
        x = max(0, (screen_w - w) // 2)
        y = max(0, (screen_h - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min_w, min_h)

    def _effective_dpi_scale(self) -> float:
        """Combine CTk's window-scaling factor with Tk's `tk scaling` value.

        CTk's tracker is the best signal on Windows (it consults the OS DPI
        awareness API). On Linux it often returns 1.0 even on HiDPI displays,
        so we also consult `tk scaling` (1.33 ≈ 96 DPI, 2.66 ≈ 192 DPI) and
        take the larger of the two as a conservative upscale factor.
        """
        try:
            from customtkinter.windows.widgets.scaling.scaling_tracker import (
                ScalingTracker,
            )
            ctk_scale = ScalingTracker.get_window_scaling(self.root)
        except Exception:
            ctk_scale = 1.0
        try:
            tk_scale = float(self.root.tk.call("tk", "scaling")) / 1.3333
        except (tk.TclError, ValueError):
            tk_scale = 1.0
        return max(1.0, ctk_scale, tk_scale)

    # MARK: Public entry point ------------------------------------------------
    def run(self) -> None:
        # Schedule startup AFTER mainloop() begins so the UI paints before the
        # (potentially slow) HID open / UDP bind on cold start.
        self.root.after(0, self._on_start)
        try:
            self.root.mainloop()
        finally:
            # Belt-and-braces for cases where mainloop exits via a path that
            # didn't go through WM_DELETE_WINDOW (Ctrl+C in parent terminal,
            # uncaught exception inside Tk).
            self._teardown()

    # MARK: Startup -----------------------------------------------------------
    def _on_start(self) -> None:
        self._attach_log_handler()
        self._refresh_status()
        self._status_timer = self.root.after(STATUS_REFRESH_MS, self._tick_status)
        log_latest_commit_age()
        log.info("Starting controller and telemetry listener...")
        # Defer the backend by another tick so the first status repaint runs
        # before the HID open call (which can take ~200 ms on a cold connect).
        self.root.after(BACKEND_START_DELAY_MS, self._start_backend)

    def _start_backend(self) -> None:
        if not self.backend.start():
            err = self.backend.startup_error
            self.status_label.configure(text=f"Backend failed: {err}")

    def _attach_log_handler(self) -> None:
        root = logging.getLogger()
        root.handlers.clear()
        handler = self.log_box.attach_handler()
        root.addHandler(handler)
        root.setLevel(self._current_level())
        self._log_handler = handler
        self.log_box.start()

    # MARK: Shutdown ----------------------------------------------------------
    def _on_close(self) -> None:
        self._teardown()
        safe_destroy(self.root)

    def _on_loop_exit(self) -> None:
        """Backend exited on its own (game closed, telemetry-lost). Close the
        window from the UI thread so destroy runs in the right place."""
        try:
            self.root.after(0, self._on_close)
        except (RuntimeError, tk.TclError):
            pass

    def _teardown(self) -> None:
        # Order: cancel UI timers → detach log handler → drain → stop backend.
        # Detaching the handler before the backend stops means shutdown log
        # records from the backend hit a no-op deque instead of a destroyed
        # widget.
        if self._teardown_done:
            return
        self._teardown_done = True
        safe_after_cancel(self.root, self._status_timer)
        self._status_timer = None
        self._detach_log_handler()
        try:
            self.log_box.stop()
        except (tk.TclError, AttributeError):
            pass
        self.backend.stop()

    def _detach_log_handler(self) -> None:
        if self._log_handler is None:
            return
        logging.getLogger().removeHandler(self._log_handler)
        self._log_handler = None

    # MARK: UI construction ---------------------------------------------------
    def _build_ui(self) -> None:
        self._build_top_bar()
        self._build_tabs()
        self._build_bottom_bar()
        self._bind_shortcuts()

    def _build_top_bar(self) -> None:
        bar = ctk.CTkFrame(self.root, height=32, corner_radius=0)
        bar.pack(side="top", fill="x")
        self.status_label = ctk.CTkLabel(bar, text="", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True, padx=12, pady=4)
        ctk.CTkLabel(
            bar, text=f"v{_version() or '?'}",
            anchor="e", text_color="gray70",
        ).pack(side="right", padx=12, pady=4)

    def _build_bottom_bar(self) -> None:
        bar = ctk.CTkFrame(self.root, height=40, corner_radius=0)
        bar.pack(side="bottom", fill="x")
        ctk.CTkButton(bar, text="Quit  (Q)", width=90,
                      command=self._on_close).pack(side="right", padx=4, pady=4)
        self.pause_btn = ctk.CTkButton(
            bar, text=self._pause_btn_text(), width=140,
            command=self._toggle_pause,
        )
        self.pause_btn.pack(side="right", padx=4, pady=4)
        self.level_btn = ctk.CTkButton(
            bar, text=self._level_btn_text(), width=150,
            command=self._cycle_level,
        )
        self.level_btn.pack(side="right", padx=4, pady=4)
        ctk.CTkButton(bar, text="Clear Logs  (C)", width=130,
                      command=self._clear_logs).pack(side="right", padx=4, pady=4)

    def _build_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=4)
        self.tabs.add("Controls")
        self.tabs.add("Settings")
        self.tabs.add("Logs")

        self._switch_vars = build_controls_tab(
            self.tabs.tab("Controls"), self.settings,
            on_toggle=self._on_switch_toggled,
        )
        self._entry_vars = build_settings_tab(
            self.tabs.tab("Settings"), self.settings,
            on_change=self._on_entry_changed, on_reset=self._on_reset,
        )
        self.log_box = LogTextbox(self.tabs.tab("Logs"), max_lines=2000)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)

    def _bind_shortcuts(self) -> None:
        # Bind to the root and consult focus_get() so single-letter shortcuts
        # don't fire while the user is typing into an entry.
        self.root.bind("<Key-q>", lambda _e: self._shortcut(self._on_close))
        self.root.bind("<Key-p>", lambda _e: self._shortcut(self._toggle_pause))
        self.root.bind("<Key-l>", lambda _e: self._shortcut(self._cycle_level))
        self.root.bind("<Key-c>", lambda _e: self._shortcut(self._clear_logs))

    def _shortcut(self, action: Callable[[], None]) -> str | None:
        """Run `action` unless the focused widget is a text input."""
        focus = self.root.focus_get()
        if focus is not None and focus.winfo_class() in _TEXT_INPUT_CLASSES:
            return None
        action()
        return "break"

    # MARK: Status bar --------------------------------------------------------
    def _tick_status(self) -> None:
        self._refresh_status()
        try:
            self._status_timer = self.root.after(STATUS_REFRESH_MS, self._tick_status)
        except tk.TclError:
            self._status_timer = None

    def _refresh_status(self) -> None:
        connected = self.backend.is_connected
        state = "DualSense: connected" if connected else "DualSense: waiting"
        level = f"Logs: {LOG_LEVELS[self._level_idx]}"
        paused = "PAUSED" if self._paused else "live"
        if connected:
            text = f"  •  {state}  •  {level}  •  {paused}"
        else:
            hint = STARTUP_HINT.format(host=self.settings.udp_host,
                                       port=self.settings.udp_port)
            text = f"{state}  •  {level}  •  {paused}     {hint}"
        try:
            self.status_label.configure(text=text)
        except tk.TclError:
            pass

    # MARK: Actions -----------------------------------------------------------
    def _current_level(self) -> int:
        return getattr(logging, LOG_LEVELS[self._level_idx])

    def _pause_btn_text(self) -> str:
        return "Resume Logs  (P)" if self._paused else "Pause Logs  (P)"

    def _level_btn_text(self) -> str:
        return f"Level: {LOG_LEVELS[self._level_idx]}  (L)"

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.log_box.set_paused(self._paused)
        self.pause_btn.configure(text=self._pause_btn_text())
        self._refresh_status()

    def _cycle_level(self) -> None:
        self._level_idx = (self._level_idx + 1) % len(LOG_LEVELS)
        logging.getLogger().setLevel(self._current_level())
        self.level_btn.configure(text=self._level_btn_text())
        self._refresh_status()
        log.info("Log level: %s", LOG_LEVELS[self._level_idx])

    def _clear_logs(self) -> None:
        self.log_box.clear()

    def _on_switch_toggled(self, attr: str, value: bool) -> None:
        if not hasattr(self.settings, attr):
            return
        setattr(self.settings, attr, value)
        preferences.save(self.settings)
        self.backend.confirm_toggle(value)

    def _on_entry_changed(self, attr: str) -> None:
        if not hasattr(self.settings, attr):
            return
        var = self._entry_vars.get(attr)
        if var is None:
            return
        current = getattr(self.settings, attr)
        new = coerce_clamp(attr, current, var.get())
        if new is None:
            var.set(str(current))  # revert on parse error
            return
        if str(new) != var.get():
            var.set(str(new))  # display the clamped value
        if new == current:
            return
        setattr(self.settings, attr, new)
        preferences.save(self.settings)
        log.info("%s = %s", attr, new)

    def _on_reset(self) -> None:
        preferences.reset(self.settings)
        self._refresh_input_widgets()
        log.info("Settings reset to defaults.")

    def _refresh_input_widgets(self) -> None:
        """Re-sync every switch and entry from the current `self.settings`."""
        for attr, sw_var in self._switch_vars.items():
            if hasattr(self.settings, attr):
                sw_var.set(bool(getattr(self.settings, attr)))
        for attr, entry_var in self._entry_vars.items():
            if hasattr(self.settings, attr):
                entry_var.set(str(getattr(self.settings, attr)))
