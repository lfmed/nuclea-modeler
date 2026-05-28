"""Tests para _maybe_run_startup_migrations gate logic.

Foca no flag NUCLEA_MIGRATIONS_AUTO_APPLY — controla se apply_migrations
roda no boot. Testa que disabled/falsy values pulam, truthy aplicam,
e que failures NÃO abortam boot (defesa do operador).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nuclea_modeler.backend.core._factory import _maybe_run_startup_migrations


# ─── Flag gating ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "flag_value",
    ["true", "TRUE", "True", "1", "yes", "YES"],
)
def test_truthy_flag_triggers_apply(monkeypatch, flag_value):
    """Flag em qualquer truthy variation → tenta aplicar migrations."""
    monkeypatch.setenv("NUCLEA_MIGRATIONS_AUTO_APPLY", flag_value)

    apply_called = {"count": 0}

    def fake_apply(*args, **kwargs):
        apply_called["count"] += 1
        return {"applied": 0, "skipped": 0, "drifted": 0, "failed": 0}

    # Patches são by-module-import path
    with patch("nuclea_modeler.backend.core.migrations.apply_migrations", side_effect=fake_apply):
        with patch("nuclea_modeler.backend.core.migrations.find_migrations_dir") as fake_dir:
            fake_dir.return_value.exists.return_value = True
            with patch("databricks.sdk.WorkspaceClient") as ws:
                ws.return_value.statement_execution = MagicMock()
                _maybe_run_startup_migrations(MagicMock())

    assert apply_called["count"] == 1


@pytest.mark.parametrize(
    "flag_value",
    ["false", "FALSE", "0", "no", "off", "", "anything-else", "disabled"],
)
def test_falsy_flag_skips_apply(monkeypatch, flag_value):
    """Flag em qualquer falsy/unrecognized → não tenta aplicar."""
    monkeypatch.setenv("NUCLEA_MIGRATIONS_AUTO_APPLY", flag_value)

    apply_called = {"count": 0}

    def fake_apply(*args, **kwargs):
        apply_called["count"] += 1
        return {"applied": 0, "skipped": 0, "drifted": 0, "failed": 0}

    with patch("nuclea_modeler.backend.core.migrations.apply_migrations", side_effect=fake_apply):
        _maybe_run_startup_migrations(MagicMock())

    assert apply_called["count"] == 0


def test_default_flag_is_truthy(monkeypatch):
    """Sem env var setada, default é 'true' → aplica."""
    monkeypatch.delenv("NUCLEA_MIGRATIONS_AUTO_APPLY", raising=False)

    apply_called = {"count": 0}

    def fake_apply(*args, **kwargs):
        apply_called["count"] += 1
        return {"applied": 0, "skipped": 0, "drifted": 0, "failed": 0}

    with patch("nuclea_modeler.backend.core.migrations.apply_migrations", side_effect=fake_apply):
        with patch("nuclea_modeler.backend.core.migrations.find_migrations_dir") as fake_dir:
            fake_dir.return_value.exists.return_value = True
            with patch("databricks.sdk.WorkspaceClient") as ws:
                ws.return_value.statement_execution = MagicMock()
                _maybe_run_startup_migrations(MagicMock())

    assert apply_called["count"] == 1


# ─── Failure handling — boot resiliente ─────────────────────────────────────


def test_apply_failure_does_not_raise(monkeypatch):
    """Falha em apply_migrations NÃO propaga — operator investiga via CLI.
    Esse é o contrato crítico: app sobe mesmo com schema problemático,
    /readyz reflete o estado real."""
    monkeypatch.setenv("NUCLEA_MIGRATIONS_AUTO_APPLY", "true")

    with patch(
        "nuclea_modeler.backend.core.migrations.apply_migrations",
        side_effect=RuntimeError("oops"),
    ):
        with patch("nuclea_modeler.backend.core.migrations.find_migrations_dir") as fake_dir:
            fake_dir.return_value.exists.return_value = True
            with patch("databricks.sdk.WorkspaceClient") as ws:
                ws.return_value.statement_execution = MagicMock()
                # Deve completar sem raise — log.error mas não exception
                _maybe_run_startup_migrations(MagicMock())


def test_missing_directory_logs_warning_not_error(monkeypatch):
    """Se NUCLEA_MIGRATIONS_DIR não existe, função emite warning sem abortar."""
    monkeypatch.setenv("NUCLEA_MIGRATIONS_AUTO_APPLY", "true")

    apply_called = {"count": 0}

    def fake_apply(*args, **kwargs):
        apply_called["count"] += 1
        return {"applied": 0, "skipped": 0, "drifted": 0, "failed": 0}

    with patch("nuclea_modeler.backend.core.migrations.apply_migrations", side_effect=fake_apply):
        with patch("nuclea_modeler.backend.core.migrations.find_migrations_dir") as fake_dir:
            fake_dir.return_value.exists.return_value = False
            _maybe_run_startup_migrations(MagicMock())

    # Não chamou apply porque directory não existia
    assert apply_called["count"] == 0
