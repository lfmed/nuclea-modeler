"""Tests para rbac/service.py — get_user_roles, has_role, require_role.

Mocks delta.fetch_all_params para retornar roles fake. Não toca Sql real.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from nuclea_modeler.backend.rbac import service as rbac
from nuclea_modeler.backend.rbac.service import (
    ROLE_ADMIN,
    ROLE_DATA_ARCHITECT,
    ROLE_DATA_STEWARD,
    TICKET_APPLIERS,
    TICKET_APPROVERS,
    get_user_roles,
    has_role,
    require_role,
)


@pytest.fixture
def patched_rbac(monkeypatch):
    """Patch settings + delta.fetch_all_params para retornar roles capturadas."""
    fake_settings = type("S", (), {})()
    fake_settings.catalog = "cat"
    fake_settings.schema_ = "sch"
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(rbac, "get_settings", lambda: fake_settings)

    state = {"return_roles": []}

    def fake_fetch_all_params(sql_dep, query, params=None):
        # Verifica que o query usa parametro nomeado :user_email
        assert ":user_email" in query
        return [[r] for r in state["return_roles"]]

    from nuclea_modeler.backend.core import delta
    monkeypatch.setattr(delta, "fetch_all_params", fake_fetch_all_params)
    return state


# ─── get_user_roles ─────────────────────────────────────────────────────────


def test_get_user_roles_returns_role_names(patched_rbac):
    patched_rbac["return_roles"] = ["ADMIN", "DATA_ARCHITECT"]
    roles = get_user_roles(MagicMock(), "alice@nuclea")
    assert roles == ["ADMIN", "DATA_ARCHITECT"]


def test_get_user_roles_empty_for_empty_email(patched_rbac):
    """Email vazio NÃO faz query — retorna lista vazia direta."""
    roles = get_user_roles(MagicMock(), "")
    assert roles == []


def test_get_user_roles_none_email_returns_empty(patched_rbac):
    roles = get_user_roles(MagicMock(), None)
    assert roles == []


def test_get_user_roles_empty_when_db_returns_nothing(patched_rbac):
    patched_rbac["return_roles"] = []
    roles = get_user_roles(MagicMock(), "novo@nuclea")
    assert roles == []


# ─── has_role ───────────────────────────────────────────────────────────────


def test_has_role_true_when_user_has_required(patched_rbac):
    patched_rbac["return_roles"] = ["DATA_ARCHITECT", "DATA_STEWARD"]
    assert has_role(MagicMock(), "alice", ROLE_DATA_ARCHITECT) is True


def test_has_role_true_with_multiple_required_any_match(patched_rbac):
    """Has-role é OR — basta ter UMA das roles passadas."""
    patched_rbac["return_roles"] = ["DATA_STEWARD"]
    assert has_role(MagicMock(), "alice", ROLE_ADMIN, ROLE_DATA_STEWARD) is True


def test_has_role_false_when_user_lacks_all(patched_rbac):
    patched_rbac["return_roles"] = ["DATA_ENGINEER"]
    assert has_role(MagicMock(), "bob", ROLE_ADMIN, ROLE_DATA_ARCHITECT) is False


def test_has_role_true_when_no_required(patched_rbac):
    """Sem required = sempre permitido (auth opcional)."""
    patched_rbac["return_roles"] = []
    assert has_role(MagicMock(), "anyone") is True


def test_has_role_false_with_empty_user_email(patched_rbac):
    """Sem email = sem roles = falha em qualquer requirement."""
    patched_rbac["return_roles"] = []
    assert has_role(MagicMock(), "", ROLE_ADMIN) is False


# ─── require_role ───────────────────────────────────────────────────────────


def test_require_role_passes_when_user_has_role(patched_rbac):
    """Não levanta — retorna None."""
    patched_rbac["return_roles"] = [ROLE_ADMIN]
    result = require_role(MagicMock(), "alice", ROLE_ADMIN)
    assert result is None


def test_require_role_raises_403_when_user_lacks(patched_rbac):
    patched_rbac["return_roles"] = ["DATA_ENGINEER"]
    with pytest.raises(HTTPException) as exc_info:
        require_role(MagicMock(), "bob", ROLE_ADMIN, ROLE_DATA_ARCHITECT)
    assert exc_info.value.status_code == 403
    assert "bob" in exc_info.value.detail
    assert "ADMIN" in exc_info.value.detail
    assert "DATA_ARCHITECT" in exc_info.value.detail


def test_require_role_message_lists_all_required(patched_rbac):
    """Error message ajuda o usuário entender o que precisa pedir."""
    patched_rbac["return_roles"] = []
    with pytest.raises(HTTPException) as exc:
        require_role(MagicMock(), "carol", ROLE_ADMIN, ROLE_DATA_STEWARD)
    detail = exc.value.detail
    assert "ADMIN" in detail
    assert "DATA_STEWARD" in detail


# ─── Constantes ─────────────────────────────────────────────────────────────


def test_ticket_approvers_includes_architect_steward_admin():
    """Spec §4.5.x — quem pode aprovar tickets de reconciliação."""
    assert ROLE_DATA_ARCHITECT in TICKET_APPROVERS
    assert ROLE_DATA_STEWARD in TICKET_APPROVERS
    assert ROLE_ADMIN in TICKET_APPROVERS


def test_ticket_appliers_is_more_restrictive_than_approvers():
    """Apply requer ARCHITECT ou ADMIN — STEWARD só aprova."""
    assert set(TICKET_APPLIERS) <= set(TICKET_APPROVERS)
    assert ROLE_DATA_STEWARD not in TICKET_APPLIERS
    assert ROLE_ADMIN in TICKET_APPLIERS
    assert ROLE_DATA_ARCHITECT in TICKET_APPLIERS
