"""GUI building-block widgets: tooltip, help button, log handler, log textbox, scrolling frame.

The log handler / textbox pair uses a bounded `deque` and a periodic Tk drain
timer instead of marshaling each record with `after(0, ...)`. Under heavy
DEBUG traffic the per-record approach floods the Tk event queue and freezes
the UI; draining in 50 ms batches keeps the UI responsive regardless of log
rate.
"""
from __future__ import annotations

import logging
import tkinter as tk
from collections import deque
from tkinter import ttk

import customtkinter as ctk


# ---- Small helpers -------------------------------------------------------
def safe_after_cancel(widget: tk.Misc, after_id: str | None) -> None:
    """`after_cancel` that tolerates a destroyed widget / unknown ID.

    Tk raises `TclError` if the widget has already been destroyed; we don't
    care about that case in any caller (we always cancel during teardown).
    """
    if after_id is None:
        return
    try:
        widget.after_cancel(after_id)
    except tk.TclError:
        pass


def safe_destroy(widget: tk.Misc | None) -> None:
    if widget is None:
        return
    try:
        widget.destroy()
    except tk.TclError:
        pass


# ---- Scrolling frame -----------------------------------------------------
class ScrollingFrame(tk.Frame):
    """Vertical scrollable container — a lighter alternative to `CTkScrollableFrame`.

    Provides an `interior` Frame that callers pack widgets into. The interior
    expands to the canvas width and scrolls vertically when its natural height
    exceeds the visible area. Mouse-wheel scroll is bound while the cursor is
    over the canvas.

    Used in place of CTkScrollableFrame for the Settings tab because the
    latter re-renders its CTk-themed background through PIL on every Configure
    event, which made window resizes laggy.
    """

    SCROLL_UNITS_PER_TICK = 3
    BG = "#2b2b2b"

    def __init__(self, master: tk.Misc, **kwargs):
        super().__init__(master, bg=self.BG, **kwargs)
        self._canvas = tk.Canvas(
            self, bg=self.BG, highlightthickness=0, bd=0, takefocus=False,
        )
        self._scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self._canvas.yview,
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.interior = tk.Frame(self._canvas, bg=self.BG)
        self._interior_id = self._canvas.create_window(
            (0, 0), window=self.interior, anchor="nw",
        )

        # Keep the scroll region in sync with the interior's natural size.
        self.interior.bind("<Configure>", self._on_interior_configure)
        # Make the interior always fill the canvas width.
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # Wheel scroll when the cursor is over the canvas.
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)

    def _on_interior_configure(self, _event: object) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        # Stretch the interior to the full canvas width so child widgets
        # using `fill="x"` actually fill.
        self._canvas.itemconfigure(self._interior_id, width=event.width)

    def _bind_wheel(self, _event: object) -> None:
        # On Windows + macOS the wheel event delivers <MouseWheel>;
        # on Linux it's <Button-4> / <Button-5>.
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind_all("<Button-4>", self._on_mousewheel_linux_up)
        self._canvas.bind_all("<Button-5>", self._on_mousewheel_linux_down)

    def _unbind_wheel(self, _event: object) -> None:
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        # Windows reports delta in multiples of 120; mac in single units.
        step = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(step * self.SCROLL_UNITS_PER_TICK, "units")

    def _on_mousewheel_linux_up(self, _event: object) -> None:
        self._canvas.yview_scroll(-self.SCROLL_UNITS_PER_TICK, "units")

    def _on_mousewheel_linux_down(self, _event: object) -> None:
        self._canvas.yview_scroll(self.SCROLL_UNITS_PER_TICK, "units")


# ---- Help button ---------------------------------------------------------
class HelpButton(tk.Canvas):
    """A small `?` icon that shows a hover tooltip and a click-modal.

    Both routes show the same `help_text`, so callers maintain one string per
    setting. The click-modal is useful when the user wants to *read* the help
    without it vanishing the moment they move the mouse away.

    Implemented as a `tk.Canvas` with statically-drawn circle + glyph rather
    than a `CTkLabel` with `corner_radius`: CTk re-renders the rounded
    background through PIL on every Configure event, which made window
    resizes laggy when ~36 of these were on screen.
    """

    DIAMETER = 22
    FILL = "#4a4a4a"
    FILL_HOVER = "#5d5d5d"
    FG = "#f0f0f0"

    def __init__(self, master: tk.Misc, help_text: str, *, title: str = "What this does"):
        # Match the parent's background so the canvas vanishes into the row.
        # CTk widgets reject `cget("bg")` with ValueError; tk widgets give
        # TclError if no `bg` is set. Either way, fall back to a known
        # CTk-dark-theme color so the canvas blends in without a halo.
        try:
            parent_bg = master.cget("bg")
        except (tk.TclError, ValueError):
            parent_bg = "#2b2b2b"
        super().__init__(
            master,
            width=self.DIAMETER,
            height=self.DIAMETER,
            highlightthickness=0,
            bd=0,
            bg=parent_bg,
            cursor="hand2",
        )
        # Static items — no Configure-driven redraw, just two canvas objects.
        pad = 2
        self._circle = self.create_oval(
            pad, pad, self.DIAMETER - pad, self.DIAMETER - pad,
            fill=self.FILL, outline="",
        )
        self.create_text(
            self.DIAMETER // 2, self.DIAMETER // 2,
            text="?", fill=self.FG, font=("TkDefaultFont", 9, "bold"),
        )
        self._help_text = help_text
        self._title = title
        Tooltip(self, help_text)
        self.bind("<Button-1>", self._open_modal, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    def _on_enter(self, _event: object = None) -> None:
        self.itemconfig(self._circle, fill=self.FILL_HOVER)

    def _on_leave(self, _event: object = None) -> None:
        self.itemconfig(self._circle, fill=self.FILL)

    def _open_modal(self, _event: object = None) -> None:
        HelpDialog(self.winfo_toplevel(), self._title, self._help_text)


class HelpDialog(tk.Toplevel):
    """Modal-style help popup. Centered on the parent, dismissable with OK/Esc."""

    PAD = 18
    WRAP_PX = 460

    def __init__(self, parent: tk.Misc, title: str, text: str):
        super().__init__(parent)
        self.title(title)
        # `transient` expects a `Wm` (toplevel) — narrow if we can.
        toplevel = parent.winfo_toplevel() if hasattr(parent, "winfo_toplevel") else parent
        if isinstance(toplevel, (tk.Tk, tk.Toplevel)):
            self.transient(toplevel)
        self.resizable(False, False)
        self.configure(bg="#1f1f24")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(
            self,
            text=text,
            wraplength=self.WRAP_PX,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=12),
        ).pack(padx=self.PAD, pady=(self.PAD, 8), fill="x")

        ctk.CTkButton(
            self, text="OK", width=80, command=self.destroy,
        ).pack(pady=(0, self.PAD))

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.destroy())
        self._center_over_parent(parent)
        self.grab_set()
        self.focus_set()

    def _center_over_parent(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"+{x}+{y}")


# ---- Tooltip -------------------------------------------------------------
class Tooltip:
    """Hover tooltip for any Tk widget.

    Uses a borderless `tk.Toplevel` rather than a CustomTkinter widget so the
    tooltip renders cleanly on top of every platform's window manager without
    inheriting the CTk theme padding.
    """

    SHOW_DELAY_MS = 450
    WRAP_PX = 420
    BG = "#2b2b2b"
    FG = "#f4f4f4"

    def __init__(self, widget: tk.Misc, text: str, delay_ms: int | None = None):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms if delay_ms is not None else self.SHOW_DELAY_MS
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def update_text(self, text: str) -> None:
        self.text = text

    def _schedule(self, _event: object = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self, _event: object = None) -> None:
        safe_after_cancel(self.widget, self._after_id)
        self._after_id = None
        safe_destroy(self._tip)
        self._tip = None

    def _show(self) -> None:
        if self._tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            tip = tk.Toplevel(self.widget)
        except tk.TclError:
            return
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tip.attributes("-topmost", True)
        tk.Label(
            tip,
            text=self.text,
            background=self.BG,
            foreground=self.FG,
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            wraplength=self.WRAP_PX,
            justify="left",
            font=("TkTooltipFont",),
        ).pack()
        self._tip = tip


# ---- Logging -------------------------------------------------------------
class LogHandler(logging.Handler):
    """Thread-safe `logging.Handler` that appends formatted records to a deque.

    The deque is drained on the Tk main thread by `LogTextbox`. The deque is
    bounded (caller-provided `maxlen`) so memory cannot grow without limit no
    matter the log rate.
    """

    def __init__(self, sink: deque):
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.sink.append(self.format(record))
        except Exception:
            # Logging must never raise; swallow formatting/append errors.
            pass


class LogTextbox(ctk.CTkTextbox):
    """`CTkTextbox` that drains a thread-safe queue every `DRAIN_INTERVAL_MS`.

    Wire it up once at startup:

        log_box = LogTextbox(parent, max_lines=2000)
        log_box.pack(...)
        handler = log_box.attach_handler()
        logging.getLogger().addHandler(handler)
        log_box.start()

    Call `stop()` and remove the handler during teardown — in that order, so
    the handler cannot append to a deque that's about to be GC'd while the
    drain timer is still alive.
    """

    DRAIN_INTERVAL_MS = 50
    DRAIN_BATCH_MAX = 500

    def __init__(self, master: tk.Misc, max_lines: int = 2000, **kwargs: object):
        super().__init__(master, wrap="word", **kwargs)
        self.configure(state="disabled")
        self.max_lines = max_lines
        # Cap queue at ~2x max_lines so an unreachable drain (e.g. during
        # shutdown) cannot grow memory unboundedly.
        self._queue: deque[str] = deque(maxlen=max_lines * 2)
        self._paused = False
        self._drain_id: str | None = None

    def attach_handler(self, fmt: str = "%(asctime)s %(message)s",
                       datefmt: str = "%H:%M:%S") -> LogHandler:
        h = LogHandler(self._queue)
        h.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        return h

    def start(self) -> None:
        if self._drain_id is None:
            self._drain_id = self.after(self.DRAIN_INTERVAL_MS, self._drain)

    def stop(self) -> None:
        safe_after_cancel(self, self._drain_id)
        self._drain_id = None

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def clear(self) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")

    def _drain(self) -> None:
        try:
            if not self._paused and self._queue:
                self._flush_pending()
        except tk.TclError:
            # Widget destroyed mid-drain; stop rearming.
            self._drain_id = None
            return
        self._drain_id = self.after(self.DRAIN_INTERVAL_MS, self._drain)

    def _flush_pending(self) -> None:
        lines: list[str] = []
        for _ in range(self.DRAIN_BATCH_MAX):
            if not self._queue:
                break
            lines.append(self._queue.popleft())
        if not lines:
            return
        self.configure(state="normal")
        self.insert("end", "\n".join(lines) + "\n")
        line_count = int(self.index("end-1c").split(".")[0])
        if line_count > self.max_lines:
            self.delete("1.0", f"{line_count - self.max_lines + 1}.0")
        self.see("end")
        self.configure(state="disabled")
