"""Persist enable_* toggle states across runs as a tiny JSON file next to main.py.

Other tunables (forces, curves, deadzones) still live in settings.py — only the
on/off switches are remembered, since those are the things the TUI changes.
"""
import json
import logging
from pathlib import Path

log = logging.getLogger("fh5ds")

PATH = Path(__file__).resolve().parent.parent / "user_preferences.json"


def _toggle_attrs(s) -> list[str]:
    return [k for k in vars(s) if k.startswith("enable_")]


def load(s) -> None:
    if not PATH.exists():
        return
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Could not load preferences (%s): %s", PATH.name, e)
        return
    for k, v in data.items():
        if k in _toggle_attrs(s):
            setattr(s, k, v)


def save(s) -> None:
    data = {k: getattr(s, k) for k in _toggle_attrs(s)}
    try:
        PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("Could not save preferences (%s): %s", PATH.name, e)
