"""Named tuning presets ("profiles") backed by one JSON file per profile.

Layout (next to main.py):

    profiles/
    ├── index.json        # {"active": "default", "version": "1.2.0"}
    ├── default.json      # Settings field dump
    └── My Tune.json

Each profile file is just a `{field: value}` dump of the simple-typed fields
on `Settings` — no metadata, no per-file version. Adding a new field to
`Settings` is forward-compatible: old profile files just inherit the dataclass
default for the missing key.

Reads/writes are atomic via `os.replace` so a crash mid-save cannot corrupt
the active profile (and copying / sharing a single profile is a single-file
operation).
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from modules import preferences
from modules.preferences import _version

log = logging.getLogger("fhds")

ROOT = Path(__file__).resolve().parent.parent / "profiles"
INDEX_PATH = ROOT / "index.json"
LEGACY_PREFERENCES = preferences.PATH
LEGACY_BACKUP = LEGACY_PREFERENCES.with_suffix(LEGACY_PREFERENCES.suffix + ".bak")

DEFAULT_NAME = "default"
MAX_NAME_LEN = 64

# Refuse names that would be unsafe as filenames on Windows or POSIX.
_INVALID_CHARS = re.compile(r"""[\x00-\x1f/\\:*?"<>|]""")
_WIN_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

_SIMPLE = (bool, int, float, str)


# ---- Naming + paths ------------------------------------------------------
class InvalidProfileName(ValueError):
    """Raised when a profile name fails validation."""


def _validate_name(name: str) -> str:
    """Return the cleaned name or raise `InvalidProfileName`.

    Centralizes every rule so the GUI / CLI / migration code can't drift.
    """
    cleaned = (name or "").strip()
    if not cleaned:
        raise InvalidProfileName("name must not be empty")
    if len(cleaned) > MAX_NAME_LEN:
        raise InvalidProfileName(f"name must be ≤ {MAX_NAME_LEN} characters")
    if cleaned.startswith("."):
        raise InvalidProfileName("name must not start with '.'")
    if _INVALID_CHARS.search(cleaned):
        raise InvalidProfileName(r"name must not contain control chars or any of: \ / : * ? \" < > |")
    if cleaned.upper() in _WIN_RESERVED:
        raise InvalidProfileName(f"name '{cleaned}' is reserved on Windows")
    return cleaned


def _profile_path(name: str) -> Path:
    return ROOT / f"{_validate_name(name)}.json"


# ---- Atomic JSON I/O -----------------------------------------------------
def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Could not read %s: %s", path, e)
        return None


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---- Public API ----------------------------------------------------------
def list_profiles() -> list[str]:
    """Return profile names sorted alphabetically (case-insensitive).

    `default` is always included, even if its file doesn't exist yet.
    """
    names = {DEFAULT_NAME}
    if ROOT.is_dir():
        for f in ROOT.glob("*.json"):
            if f.name == INDEX_PATH.name:
                continue
            names.add(f.stem)
    return sorted(names, key=str.lower)


def active_name() -> str:
    """Return the currently-active profile name, or `default` if not set."""
    data = _read_json(INDEX_PATH) or {}
    name = data.get("active") or DEFAULT_NAME
    try:
        return _validate_name(name)
    except InvalidProfileName:
        # Corrupt index — fall back to default rather than crash.
        log.warning("Active profile name in index.json is invalid; using '%s'.", DEFAULT_NAME)
        return DEFAULT_NAME


def set_active(name: str) -> None:
    """Persist `name` as the active profile (does not load its values)."""
    name = _validate_name(name)
    _write_json_atomic(INDEX_PATH, {"active": name, "version": _version()})


def load(name: str, settings) -> None:
    """Apply the named profile's values to `settings` in place.

    Unknown keys in the file are ignored; missing keys fall back to the
    dataclass default (already on `settings` because the caller constructs
    `Settings()` before calling us).
    """
    name = _validate_name(name)
    data = _read_json(_profile_path(name))
    if data is None:
        log.info("Profile '%s' has no file yet; using current defaults.", name)
        return
    for key, current in _fields(settings).items():
        if key in data:
            try:
                setattr(settings, key, type(current)(data[key]))
            except (TypeError, ValueError):
                pass


def save(name: str, settings) -> None:
    """Write the named profile from the current `settings` values."""
    name = _validate_name(name)
    _write_json_atomic(_profile_path(name), _fields(settings))


def rename(old: str, new: str) -> None:
    """Rename profile `old` to `new`. Refuses to rename `default` or overwrite an existing name."""
    old = _validate_name(old)
    new = _validate_name(new)
    if old == DEFAULT_NAME:
        raise InvalidProfileName("the 'default' profile cannot be renamed")
    if old == new:
        return
    if _profile_path(new).exists():
        raise InvalidProfileName(f"a profile named '{new}' already exists")
    src = _profile_path(old)
    if not src.exists():
        raise InvalidProfileName(f"no profile named '{old}'")
    os.replace(src, _profile_path(new))
    if active_name() == old:
        set_active(new)


def delete(name: str) -> None:
    """Delete the named profile. Refuses to delete `default`."""
    name = _validate_name(name)
    if name == DEFAULT_NAME:
        raise InvalidProfileName("the 'default' profile cannot be deleted")
    _profile_path(name).unlink(missing_ok=True)
    if active_name() == name:
        set_active(DEFAULT_NAME)


def duplicate(src_name: str, new_name: str, settings=None) -> None:
    """Copy `src_name` to `new_name`. If `settings` is given, write its values
    instead of the source file's contents (for "Save As current settings")."""
    src_name = _validate_name(src_name)
    new_name = _validate_name(new_name)
    if _profile_path(new_name).exists():
        raise InvalidProfileName(f"a profile named '{new_name}' already exists")
    if settings is not None:
        save(new_name, settings)
        return
    data = _read_json(_profile_path(src_name)) or {}
    _write_json_atomic(_profile_path(new_name), data)


def load_or_migrate(settings, requested: str | None = None) -> str:
    """Initialize the profiles directory if necessary and load a profile.

    If `requested` is given, load that profile (creating it if missing).
    Otherwise load the persisted active profile.

    On first run after upgrading from the single-file `user_preferences.json`
    layout, migrates the old file's contents into `profiles/default.json` and
    moves the old file aside as `.bak` so a downgrade still has it.

    Returns the name of the profile that was loaded.
    """
    _migrate_legacy_if_needed(settings)
    name = _validate_name(requested) if requested else active_name()
    if not _profile_path(name).exists():
        # Either first-time use, or the user asked for a not-yet-saved profile
        # via --profile. Materialize a file from current Settings so the row
        # in the picker actually has something to load on the next launch.
        save(name, settings)
    else:
        load(name, settings)
    set_active(name)
    return name


# ---- Internals -----------------------------------------------------------
def _fields(s) -> dict:
    return {k: v for k, v in vars(s).items() if isinstance(v, _SIMPLE)}


def _migrate_legacy_if_needed(settings) -> None:
    if ROOT.is_dir():
        return
    if not LEGACY_PREFERENCES.exists():
        # Nothing to migrate; just seed `default.json` from current Settings.
        save(DEFAULT_NAME, settings)
        set_active(DEFAULT_NAME)
        return
    log.info("Migrating %s -> profiles/default.json", LEGACY_PREFERENCES.name)
    # Read the legacy file directly (rather than delegating to preferences.load)
    # so the migration can't be silently wiped by the old version-gated reset.
    # Profiles represent user labor — preserve it across this one-time step.
    data = _read_json(LEGACY_PREFERENCES) or {}
    for key, current in _fields(settings).items():
        if key in data:
            try:
                setattr(settings, key, type(current)(data[key]))
            except (TypeError, ValueError):
                pass
    save(DEFAULT_NAME, settings)
    set_active(DEFAULT_NAME)
    try:
        os.replace(LEGACY_PREFERENCES, LEGACY_BACKUP)
        log.info("Old preferences file kept as %s", LEGACY_BACKUP.name)
    except OSError as e:
        log.warning("Could not move legacy preferences aside: %s", e)


# ---- Convenience for callers --------------------------------------------
def save_active(settings) -> None:
    """Save `settings` into the currently-active profile (used after every edit)."""
    save(active_name(), settings)


__all__: tuple[str, ...] = (
    "DEFAULT_NAME",
    "InvalidProfileName",
    "active_name",
    "delete",
    "duplicate",
    "list_profiles",
    "load",
    "load_or_migrate",
    "rename",
    "save",
    "save_active",
    "set_active",
)
