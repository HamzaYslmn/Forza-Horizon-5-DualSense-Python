"""Shared fixtures.

Tests run from `src/`, so the `modules` package is already importable.

`tk_root` boots a hidden `CTk` root for tests that need a parent widget.
It's function-scoped on purpose: Tkinter wants exactly one root per process,
so we create + destroy per-test to avoid colliding with tests (like the GUI
smoke tests) that construct their own root.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _have_display() -> bool:
    """True if a display is available for Tk to render into."""
    if os.name == "nt":
        return True  # Windows always has a display surface
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@pytest.fixture
def display_required():
    """Skip the test if no display is available — for tests that build their own root."""
    if not _have_display():
        pytest.skip("No display available (set DISPLAY for headless GUI tests)")


@pytest.fixture
def tk_root(display_required):
    """Provide a hidden CTk root for tests that need a parent widget."""
    import customtkinter as ctk  # noqa: PLC0415

    root = ctk.CTk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass
