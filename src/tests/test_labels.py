"""Tests for the labels module.

These are mostly invariant checks: every label/help string must point at a real
Settings field, every range must be sane, etc. Doubles as the spec for what
adding a new Settings field requires (add a FieldSpec or ToggleSpec).
"""
from __future__ import annotations

import pytest

from modules.gui.labels import (
    FIELD_RANGES,
    SECTIONS,
    STARTUP_HINT,
    TOGGLE_GROUPS,
    _validate_against_settings,
    format_range,
)
from modules.settings import Settings


def test_validation_passes():
    """Re-running the import-time validator should succeed."""
    _validate_against_settings()


def test_every_field_spec_attr_exists_on_settings():
    s = Settings()
    for _, fields in SECTIONS:
        for spec in fields:
            assert hasattr(s, spec.attr), f"{spec.attr} not on Settings"


def test_every_toggle_spec_attr_is_bool_on_settings():
    s = Settings()
    for _, toggles in TOGGLE_GROUPS:
        for spec in toggles:
            assert hasattr(s, spec.attr), f"{spec.attr} not on Settings"
            assert isinstance(getattr(s, spec.attr), bool), (
                f"{spec.attr} expected bool, got {type(getattr(s, spec.attr)).__name__}"
            )


def test_field_ranges_are_lo_le_hi():
    for attr, (lo, hi) in FIELD_RANGES.items():
        assert lo <= hi, f"{attr}: lo={lo} > hi={hi}"


def test_field_defaults_fall_within_range():
    """Sanity: every default in Settings is within its declared range."""
    s = Settings()
    for attr, (lo, hi) in FIELD_RANGES.items():
        value = getattr(s, attr)
        if isinstance(value, bool):
            continue  # toggles shouldn't be in FIELD_RANGES anyway
        assert lo <= value <= hi, f"{attr}: default {value} outside [{lo}, {hi}]"


def test_no_duplicate_field_specs():
    seen: set[str] = set()
    for _, fields in SECTIONS:
        for spec in fields:
            assert spec.attr not in seen, f"duplicate FieldSpec for {spec.attr}"
            seen.add(spec.attr)


def test_no_duplicate_toggle_specs():
    seen: set[str] = set()
    for _, toggles in TOGGLE_GROUPS:
        for spec in toggles:
            assert spec.attr not in seen, f"duplicate ToggleSpec for {spec.attr}"
            seen.add(spec.attr)


def test_field_specs_and_toggle_specs_are_disjoint():
    field_attrs = {spec.attr for _, fields in SECTIONS for spec in fields}
    toggle_attrs = {spec.attr for _, toggles in TOGGLE_GROUPS for spec in toggles}
    overlap = field_attrs & toggle_attrs
    assert not overlap, f"attrs in both SECTIONS and TOGGLE_GROUPS: {overlap}"


def test_help_text_is_non_trivial():
    """Every help string must be more than a one-liner — it's the click-modal content too."""
    for _, fields in SECTIONS:
        for spec in fields:
            assert len(spec.help) > 40, f"{spec.attr}: help too short"
    for _, toggles in TOGGLE_GROUPS:
        for spec in toggles:
            assert len(spec.help) > 40, f"{spec.attr}: help too short"


def test_help_text_references_field_name():
    """Help strings end with `(field: foo)` so users can find the actual attr."""
    for _, fields in SECTIONS:
        for spec in fields:
            assert f"(field: {spec.attr})" in spec.help, (
                f"{spec.attr}: help missing '(field: ...)' breadcrumb"
            )


def test_startup_hint_has_format_placeholders():
    s = STARTUP_HINT.format(host="127.0.0.1", port=5300)
    assert "127.0.0.1" in s
    assert "5300" in s


@pytest.mark.parametrize("lo,hi,expected", [
    (0, 255, "0-255"),
    (0.0, 1.0, "0-1"),
    (0.1, 20.0, "0.1-20"),
    (-5, 5, "-5-5"),
])
def test_format_range(lo, hi, expected):
    assert format_range(lo, hi) == expected
