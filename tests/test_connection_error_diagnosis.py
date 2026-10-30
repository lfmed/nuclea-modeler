"""Diagnóstico de falha de conexão de banco (rodada 9, item 3).

O cliente reportou "não foi possível estabelecer conexão com bases externas" e a
tela só mostrava o texto cru do driver. `classify_db_error` mapeia esse texto
para uma categoria + orientação acionável; `test_database` anexa as duas ao
resultado. As mensagens abaixo são as REAIS (ou o trecho característico) que
cada driver embutido produz — psycopg, oracledb, PyMySQL, python-tds, ibm_db.
"""
from __future__ import annotations

import socket

import pytest

from nuclea_modeler.backend.connections import testers


@pytest.mark.parametrize(
    "message,expected",
    [
        # DNS
        ('failed to resolve host "db.interno": [Errno -2] Name or service not known', "DNS"),
        ("could not translate host name \"x\" to address", "DNS"),
        ("[Errno 8] nodename nor servname provided, or not known", "DNS"),
        # AUTH — inclusive a do pg_hba, que cita "SSL off" mas NÃO é falha de TLS
        ('FATAL:  password authentication failed for user "app"', "AUTH"),
        ('no pg_hba.conf entry for host "1.2.3.4", user "app", database "x", SSL off', "AUTH"),
        ("(1045, \"Access denied for user 'app'@'1.2.3.4' (using password: YES)\")", "AUTH"),
        ("Login failed for user 'app'.", "AUTH"),
        ("ORA-01017: invalid username/password; logon denied", "AUTH"),
        ("SQL30082N  Security processing failed with reason \"24\"", "AUTH"),
        ('FATAL:  role "app" does not exist', "AUTH"),
        # REFUSED
        ("[Errno 111] Connection refused", "REFUSED"),
        ("ORA-12541: TNS:no listener", "REFUSED"),
        # NETWORK (firewall / rede privada)
        ("connection to server at \"10.0.0.5\", port 5432 failed: timeout expired", "NETWORK"),
        ("timed out", "NETWORK"),
        ("ORA-12170: TNS:Connect timeout occurred", "NETWORK"),
        ("SQL30081N  A communication error has been detected", "NETWORK"),
        ("[Errno 113] No route to host", "NETWORK"),
        # SSL
        ("SSL error: certificate verify failed", "SSL"),
        # DATABASE
        ('FATAL:  database "xpto" does not exist', "DATABASE"),
        ("(1049, \"Unknown database 'xpto'\")", "DATABASE"),
        ("ORA-12514: TNS:listener does not currently know of service requested", "DATABASE"),
        # Sem padrão conhecido
        ("algo inesperado aconteceu", "UNKNOWN"),
        ("", "UNKNOWN"),
    ],
)
def test_classify_db_error(message, expected):
    category, hint = testers.classify_db_error(message, 5432)
    assert category == expected
    assert hint  # sempre há uma orientação, mesmo em UNKNOWN


def test_hint_de_rede_cita_a_porta_e_a_rede_privada():
    _, hint = testers.classify_db_error("timed out", 1521)
    assert "1521" in hint
    assert "rede privada" in hint


def test_hint_sem_porta_nao_quebra():
    _, hint = testers.classify_db_error("timed out", None)
    assert "{port}" not in hint


def test_test_database_anexa_categoria_e_hint(monkeypatch):
    def _boom(*_a, **_k):
        raise socket.timeout("timed out")

    monkeypatch.setitem(testers._ENGINE_PROBES, "POSTGRES", _boom)
    out = testers.test_database(
        engine="POSTGRES", config={"host": "db.interno", "port": 5432}, username="u", password="p",
    )
    assert out.status == "failure"
    assert out.error_category == "NETWORK"
    assert "5432" in (out.hint or "")
    # O texto cru do driver continua no `error` (para o DBA/infra).
    assert "timed out" in (out.error or "")


def test_test_database_usa_a_causa_encadeada(monkeypatch):
    """oracledb embrulha o erro de socket (DPY-6005); a causa real está em __cause__."""

    def _boom(*_a, **_k):
        try:
            raise ConnectionRefusedError("[Errno 111] Connection refused")
        except ConnectionRefusedError as inner:
            raise RuntimeError("DPY-6005: cannot connect to database") from inner

    monkeypatch.setitem(testers._ENGINE_PROBES, "ORACLE", _boom)
    out = testers.test_database(engine="ORACLE", config={"host": "h"}, username="u", password="p")
    assert out.error_category == "REFUSED"


def test_driver_indisponivel_tem_categoria_propria(monkeypatch):
    def _boom(*_a, **_k):
        raise testers.DriverUnavailable("driver DB2 (ibm_db) indisponível no runtime")

    monkeypatch.setitem(testers._ENGINE_PROBES, "DB2", _boom)
    out = testers.test_database(engine="DB2", config={"host": "h"}, username="u", password="p")
    assert out.error_category == "DRIVER"
