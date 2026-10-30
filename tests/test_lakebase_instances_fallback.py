"""Listagem de instâncias Lakebase com fallback para o SP (rodada 9, item 1).

Contexto: em produção `GET /api/lakebase/instances` dava 403 "Invalid scope,
required scopes: postgres" porque o token OBO do usuário não tinha o scope
`postgres`. A rota agora tenta o usuário e, SÓ em erro de scope, cai no service
principal do app. Outros erros continuam virando 500 (não mascarar falhas reais).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from nuclea_modeler.backend.lakebase import router as lk_router


def _inst(name: str):
    return SimpleNamespace(
        name=name, state=None, capacity=None, pg_version=None,
        read_write_dns=f"{name}.db", uid=f"uid-{name}",
    )


class _WS:
    """WorkspaceClient fake: `database.list_database_instances` devolve ou levanta."""

    def __init__(self, result=None, exc: Exception | None = None):
        def _list():
            if exc is not None:
                raise exc
            return result or []

        self.database = SimpleNamespace(list_database_instances=_list)


_SCOPE_ERR = RuntimeError(
    "unable to parse response ... < 403 Forbidden < Invalid scope, required scopes: postgres"
)


def test_usa_token_do_usuario_quando_funciona():
    out = lk_router.list_instances(_WS([_inst("u1")]), _WS([_inst("sp1")]))
    assert [i.instance_name for i in out] == ["u1"]


def test_cai_no_sp_quando_falta_scope_postgres():
    out = lk_router.list_instances(_WS(exc=_SCOPE_ERR), _WS([_inst("JDBCTESTLAKEBASE")]))
    assert [i.instance_name for i in out] == ["JDBCTESTLAKEBASE"]
    assert out[0].state == "UNKNOWN"


def test_erro_que_nao_e_de_scope_nao_cai_no_sp():
    with pytest.raises(HTTPException) as ei:
        lk_router.list_instances(_WS(exc=RuntimeError("timeout")), _WS([_inst("sp1")]))
    assert ei.value.status_code == 500
    assert "timeout" in ei.value.detail


def test_sp_tambem_falhando_devolve_mensagem_clara():
    with pytest.raises(HTTPException) as ei:
        lk_router.list_instances(_WS(exc=_SCOPE_ERR), _WS(exc=RuntimeError("sp sem acesso")))
    assert ei.value.status_code == 500
    assert "postgres" in ei.value.detail
    assert "sp sem acesso" in ei.value.detail
