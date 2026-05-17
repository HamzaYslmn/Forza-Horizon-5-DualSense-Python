"""System-tray icon (pystray + Pillow).

Tray behavior is best-effort, never required. On Linux this depends on an
AppIndicator-compatible status notifier (GNOME extension, KDE Plasma's built-
in, XFCE/MATE/Cinnamon tray), which the user may not have. If initialization
fails, `start()` returns False and the rest of the GUI is unaffected: the
window's close button just closes the app instead of hiding it.

Pystray menu callbacks fire on its own thread, so every action is marshaled
back to the Tk thread via the `marshal` callable injected at construction.
That keeps the contract clean: callbacks injected here never touch Tk
directly, they just say "I want this action to happen", and the host runs it
on its event loop.
"""
from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Callable

from PIL import Image, ImageDraw
import pystray

log = logging.getLogger("fhds")


class Status(str, Enum):
    """Color-coded tray-icon states the host sets via `set_status`."""
    WAITING = "waiting"            # no DualSense / no telemetry — yellow
    RUNNING = "running"            # connected and triggers active — green
    PAUSED = "paused"              # effects manually paused — gray
    ERROR = "error"                # backend failed — red


_STATUS_COLORS: dict[Status, tuple[int, int, int]] = {
    Status.WAITING: (235, 195, 55),
    Status.RUNNING: (95, 200, 110),
    Status.PAUSED: (160, 160, 160),
    Status.ERROR: (210, 80, 80),
}

ICON_SIZE = 64
ICON_BG = (28, 28, 32, 255)
ICON_FG_BORDER = (240, 240, 240, 255)


class TrayController:
    """Lifecycle-managed wrapper around a `pystray.Icon`.

    All actions you pass in (`on_show`, `on_quit`, `on_toggle_pause`) are
    routed through `marshal(action)` so the host gets to run them on the Tk
    event loop — no host code ever runs on pystray's worker thread.
    """

    def __init__(
        self,
        *,
        marshal: Callable[[Callable[[], None]], None],
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        on_toggle_pause: Callable[[], None],
    ):
        self._marshal = marshal
        self._on_show = on_show
        self._on_quit = on_quit
        self._on_toggle_pause = on_toggle_pause

        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None
        self._status = Status.WAITING
        self._paused = False
        self._started = False
        self._stopped = False

    # MARK: Lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        """Create and start the tray icon in a background thread.

        Returns True on success; False (with a logged warning) if pystray
        can't initialize on this platform / desktop environment.
        """
        if self._started:
            return True
        try:
            self._icon = pystray.Icon(
                "fhds",
                icon=self._render_icon(),
                title=self._tooltip_text(),
                menu=self._build_menu(),
            )
            # `run_detached` doesn't start a thread on all backends; do it
            # ourselves so behavior is uniform across Windows/Linux.
            self._thread = threading.Thread(
                target=self._icon.run, daemon=True, name="fhds-tray",
            )
            self._thread.start()
            self._started = True
            return True
        except Exception as e:
            log.warning("System tray unavailable: %s. Close the window with X to exit.", e)
            self._icon = None
            return False

    def stop(self) -> None:
        """Stop the tray icon and join its thread. Idempotent."""
        if self._stopped:
            return
        self._stopped = True
        icon, thread = self._icon, self._thread
        self._icon = None
        self._thread = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                log.debug("Tray stop raised", exc_info=True)
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    # MARK: External state setters --------------------------------------------
    def set_status(self, status: Status) -> None:
        if status == self._status or self._icon is None:
            return
        self._status = status
        try:
            self._icon.icon = self._render_icon()
            self._icon.title = self._tooltip_text()
        except Exception:
            log.debug("Tray status update failed", exc_info=True)

    def set_paused(self, paused: bool) -> None:
        if paused == self._paused or self._icon is None:
            return
        self._paused = paused
        try:
            # Rebuilding the menu is the only way pystray surfaces a label
            # change on Windows; updating in place is a no-op.
            self._icon.menu = self._build_menu()
            self._icon.update_menu()
        except Exception:
            log.debug("Tray menu update failed", exc_info=True)

    # MARK: Internals ---------------------------------------------------------
    def _build_menu(self) -> pystray.Menu:
        pause_label = "Resume effects" if self._paused else "Pause effects"
        return pystray.Menu(
            pystray.MenuItem("Show window", self._wrap(self._on_show),
                             default=True),
            pystray.MenuItem(pause_label, self._wrap(self._on_toggle_pause)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._wrap(self._on_quit)),
        )

    def _wrap(self, action: Callable[[], None]) -> Callable[[pystray.Icon, pystray.MenuItem], None]:
        """Adapt a 0-arg host action to pystray's `(icon, item)` callback shape
        and route the actual call through the host's event-loop marshal."""
        def _cb(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
            self._marshal(action)
        return _cb

    def _tooltip_text(self) -> str:
        label = {
            Status.WAITING: "waiting for DualSense / telemetry",
            Status.RUNNING: "running",
            Status.PAUSED: "effects paused",
            Status.ERROR: "backend error",
        }[self._status]
        return f"FH DualSense — {label}"

    def _render_icon(self) -> Image.Image:
        """Compose a dark-background icon with a centered colored dot."""
        img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), ICON_BG)
        draw = ImageDraw.Draw(img)
        # Outer square border to make the icon distinct in a busy tray.
        draw.rectangle((0, 0, ICON_SIZE - 1, ICON_SIZE - 1),
                       outline=ICON_FG_BORDER, width=2)
        # Status dot, ~60 % of icon size, centered.
        d = int(ICON_SIZE * 0.6)
        x0 = (ICON_SIZE - d) // 2
        y0 = (ICON_SIZE - d) // 2
        color = _STATUS_COLORS[self._status] + (255,)
        draw.ellipse((x0, y0, x0 + d, y0 + d), fill=color)
        return img
