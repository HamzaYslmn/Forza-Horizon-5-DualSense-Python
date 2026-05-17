"""GUI lifecycle test — kept in its own file so it runs in a separate
collection from the main smoke test, avoiding the multi-Tk-root-per-process
limitation. Pytest discovers each test file independently; collecting them
into one process works because each file only creates a single root.
"""
from __future__ import annotations

import time

import pytest

from modules.settings import Settings


@pytest.mark.gui
def test_lifecycle(tmp_path, monkeypatch, display_required):
    """Build → start → schedule quit → mainloop exits → idempotent re-quit."""
    import modules.preferences as preferences
    monkeypatch.setattr(preferences, "PATH", tmp_path / "user_preferences.json")

    s = Settings()
    from modules.gui import TriggerGUI
    gui = TriggerGUI(s)

    gui.root.after(0, gui._on_start)
    gui.root.after(500, gui._on_close)

    start = time.monotonic()
    gui.root.mainloop()
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"mainloop took {elapsed:.2f}s — expected exit within 5s"
    assert gui._teardown_done, "teardown should have run during close"

    # Second close is a no-op
    gui._on_close()
    assert gui._teardown_done
