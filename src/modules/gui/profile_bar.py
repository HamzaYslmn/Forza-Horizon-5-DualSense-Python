"""Profile picker for the top bar.

Self-contained widget: it owns its dropdown variable and "..." popup menu,
and exposes one outward signal (`on_profile_changed`) plus four imperative
operations (Save / Save As / Rename / Delete) the caller wires up. Keeping
all profile UI here means `TriggerGUI` only sees a single tidy surface.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Callable

import customtkinter as ctk

from modules import profiles
from modules.settings import Settings

log = logging.getLogger("fhds")


class ProfileBar(ctk.CTkFrame):
    """Dropdown + actions menu for selecting/managing tuning profiles."""

    def __init__(self, master: tk.Misc, settings: Settings,
                 on_profile_changed: Callable[[str], None]):
        super().__init__(master, fg_color="transparent")
        self._settings = settings
        self._on_changed = on_profile_changed
        self._refreshing = False  # guard against re-entrant set() during refresh

        ctk.CTkLabel(self, text="Profile:", anchor="w").pack(
            side="left", padx=(4, 6))

        self._var = tk.StringVar(value=profiles.active_name())
        self._menu = ctk.CTkOptionMenu(
            self, variable=self._var, values=profiles.list_profiles(),
            width=180, dynamic_resizing=False, command=self._on_select,
        )
        self._menu.pack(side="left", padx=(0, 4))

        ctk.CTkButton(self, text="Save", width=70,
                      command=self._action_save).pack(side="left", padx=2)
        ctk.CTkButton(self, text="…", width=34,
                      command=self._open_actions_menu).pack(side="left", padx=2)

    # MARK: External API ------------------------------------------------------
    def refresh(self, active: str | None = None) -> None:
        """Repopulate the dropdown (e.g. after a save/rename/delete)."""
        self._refreshing = True
        try:
            self._menu.configure(values=profiles.list_profiles())
            self._var.set(active or profiles.active_name())
        finally:
            self._refreshing = False

    # MARK: Internal handlers -------------------------------------------------
    def _on_select(self, name: str) -> None:
        if self._refreshing:
            return
        try:
            self._on_changed(name)
        except Exception:
            log.exception("Profile switch failed")
            self.refresh()

    def _action_save(self) -> None:
        """Save settings into the currently-selected profile (overwrite)."""
        try:
            profiles.save_active(self._settings)
            log.info("Saved profile '%s'.", profiles.active_name())
        except Exception:
            log.exception("Save failed")

    def _open_actions_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Save As…", command=self._action_save_as)
        active = profiles.active_name()
        is_default = active == profiles.DEFAULT_NAME
        menu.add_command(label="Rename…", command=self._action_rename,
                         state="disabled" if is_default else "normal")
        menu.add_command(label="Delete", command=self._action_delete,
                         state="disabled" if is_default else "normal")
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _action_save_as(self) -> None:
        new_name = simpledialog.askstring(
            "Save profile as", "New profile name:", parent=self.winfo_toplevel(),
        )
        if not new_name:
            return
        try:
            profiles.duplicate(profiles.active_name(), new_name,
                               settings=self._settings)
        except profiles.InvalidProfileName as e:
            messagebox.showerror("Invalid name", str(e), parent=self.winfo_toplevel())
            return
        profiles.set_active(new_name)
        self.refresh(active=new_name)
        log.info("Created profile '%s'.", new_name)
        self._on_changed(new_name)

    def _action_rename(self) -> None:
        old = profiles.active_name()
        new = simpledialog.askstring(
            "Rename profile", f"Rename '{old}' to:",
            parent=self.winfo_toplevel(), initialvalue=old,
        )
        if not new or new == old:
            return
        try:
            profiles.rename(old, new)
        except profiles.InvalidProfileName as e:
            messagebox.showerror("Cannot rename", str(e), parent=self.winfo_toplevel())
            return
        self.refresh(active=new)
        log.info("Renamed profile '%s' -> '%s'.", old, new)

    def _action_delete(self) -> None:
        name = profiles.active_name()
        if not messagebox.askyesno(
            "Delete profile", f"Delete profile '{name}'?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            profiles.delete(name)
        except profiles.InvalidProfileName as e:
            messagebox.showerror("Cannot delete", str(e), parent=self.winfo_toplevel())
            return
        log.info("Deleted profile '%s'.", name)
        new_active = profiles.active_name()
        self.refresh(active=new_active)
        self._on_changed(new_active)
