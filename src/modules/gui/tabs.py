"""Tab content builders.

Each builder takes a parent container plus a "what changed" callback and
returns the Tk variables that back its inputs, so the orchestrator can
repopulate them after a `Reset to defaults` without having to walk the widget
tree by hand.

Every row gets a `?` HelpButton (hover-tooltip + click-modal); hovering the
label itself also surfaces the same text via Tooltip. Two paths to the same
help string means callers maintain one piece of text per setting.

Inside the rows we use plain `tk` widgets (Frame, Label, Entry) rather than
their CustomTkinter equivalents: CTk variants render rounded backgrounds via
PIL on every `<Configure>` event, which made window resizes laggy when the
Settings tab held ~30 of them. The CTk visual identity is preserved on the
chrome (top bar, tabs, buttons, switches); inner row widgets are tk-native
and styled to match the dark theme.
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
from modules.gui.widgets import HelpButton, ScrollingFrame, Tooltip
from modules.settings import Settings

# Tk-native row colors picked to match the CTk dark theme so plain tk.Entry
# and tk.Label rows visually belong inside CTk frames.
_ROW_FG = "#dce4ee"           # CTk dark default text color
_ROW_BG = "#2b2b2b"            # CTk dark frame background
_ENTRY_BG = "#343638"          # CTk dark entry background
_ENTRY_FG = "#dce4ee"
_ENTRY_BORDER = "#565b5e"


ToggleCallback = Callable[[str, bool], None]
EntryCallback = Callable[[str], None]
ResetCallback = Callable[[], None]


# CTk widgets reject `cget("bg")` because their attribute system only
# whitelists CTk-known arguments. Hardcoding the dark-theme scrollable-frame
# background lets the plain tk.Frame containers we use for row layout blend in
# without the per-Configure redraw cost CTkFrame incurs.
_PLACEHOLDER_FRAME_BG = "#2b2b2b"  # CTk dark theme inner-frame background


def _parent_bg(widget: tk.Misc) -> str:
    """Return the parent's background color if it's a tk-native widget,
    falling back to the CTk dark-theme placeholder otherwise.

    Catches both `tk.TclError` (tk-native widget with no `bg`) and
    `ValueError` (CTk widgets reject any `cget` arg not on their whitelist).
    """
    try:
        return widget.cget("bg")
    except (tk.TclError, ValueError):
        return _PLACEHOLDER_FRAME_BG


def build_controls_tab(parent: ctk.CTkFrame, settings: Settings,
                       on_toggle: ToggleCallback) -> dict[str, tk.BooleanVar]:
    """Build the Controls tab: one column per TOGGLE_GROUPS entry.

    Returns the `{attr: BooleanVar}` dict so the caller can refresh switches
    after a settings reset.
    """
    grid = tk.Frame(parent, bg=_parent_bg(parent))
    grid.pack(fill="both", expand=True, padx=8, pady=4)
    for i in range(len(TOGGLE_GROUPS)):
        grid.grid_columnconfigure(i, weight=1, uniform="trigger")
    grid.grid_rowconfigure(0, weight=1)

    vars_by_attr: dict[str, tk.BooleanVar] = {}
    for col, (title, toggles) in enumerate(TOGGLE_GROUPS):
        column = ctk.CTkFrame(grid)
        column.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)
        # Keep CTkFrame for the column (single instance, gives the rounded
        # group look) but use tk.Label for the column header so we don't
        # pay the per-resize CTk redraw cost.
        tk.Label(column, text=title, anchor="w",
                 bg=_parent_bg(column), fg=_ROW_FG,
                 font=("TkDefaultFont", 11, "bold")).pack(
            anchor="w", padx=10, pady=(8, 4))
        for spec in toggles:
            vars_by_attr[spec.attr] = _build_toggle_row(column, spec,
                                                       settings, on_toggle)
    return vars_by_attr


def build_settings_tab(parent: ctk.CTkFrame, settings: Settings,
                       on_change: EntryCallback,
                       on_reset: ResetCallback) -> dict[str, tk.StringVar]:
    """Build the Settings tab: a scrollable form of numeric inputs.

    Uses the lighter `ScrollingFrame` (tk.Canvas + tk.Frame + ttk.Scrollbar)
    rather than `CTkScrollableFrame`, which re-rendered its CTk-themed
    background through PIL on every Configure event and made the parent
    window's resize laggy.

    Returns the `{attr: StringVar}` dict so the caller can refresh entries
    after a settings reset.
    """
    scroll_container = ScrollingFrame(parent)
    scroll_container.pack(fill="both", expand=True, padx=4, pady=4)
    scroll = scroll_container.interior  # the inner frame children pack into

    vars_by_attr: dict[str, tk.StringVar] = {}
    for section_title, fields in SECTIONS:
        tk.Label(
            scroll, text=section_title, anchor="w",
            bg=_parent_bg(scroll), fg=_ROW_FG,
            font=("TkDefaultFont", 11, "bold"),
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
    # Plain tk.Frame instead of CTkFrame: zero corner_radius work on resize.
    # Each setting row gets one — 35+ rows means 35+ fewer CTk redraws per
    # Configure event.
    row = tk.Frame(parent, bg=_parent_bg(parent))
    row.pack(fill="x", padx=8, pady=2)

    var = tk.BooleanVar(value=getattr(settings, spec.attr))
    switch = ctk.CTkSwitch(
        row, text="", variable=var, width=44,
        command=_toggle_command(spec.attr, var, on_toggle),
    )
    switch.pack(side="left", padx=(2, 8))

    # tk.Label rather than CTkLabel: 8 toggles is small, but the row label
    # has no rounded background to render, so the visual delta is zero and
    # we save 8 PIL-redraw cycles per resize event.
    label = tk.Label(row, text=spec.label, anchor="w",
                     bg=_parent_bg(row), fg=_ROW_FG)
    label.pack(side="left", fill="x", expand=True)

    HelpButton(row, spec.help, title=spec.label).pack(side="right", padx=(0, 4))
    Tooltip(label, spec.help)
    Tooltip(switch, spec.help)
    return var


def _build_entry_row(parent: ctk.CTkFrame, spec: FieldSpec, value: object,
                     on_change: EntryCallback) -> tk.StringVar:
    # Plain tk.Frame instead of CTkFrame: zero corner_radius work on resize.
    # Each setting row gets one — 35+ rows means 35+ fewer CTk redraws per
    # Configure event.
    row = tk.Frame(parent, bg=_parent_bg(parent))
    row.pack(fill="x", padx=8, pady=2)

    label_text = f"{spec.label}  ({format_range(spec.lo, spec.hi)})"
    # tk.Label + tk.Entry rather than CTk equivalents. With 28 of each on the
    # Settings tab, CTk's per-Configure PIL redraw was the main cause of the
    # window-resize lag. Plain tk widgets styled to match the dark theme
    # have the same usable feel without the redraw cost.
    label = tk.Label(row, text=label_text, anchor="w",
                     bg=_parent_bg(row), fg=_ROW_FG)
    label.pack(side="left", fill="x", expand=True, padx=(2, 8))
    Tooltip(label, spec.help)

    HelpButton(row, spec.help, title=spec.label).pack(side="right", padx=(0, 4))

    var = tk.StringVar(value=str(value))
    entry = tk.Entry(
        row, textvariable=var, width=14,
        bg=_ENTRY_BG, fg=_ENTRY_FG, insertbackground=_ENTRY_FG,
        relief="flat", highlightthickness=1,
        highlightbackground=_ENTRY_BORDER, highlightcolor="#1f6aa5",
    )
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
