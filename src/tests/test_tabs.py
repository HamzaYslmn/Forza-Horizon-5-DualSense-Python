"""Tests for the pure logic in `modules.gui.tabs` (the coerce_clamp helper).

The widget-building functions in tabs.py need Tk and are exercised by the
GUI smoke tests; this file covers the value-coercion logic that's pure
Python and worth testing exhaustively.
"""
from __future__ import annotations

import pytest

from modules.gui.tabs import coerce_clamp


class TestCoerceClampInt:
    @pytest.mark.parametrize("raw,expected", [
        ("0", 0),
        ("60", 60),
        ("255", 255),
        ("  120  ", 120),     # whitespace trimmed
        ("99.7", 99),         # float→int truncates
        ("-5", 0),            # clamped to lo
        ("9999", 255),        # clamped to hi
    ])
    def test_int_field(self, raw, expected):
        # brake_max_force has range 0-255 and an int default
        assert coerce_clamp("brake_max_force", 60, raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", "1e", "not a number"])
    def test_int_field_unparseable_returns_none(self, raw):
        assert coerce_clamp("brake_max_force", 60, raw) is None

    def test_int_clamp_returns_int_type(self):
        result = coerce_clamp("brake_max_force", 60, "300")
        assert result == 255
        assert isinstance(result, int)


class TestCoerceClampFloat:
    # brake_curve range is 0.1-20.0 — picks values that exercise parse + clamp
    @pytest.mark.parametrize("raw,expected", [
        ("5", 5.0),
        ("5.0", 5.0),
        ("3.2", 3.2),
        ("20.0", 20.0),
        ("100", 20.0),        # clamped to hi
        ("0", 0.1),           # clamped to lo
        ("-1", 0.1),          # clamped to lo
    ])
    def test_float_field(self, raw, expected):
        assert coerce_clamp("brake_curve", 5.0, raw) == pytest.approx(expected)

    def test_clamp_at_ratio_boundary(self):
        # rev_limit_ratio range is 0.0-1.0
        assert coerce_clamp("rev_limit_ratio", 0.93, "0.5") == pytest.approx(0.5)
        assert coerce_clamp("rev_limit_ratio", 0.93, "5.0") == pytest.approx(1.0)
        assert coerce_clamp("rev_limit_ratio", 0.93, "-1") == pytest.approx(0.0)

    @pytest.mark.parametrize("raw", ["xyz", ""])
    def test_float_field_unparseable_returns_none(self, raw):
        assert coerce_clamp("rev_limit_ratio", 0.93, raw) is None

    def test_float_returns_float_type(self):
        result = coerce_clamp("brake_curve", 5.0, "3.2")
        assert isinstance(result, float)


class TestCoerceClampBool:
    @pytest.mark.parametrize("raw", ["1", "true", "True", "TRUE", "yes", "on"])
    def test_truthy(self, raw):
        # If a bool field is ever coerced through here (unusual since toggles
        # don't go through entries), it should parse common truthy strings.
        assert coerce_clamp("enable_abs", False, raw) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "garbage"])
    def test_falsy(self, raw):
        assert coerce_clamp("enable_abs", True, raw) is False


class TestCoerceClampUnknownAttr:
    def test_no_range_means_no_clamp(self):
        """An attr not in FIELD_RANGES should still coerce types but not clamp."""
        assert coerce_clamp("never_heard_of_it", 5, "9999") == 9999
        assert coerce_clamp("never_heard_of_it", 1.5, "100.0") == 100.0
