"""Testes da cifra em repouso das senhas de conexão (v1.0058, rodada 8).

Exercita o round-trip real texto→cifra→texto e as falhas ESPERADAS (chave
ausente, chave trocada, chave malformada) — que garantem que nunca gravamos/
usamos senha em claro por engano. Ver connections/crypto.py e migration 022.
"""
from __future__ import annotations

import pytest

# cryptography é dependência de runtime (requirements.txt); pula o módulo se por
# acaso não estiver instalado no ambiente de teste, em vez de quebrar a coleta.
pytest.importorskip("cryptography")
from cryptography.fernet import Fernet  # noqa: E402

from nuclea_modeler.backend.connections import crypto  # noqa: E402


def test_roundtrip_encrypts_and_decrypts(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("NUCLEA_CONN_ENC_KEY", key)
    assert crypto.is_configured() is True

    secret = "s3nh@-do-cliente!"
    token = crypto.encrypt(secret)
    # O cifrado NÃO pode conter o texto plano.
    assert secret not in token
    assert token != secret
    assert crypto.decrypt(token) == secret


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("NUCLEA_CONN_ENC_KEY", raising=False)
    assert crypto.is_configured() is False
    with pytest.raises(RuntimeError):
        crypto.encrypt("qualquer")


def test_wrong_key_cannot_decrypt(monkeypatch):
    monkeypatch.setenv("NUCLEA_CONN_ENC_KEY", Fernet.generate_key().decode())
    token = crypto.encrypt("abc")
    # Troca a chave — decifrar o token antigo deve falhar (não retornar lixo).
    monkeypatch.setenv("NUCLEA_CONN_ENC_KEY", Fernet.generate_key().decode())
    with pytest.raises(Exception):
        crypto.decrypt(token)


def test_malformed_key_raises_clear_error(monkeypatch):
    monkeypatch.setenv("NUCLEA_CONN_ENC_KEY", "isto-nao-e-uma-fernet-key")
    with pytest.raises(RuntimeError):
        crypto.encrypt("x")
