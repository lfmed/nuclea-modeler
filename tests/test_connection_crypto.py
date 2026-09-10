"""Testes da cifra em repouso das senhas de conexão (v1.0058/v1.0059, rodada 8).

Exercita o round-trip real texto→cifra→texto, o fallback de resolução da chave
(env override → Databricks Secrets via SP) e as falhas ESPERADAS (chave ausente,
chave trocada, chave malformada) — que garantem que nunca gravamos/usamos senha em
claro por engano. Ver connections/crypto.py e migration 022.
"""
from __future__ import annotations

import base64

import pytest

# cryptography é dependência de runtime (requirements.txt); pula o módulo se por
# acaso não estiver instalado no ambiente de teste, em vez de quebrar a coleta.
pytest.importorskip("cryptography")
from cryptography.fernet import Fernet  # noqa: E402

from nuclea_modeler.backend.connections import crypto  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_key_cache():
    """A chave é cacheada em memória (evita reler o Secret). Zera entre testes
    para isolar cada cenário (senão a 1ª chave resolvida "gruda")."""
    crypto._cached_key = None
    yield
    crypto._cached_key = None


class _FakeWS:
    """WorkspaceClient fake cujo secrets.get_secret devolve a chave em base64
    (como o Databricks Secrets faz de verdade)."""

    def __init__(self, key_plain: str | None):
        self._key = key_plain

        class _Secrets:
            def get_secret(_self, scope, key):
                resp = type("R", (), {})()
                resp.value = base64.b64encode(self._key.encode()).decode() if self._key else None
                return resp

        self.secrets = _Secrets()


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


def test_resolves_from_secrets_when_env_absent(monkeypatch):
    """Sem env, resolve a chave via Databricks Secrets usando o SP (fallback v1.0059)."""
    monkeypatch.delenv("NUCLEA_CONN_ENC_KEY", raising=False)
    ws = _FakeWS(Fernet.generate_key().decode())
    assert crypto.is_configured(ws) is True
    token = crypto.encrypt("abc", ws)
    assert crypto.decrypt(token, ws) == "abc"


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("NUCLEA_CONN_ENC_KEY", raising=False)
    # sem env e sem ws (ou ws sem o secret) → não configurada
    assert crypto.is_configured() is False
    assert crypto.is_configured(_FakeWS(None)) is False
    with pytest.raises(RuntimeError):
        crypto.encrypt("qualquer")


def test_wrong_key_cannot_decrypt(monkeypatch):
    monkeypatch.setenv("NUCLEA_CONN_ENC_KEY", Fernet.generate_key().decode())
    token = crypto.encrypt("abc")
    # Troca a chave (e zera o cache) — decifrar o token antigo deve falhar.
    crypto._cached_key = None
    monkeypatch.setenv("NUCLEA_CONN_ENC_KEY", Fernet.generate_key().decode())
    with pytest.raises(Exception):
        crypto.decrypt(token)


def test_malformed_key_raises_clear_error(monkeypatch):
    monkeypatch.setenv("NUCLEA_CONN_ENC_KEY", "isto-nao-e-uma-fernet-key")
    with pytest.raises(RuntimeError):
        crypto.encrypt("x")
