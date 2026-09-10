"""Contrato dos models de conexão (v1.0058, rodada 8).

Trava por teste as duas invariantes de segurança da rodada 8:
1) ConnectionOut NUNCA expõe a senha (nem em claro `password`, nem o cifrado
   `enc_password`) — só o booleano `has_password`.
2) ConnectionIn aceita `password` (write-only) para o cliente digitar a senha.
"""
from __future__ import annotations

from nuclea_modeler.backend.connections.models import ConnectionIn, ConnectionOut


def test_connection_out_never_exposes_password():
    fields = set(ConnectionOut.model_fields.keys())
    assert "password" not in fields, "ConnectionOut não pode devolver a senha em claro"
    assert "enc_password" not in fields, "ConnectionOut não pode devolver o cifrado"
    assert "has_password" in fields, "ConnectionOut deve indicar se há senha via has_password"


def test_connection_in_accepts_writeonly_password():
    c = ConnectionIn(
        alias="DW",
        environment="HINT",
        system_id="sys-1",
        connection_type="DATABASE",
        config={"engine": "POSTGRES", "host": "h", "database": "d", "username": "u"},
        password="secret",
    )
    assert c.password == "secret"
    # username fica no config (não é sigiloso); senha é campo à parte.
    assert c.config["username"] == "u"


def test_connection_in_password_optional():
    c = ConnectionIn(
        alias="R",
        environment="HINT",
        system_id="sys-1",
        connection_type="REST",
        config={"base_url": "https://x"},
    )
    assert c.password is None
