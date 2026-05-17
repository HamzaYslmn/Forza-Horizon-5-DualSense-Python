"""GUI smoke test — construct/destroy + live-mutation against one Tk root.

Tkinter strongly prefers one Tk root per process, so this file runs ONE
consolidated test that builds a TriggerGUI and exercises every wiring path
(construction, switch toggle, entry change, reset) against that single root.
Each assertion has a descriptive label in the failure message so the test
still pinpoints which step broke.

A separate `test_gui_lifecycle.py` covers shutdown / mainloop paths in
isolation — pytest invocations are separate, so each gets its own root.

The whole module is skipped without a display.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from modules.settings import Settings


@pytest.mark.gui
def test_full_gui_flow(tmp_path, monkeypatch, display_required):
    """One test, one GUI, many assertions."""
    # Redirect preferences.PATH into tmp_path so we don't disturb the user's file
    import modules.preferences as preferences
    monkeypatch.setattr(preferences, "PATH", tmp_path / "user_preferences.json")

    s = Settings()

    from modules.gui import TriggerGUI
    from modules.gui.widgets import HelpButton

    gui = TriggerGUI(s)
    try:
        # Pump the event loop so widgets render
        _pump(gui, ticks=5)

        # ---- Construction --------------------------------------------------
        # 7 toggle switches (4 brake + 3 throttle), 28 numeric entries
        assert len(gui._switch_vars) == 7, "expected 7 toggle switches"
        assert len(gui._entry_vars) == 28, "expected 28 numeric entries"

        # One HelpButton per control
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
        assert gui.settings.enable_abs is False
        # preferences.save was called — file should now exist
        prefs_path = Path(preferences.PATH)
        assert prefs_path.exists(), "preferences file should be written on toggle"
        data = json.loads(prefs_path.read_text())
        assert data["enable_abs"] is False

        # ---- Entry change persistence -------------------------------------
        gui._entry_vars["brake_max_force"].set("99")
        gui._on_entry_changed("brake_max_force")
        assert gui.settings.brake_max_force == 99

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

        # ---- Reset restores dataclass defaults ----------------------------
        gui._on_reset()
        assert gui.settings.brake_max_force == 60
        assert gui._entry_vars["brake_max_force"].get() == "60"
        assert gui.settings.enable_abs is True
    finally:
        gui._on_close()


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
