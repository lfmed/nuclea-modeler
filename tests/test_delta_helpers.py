"""Tests for the literal-quoting + parameter helpers in core/delta.

These do NOT hit a SQL Warehouse — pure logic over the helpers themselves.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import pytest

from nuclea_modeler.backend.core.delta import _quote_lit, _format_ts, param


# ─── _quote_lit ──────────────────────────────────────────────────────────────


def test_quote_lit_none():
    assert _quote_lit(None) == "NULL"


def test_quote_lit_bool():
    assert _quote_lit(True) == "true"
    assert _quote_lit(False) == "false"


def test_quote_lit_int_float():
    assert _quote_lit(42) == "42"
    assert _quote_lit(-3.14) == "-3.14"


def test_quote_lit_string_escapes_apostrophes():
    assert _quote_lit("O'Hara") == "'O''Hara'"


def test_quote_lit_list_renders_array():
    assert _quote_lit(["a", "b"]) == "array('a', 'b')"


def test_quote_lit_dict_serialises_as_json_string():
    out = _quote_lit({"k": "v"})
    assert out.startswith("'") and out.endswith("'")
    assert '"k"' in out and '"v"' in out


def test_quote_lit_naive_datetime_treated_as_utc():
    dt = datetime(2026, 1, 15, 10, 30, 0)
    out = _quote_lit(dt)
    assert out.startswith("TIMESTAMP '2026-01-15 10:30:00")
    assert out.endswith("'")


def test_quote_lit_aware_datetime_normalised_to_utc():
    tz_brt = timezone(timedelta(hours=-3))
    dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=tz_brt)
    # 10:30 BRT == 13:30 UTC
    out = _quote_lit(dt)
    assert "13:30:00" in out
    assert out.startswith("TIMESTAMP '2026-01-15 13:30:00")


def test_quote_lit_date():
    assert _quote_lit(date(2026, 1, 15)) == "DATE '2026-01-15'"


# ─── _format_ts ──────────────────────────────────────────────────────────────


def test_format_ts_microseconds():
    dt = datetime(2026, 1, 15, 10, 30, 0, 123456)
    assert _format_ts(dt) == "2026-01-15 10:30:00.123456"


# ─── param() ─────────────────────────────────────────────────────────────────


def test_param_none_is_null_string():
    p = param("x", None)
    assert p.name == "x"
    assert p.value is None
    assert p.type == "STRING"


def test_param_string_default_type():
    p = param("name", "alice")
    assert p.value == "alice"
    assert p.type == "STRING"


def test_param_int_typed_as_bigint():
    p = param("n", 42)
    assert p.value == "42"
    assert p.type == "BIGINT"


def test_param_bool_lowercase():
    p = param("active", True)
    assert p.value == "true"
    assert p.type == "BOOLEAN"


def test_param_datetime_typed_as_timestamp_and_utc_normalised():
    tz_brt = timezone(timedelta(hours=-3))
    dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=tz_brt)
    p = param("created_at", dt)
    assert p.type == "TIMESTAMP"
    assert "13:30:00" in p.value  # 10:30 BRT == 13:30 UTC


def test_param_date_typed_as_date():
    p = param("d", date(2026, 1, 15))
    assert p.value == "2026-01-15"
    assert p.type == "DATE"


def test_param_explicit_type_hint_overrides_default():
    p = param("amount", 99, type_hint="DECIMAL(18,2)")
    assert p.value == "99"
    assert p.type == "DECIMAL(18,2)"


def test_param_string_with_apostrophe_passed_through_verbatim():
    """Param API handles escaping server-side; we must NOT pre-escape."""
    p = param("name", "O'Hara")
    assert p.value == "O'Hara"
