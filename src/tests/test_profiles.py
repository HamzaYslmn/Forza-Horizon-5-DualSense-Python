"""Unit + module tests for `modules.profiles`.

Each test gets its own `tmp_path` via the `isolated_profiles` fixture, so
they're independent and never touch the user's real profile directory.
"""
from __future__ import annotations

import json

import pytest

from modules.settings import Settings


# ---- Name validation -----------------------------------------------------
class TestValidateName:
    def test_strips_whitespace(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        assert profiles._validate_name("  Sport  ") == "Sport"

    def test_rejects_empty(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        with pytest.raises(profiles.InvalidProfileName):
            profiles._validate_name("")

    def test_rejects_too_long(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        with pytest.raises(profiles.InvalidProfileName):
            profiles._validate_name("x" * (profiles.MAX_NAME_LEN + 1))

    @pytest.mark.parametrize("bad", [
        "with/slash",
        "with\\backslash",
        "with:colon",
        "with*star",
        "with?question",
        'with"quote',
        "with<lt",
        "with>gt",
        "with|pipe",
        "with\x00null",
    ])
    def test_rejects_filesystem_unsafe_chars(self, isolated_profiles, bad):
        profiles = isolated_profiles["profiles"]
        with pytest.raises(profiles.InvalidProfileName):
            profiles._validate_name(bad)

    def test_rejects_leading_dot(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        with pytest.raises(profiles.InvalidProfileName):
            profiles._validate_name(".hidden")

    @pytest.mark.parametrize("reserved", ["CON", "PRN", "aux", "NUL", "COM1", "LPT9"])
    def test_rejects_windows_reserved(self, isolated_profiles, reserved):
        profiles = isolated_profiles["profiles"]
        with pytest.raises(profiles.InvalidProfileName):
            profiles._validate_name(reserved)


# ---- CRUD on a fresh dir -------------------------------------------------
class TestProfileCRUD:
    def test_first_run_creates_default(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        name = profiles.load_or_migrate(s)
        assert name == "default"
        assert (isolated_profiles["root"] / "default.json").exists()
        assert profiles.list_profiles() == ["default"]
        assert profiles.active_name() == "default"

    def test_save_and_load_round_trip(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        s.brake_max_force = 99
        profiles.save("default", s)

        s2 = Settings()
        assert s2.brake_max_force == 60  # dataclass default
        profiles.load("default", s2)
        assert s2.brake_max_force == 99

    def test_list_profiles_sorted_case_insensitive(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        for name in ["zulu", "Alpha", "mike"]:
            profiles.duplicate("default", name, settings=s)
        # Should be sorted ignoring case
        assert profiles.list_profiles() == ["Alpha", "default", "mike", "zulu"]

    def test_list_profiles_includes_default_even_without_file(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        # Don't migrate — just check empty dir
        isolated_profiles["root"].mkdir()
        assert "default" in profiles.list_profiles()

    def test_rename_moves_file_and_follows_active(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        profiles.duplicate("default", "Stiff", settings=s)
        profiles.set_active("Stiff")
        profiles.rename("Stiff", "Sport")

        names = profiles.list_profiles()
        assert "Sport" in names
        assert "Stiff" not in names
        assert profiles.active_name() == "Sport"

    def test_rename_refuses_default(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        with pytest.raises(profiles.InvalidProfileName):
            profiles.rename("default", "Other")

    def test_rename_refuses_existing_target(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        profiles.duplicate("default", "A", settings=s)
        profiles.duplicate("default", "B", settings=s)
        with pytest.raises(profiles.InvalidProfileName):
            profiles.rename("A", "B")

    def test_delete_refuses_default(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        with pytest.raises(profiles.InvalidProfileName):
            profiles.delete("default")

    def test_delete_active_resets_to_default(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        profiles.duplicate("default", "Doomed", settings=s)
        profiles.set_active("Doomed")
        profiles.delete("Doomed")
        assert profiles.active_name() == "default"
        assert "Doomed" not in profiles.list_profiles()

    def test_duplicate_with_settings_uses_those_values(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        # Modify in-memory only — the default.json on disk has old values
        s.brake_max_force = 88
        profiles.duplicate("default", "Snapshot", settings=s)

        s2 = Settings()
        profiles.load("Snapshot", s2)
        assert s2.brake_max_force == 88

    def test_duplicate_refuses_existing_target(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        profiles.duplicate("default", "X", settings=s)
        with pytest.raises(profiles.InvalidProfileName):
            profiles.duplicate("default", "X", settings=s)


# ---- File format / forward-compat ---------------------------------------
class TestFileFormat:
    def test_unknown_keys_ignored(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        isolated_profiles["root"].mkdir()
        (isolated_profiles["root"] / "weird.json").write_text(
            json.dumps({"brake_max_force": 33, "this_field_does_not_exist": "oops"})
        )
        s = Settings()
        profiles.load("weird", s)
        assert s.brake_max_force == 33
        assert not hasattr(s, "this_field_does_not_exist")

    def test_missing_keys_keep_dataclass_defaults(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        isolated_profiles["root"].mkdir()
        # Partial file: only one field. Everything else should fall back to defaults.
        (isolated_profiles["root"] / "partial.json").write_text(
            json.dumps({"brake_max_force": 77})
        )
        s = Settings()
        s.throttle_max_force = 200  # in-memory non-default
        profiles.load("partial", s)
        assert s.brake_max_force == 77
        assert s.throttle_max_force == 200  # untouched by load

    def test_save_only_simple_types(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        data = json.loads((isolated_profiles["root"] / "default.json").read_text())
        # Settings has a tuple field `game_process_name_contains` — should be filtered out
        assert "game_process_name_contains" not in data
        # All saved values are JSON-roundtrippable
        for value in data.values():
            assert isinstance(value, (bool, int, float, str)), value

    def test_atomic_write_leaves_no_tmp_on_success(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        for f in isolated_profiles["root"].iterdir():
            assert not f.name.endswith(".tmp"), f"stray temp file: {f.name}"


# ---- Migration from legacy single-file -----------------------------------
class TestMigration:
    def test_migrates_legacy_into_default(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        legacy_data = {
            "brake_max_force": 123,
            "enable_abs": False,
            "version": "1.1.9",
        }
        isolated_profiles["legacy"].parent.mkdir(parents=True, exist_ok=True)
        isolated_profiles["legacy"].write_text(json.dumps(legacy_data))

        s = Settings()
        name = profiles.load_or_migrate(s)

        assert name == "default"
        data = json.loads((isolated_profiles["root"] / "default.json").read_text())
        assert data["brake_max_force"] == 123
        assert data["enable_abs"] is False
        # Legacy file moved aside, not deleted
        assert not isolated_profiles["legacy"].exists()
        assert isolated_profiles["legacy_backup"].exists()
        # Migration should NOT have wiped values based on a version mismatch,
        # unlike the old preferences.load behavior.
        backup_data = json.loads(isolated_profiles["legacy_backup"].read_text())
        assert backup_data == legacy_data

    def test_no_migration_when_profiles_dir_exists(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        # Create profiles/ first, then stage a legacy file — migration must skip
        isolated_profiles["root"].mkdir()
        (isolated_profiles["root"] / "default.json").write_text(
            json.dumps({"brake_max_force": 99})
        )
        isolated_profiles["legacy"].write_text(json.dumps({"brake_max_force": 1}))

        s = Settings()
        profiles.load_or_migrate(s)
        assert s.brake_max_force == 99  # from default.json, not legacy
        assert isolated_profiles["legacy"].exists()  # untouched


# ---- Edge cases ---------------------------------------------------------
class TestEdgeCases:
    def test_load_or_migrate_with_requested_profile(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        name = profiles.load_or_migrate(s, requested="Sport")
        assert name == "Sport"
        assert "Sport" in profiles.list_profiles()
        assert profiles.active_name() == "Sport"

    def test_active_name_with_corrupt_index_falls_back_to_default(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        isolated_profiles["root"].mkdir()
        # Index pointing at an invalid name
        (isolated_profiles["root"] / "index.json").write_text(
            json.dumps({"active": "with/slash"})
        )
        # Should NOT raise; should fall back
        assert profiles.active_name() == "default"

    def test_save_active_writes_to_currently_active(self, isolated_profiles):
        profiles = isolated_profiles["profiles"]
        s = Settings()
        profiles.load_or_migrate(s)
        profiles.duplicate("default", "Other", settings=s)
        profiles.set_active("Other")

        s.brake_max_force = 42
        profiles.save_active(s)

        other_data = json.loads((isolated_profiles["root"] / "Other.json").read_text())
        default_data = json.loads((isolated_profiles["root"] / "default.json").read_text())
        assert other_data["brake_max_force"] == 42
        assert default_data["brake_max_force"] == 60  # unchanged
