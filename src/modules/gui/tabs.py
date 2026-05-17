"""Tab content builders.

Each builder takes a parent container plus a "what changed" callback and
returns the Tk variables that back its inputs, so the orchestrator can
repopulate them after a `Reset to defaults` without having to walk the widget
tree by hand.

Every row gets a `?` HelpButton (hover-tooltip + click-modal); hovering the
label itself also surfaces the same text via Tooltip. Two paths to the same
help string means callers maintain one piece of text per setting.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from modules.gui.labels import (
    FIELD_RANGES,
    SECTIONS,
    TOGGLE_GROUPS,
    FieldSpec,
    ToggleSpec,
    format_range,
)
from modules.gui.widgets import HelpButton, Tooltip
from modules.settings import Settings


ToggleCallback = Callable[[str, bool], None]
EntryCallback = Callable[[str], None]
ResetCallback = Callable[[], None]


def build_controls_tab(parent: ctk.CTkFrame, settings: Settings,
                       on_toggle: ToggleCallback) -> dict[str, tk.BooleanVar]:
    """Build the Controls tab: one column per TOGGLE_GROUPS entry.

    Returns the `{attr: BooleanVar}` dict so the caller can refresh switches
    after a settings reset.
    """
    grid = ctk.CTkFrame(parent, fg_color="transparent")
    grid.pack(fill="both", expand=True, padx=8, pady=4)
    for i in range(len(TOGGLE_GROUPS)):
        grid.grid_columnconfigure(i, weight=1, uniform="trigger")
    grid.grid_rowconfigure(0, weight=1)

    vars_by_attr: dict[str, tk.BooleanVar] = {}
    for col, (title, toggles) in enumerate(TOGGLE_GROUPS):
        column = ctk.CTkFrame(grid)
        column.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)
        ctk.CTkLabel(column, text=title,
                     font=ctk.CTkFont(weight="bold", size=14)).pack(
            anchor="w", padx=10, pady=(8, 4))
        for spec in toggles:
            vars_by_attr[spec.attr] = _build_toggle_row(column, spec,
                                                       settings, on_toggle)
    return vars_by_attr


def build_settings_tab(parent: ctk.CTkFrame, settings: Settings,
                       on_change: EntryCallback,
                       on_reset: ResetCallback) -> dict[str, tk.StringVar]:
    """Build the Settings tab: a scrollable form of numeric inputs.

    Returns the `{attr: StringVar}` dict so the caller can refresh entries
    after a settings reset.
    """
    scroll = ctk.CTkScrollableFrame(parent)
    scroll.pack(fill="both", expand=True, padx=4, pady=4)

    vars_by_attr: dict[str, tk.StringVar] = {}
    for section_title, fields in SECTIONS:
        ctk.CTkLabel(
            scroll, text=section_title,
            font=ctk.CTkFont(weight="bold", size=14), anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 2))
        for spec in fields:
            value = getattr(settings, spec.attr, None)
            if value is None:
                continue
            var = _build_entry_row(scroll, spec, value, on_change)
            vars_by_attr[spec.attr] = var

    ctk.CTkButton(
        scroll, text="Reset all settings to defaults",
        fg_color="#a23a3a", hover_color="#882e2e",
        command=on_reset,
    ).pack(fill="x", padx=10, pady=(18, 10))
    return vars_by_attr


# ---- Row builders --------------------------------------------------------
def _build_toggle_row(parent: ctk.CTkFrame, spec: ToggleSpec, settings: Settings,
                      on_toggle: ToggleCallback) -> tk.BooleanVar:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=2)

    var = tk.BooleanVar(value=getattr(settings, spec.attr))
    switch = ctk.CTkSwitch(
        row, text="", variable=var, width=44,
        command=_toggle_command(spec.attr, var, on_toggle),
    )
    switch.pack(side="left", padx=(2, 8))

    label = ctk.CTkLabel(row, text=spec.label, anchor="w")
    label.pack(side="left", fill="x", expand=True)

    HelpButton(row, spec.help, title=spec.label).pack(side="right", padx=(0, 4))
    Tooltip(label, spec.help)
    Tooltip(switch, spec.help)
    return var


def _build_entry_row(parent: ctk.CTkFrame, spec: FieldSpec, value: object,
                     on_change: EntryCallback) -> tk.StringVar:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=2)

    label_text = f"{spec.label}  ({format_range(spec.lo, spec.hi)})"
    label = ctk.CTkLabel(row, text=label_text, anchor="w")
    label.pack(side="left", fill="x", expand=True, padx=(2, 8))
    Tooltip(label, spec.help)

    HelpButton(row, spec.help, title=spec.label).pack(side="right", padx=(0, 4))

    var = tk.StringVar(value=str(value))
    entry = ctk.CTkEntry(row, textvariable=var, width=110)
    entry.pack(side="right", padx=2)
    Tooltip(entry, spec.help)

    commit = _entry_commit(spec.attr, on_change)
    # Commit on Enter and on focus-out — matches the TUI's submit behavior
    # and the natural "I moved on from the field" expectation.
    entry.bind("<Return>", commit)
    entry.bind("<FocusOut>", commit)
    return var


# ---- Callback adapters ---------------------------------------------------
# Wrapping callback creation in helpers means the loop body doesn't carry a
# lambda-with-default-args (whose late-binding bugs are easy to miss).
def _toggle_command(attr: str, var: tk.BooleanVar,
                    on_toggle: ToggleCallback) -> Callable[[], None]:
    def _cmd() -> None:
        on_toggle(attr, bool(var.get()))
    return _cmd


def _entry_commit(attr: str, on_change: EntryCallback) -> Callable[[object], None]:
    def _cmd(_event: object) -> None:
        on_change(attr)
    return _cmd


# ---- Value coercion and clamping -----------------------------------------
def coerce_clamp(attr: str, current: object, raw: str) -> object | None:
    """Coerce `raw` to the type of `current`, then clamp to `FIELD_RANGES[attr]`.

    Returns the new (possibly clamped) value, or `None` if `raw` couldn't be
    parsed — caller is responsible for reverting the widget to `current` in
    that case. Pure function, no Tk imports, trivially unit-testable.
    """
    try:
        if isinstance(current, bool):
            new: object = raw.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(current, int):
            new = int(float(raw))
        elif isinstance(current, float):
            new = float(raw)
        else:
            new = raw.strip()
    except (ValueError, TypeError):
        return None

    rng = FIELD_RANGES.get(attr)
    if rng and isinstance(new, (int, float)) and not isinstance(new, bool):
        lo, hi = rng
        new = max(lo, min(hi, new))
        if isinstance(current, int):
            new = int(new)
    return new
