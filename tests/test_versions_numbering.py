"""Tests para next_version_number — pure function depende só do output do Sql.

Mock delta.fetch_all_params para retornar lista de version_number strings.
Foco: empty (v1.0 first), increment minor, handle 'v' prefix optional,
malformed strings ignorados.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.versions import service as vsvc
from nuclea_modeler.backend.versions.service import next_version_number


@pytest.fixture
def patched(monkeypatch):
    """Patcha delta.fetch_all_params para retornar versions injetadas."""
    state = {"versions": []}

    def fake(sql_dep, query, params=None):
        return [[v] for v in state["versions"]]

    from nuclea_modeler.backend.core import delta
    monkeypatch.setattr(delta, "fetch_all_params", fake)

    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(vsvc, "get_settings", lambda: fake_settings)

    return state


# ─── Empty / first version ──────────────────────────────────────────────────


def test_empty_returns_v1_0(patched):
    patched["versions"] = []
    assert next_version_number(MagicMock(), "sys-1") == "v1.0"


def test_only_malformed_versions_returns_v1_0(patched):
    """Se todas as versões são unparseable, comporta-se como vazio."""
    patched["versions"] = ["unparseable", "also-bad", ""]
    assert next_version_number(MagicMock(), "sys-1") == "v1.0"


# ─── Increment minor ────────────────────────────────────────────────────────


def test_single_v1_0_increments_to_v1_1(patched):
    patched["versions"] = ["v1.0"]
    assert next_version_number(MagicMock(), "sys-1") == "v1.1"


def test_multiple_versions_picks_max_and_increments(patched):
    patched["versions"] = ["v1.0", "v1.2", "v1.1"]
    assert next_version_number(MagicMock(), "sys-1") == "v1.3"


def test_skips_v_prefix_case_insensitive(patched):
    """Aceita v/V/None como prefix."""
    patched["versions"] = ["V1.5"]
    assert next_version_number(MagicMock(), "sys-1") == "v1.6"

    patched["versions"] = ["1.5"]  # sem prefix
    assert next_version_number(MagicMock(), "sys-1") == "v1.6"


def test_handles_major_versions(patched):
    """Múltiplas major versions — pega o max global."""
    patched["versions"] = ["v1.0", "v2.0", "v1.99"]
    assert next_version_number(MagicMock(), "sys-1") == "v2.1"


def test_minor_only_increments_when_major_matches(patched):
    """v3.0 ganha de v2.99."""
    patched["versions"] = ["v2.99", "v3.0"]
    assert next_version_number(MagicMock(), "sys-1") == "v3.1"


def test_handles_minor_without_dot(patched):
    """v2 sem .X assume minor=0 → próxima é v2.1."""
    patched["versions"] = ["v2"]
    assert next_version_number(MagicMock(), "sys-1") == "v2.1"


def test_mixed_valid_and_invalid(patched):
    """Strings unparseable são ignoradas, valid ones contam."""
    patched["versions"] = ["unparseable", "v1.5", "bad", "v1.2"]
    assert next_version_number(MagicMock(), "sys-1") == "v1.6"


def test_whitespace_in_version_string_handled(patched):
    """Strings com whitespace external são strippadas."""
    patched["versions"] = ["  v1.5  "]
    assert next_version_number(MagicMock(), "sys-1") == "v1.6"


def test_high_minor_numbers(patched):
    """Sanity: minor pode crescer arbitrariamente."""
    patched["versions"] = ["v1.99"]
    assert next_version_number(MagicMock(), "sys-1") == "v1.100"


def test_none_version_strings_skipped(patched):
    """Banco pode retornar None em version_number (row corrompida)."""
    patched["versions"] = [None, "v1.0"]
    assert next_version_number(MagicMock(), "sys-1") == "v1.1"
