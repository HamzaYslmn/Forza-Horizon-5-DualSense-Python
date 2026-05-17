"""GUI smoke test — construct/destroy + full live-mutation flow.

Tkinter strongly prefers one Tk root per process, so this file runs ONE
consolidated test that builds a TriggerGUI and exercises every wiring path
(construction, switch toggle, entry change, profile switch, reset) against
that single root. Each assertion has a descriptive label in the failure
message so the test still pinpoints which step broke.

A separate `test_gui_lifecycle.py` covers shutdown / mainloop paths in
isolation — pytest invocations are separate, so each gets its own root.

The whole module is skipped without a display.
"""
from __future__ import annotations

import json
import time

import pytest

from modules.settings import Settings


@pytest.mark.gui
def test_full_gui_flow(isolated_profiles, display_required):
    """One test, one GUI, many assertions."""
    profiles = isolated_profiles["profiles"]
    s = Settings()
    profiles.load_or_migrate(s)

    from modules.gui import TriggerGUI
    from modules.gui.widgets import HelpButton

    gui = TriggerGUI(s)
    try:
        # Pump the event loop so widgets render
        _pump(gui, ticks=5)

        # ---- Construction --------------------------------------------------
        assert len(gui._switch_vars) == 8, "expected 8 toggle switches"
        # Settings tab is lazy-built — entries don't exist until first switch
        assert len(gui._entry_vars) == 0, "Settings tab should be empty before activation"
        assert not gui._settings_built, "Settings should not yet be built"

        # Trigger the lazy build (same as clicking the Settings tab)
        gui._build_settings_tab_content()
        _pump(gui, ticks=3)
        assert gui._settings_built, "Settings should be built after activation"
        assert len(gui._entry_vars) == 28, "expected 28 numeric entries after build"

        # One HelpButton per control (now that Settings is built)
        n_help = _count(gui.root, HelpButton)
        n_controls = len(gui._switch_vars) + len(gui._entry_vars)
        assert n_help == n_controls, (
            f"expected {n_controls} HelpButtons (one per control), got {n_help}"
        )

        # Geometry: DPI-scaled and fits on the active screen
        scale = gui._effective_dpi_scale()
        assert scale >= 1.0
        geom = gui.root.geometry()
        wh, _ = geom.split("+", 1)
        w, h = map(int, wh.split("x"))
        sw, sh = gui.root.winfo_screenwidth(), gui.root.winfo_screenheight()
        assert w <= int(sw * 0.95), f"window width {w} > 95% of screen {sw}"
        assert h <= int(sh * 0.95), f"window height {h} > 95% of screen {sh}"

        # ---- Toggle switch persistence ------------------------------------
        gui._on_switch_toggled("enable_abs", False)
        default_path = isolated_profiles["root"] / "default.json"
        data = json.loads(default_path.read_text())
        assert data["enable_abs"] is False, "switch toggle should hit active profile file"

        # ---- Entry change persistence -------------------------------------
        gui._entry_vars["brake_max_force"].set("99")
        gui._on_entry_changed("brake_max_force")
        assert gui.settings.brake_max_force == 99
        data = json.loads(default_path.read_text())
        assert data["brake_max_force"] == 99

        # Out-of-range gets clamped and the entry widget shows the clamped value
        gui._entry_vars["brake_max_force"].set("9999")
        gui._on_entry_changed("brake_max_force")
        assert gui.settings.brake_max_force == 255
        assert gui._entry_vars["brake_max_force"].get() == "255"

        # Garbage input gets reverted (widget restores to current value)
        gui._entry_vars["brake_max_force"].set("not a number")
        gui._on_entry_changed("brake_max_force")
        assert gui.settings.brake_max_force == 255
        assert gui._entry_vars["brake_max_force"].get() == "255"

        # ---- Profile switching refreshes the widget vars ------------------
        profiles.duplicate("default", "Soft", settings=gui.settings)
        gui.settings.brake_max_force = 30
        profiles.save_active(gui.settings)  # writes to default

        gui._on_profile_changed("Soft")
        # Soft's saved value is 255 (we just changed it before duplicating)
        assert gui._entry_vars["brake_max_force"].get() == "255"

        gui._on_profile_changed("default")
        assert gui._entry_vars["brake_max_force"].get() == "30"

        # ---- Reset restores dataclass defaults and rewrites the profile ---
        gui._on_reset()
        assert gui.settings.brake_max_force == 60
        assert gui._entry_vars["brake_max_force"].get() == "60"
        data = json.loads(default_path.read_text())
        assert data["brake_max_force"] == 60
    finally:
        gui._quit()


# ---- Helpers ------------------------------------------------------------
def _pump(gui, ticks: int = 1, sleep: float = 0.0) -> None:
    for _ in range(ticks):
        gui.root.update_idletasks()
        gui.root.update()
        if sleep:
            time.sleep(sleep)


def _count(widget, klass) -> int:
    n = 1 if isinstance(widget, klass) else 0
    for child in widget.winfo_children():
        n += _count(child, klass)
    return n
