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
    crypto._last_error = None
    yield
    crypto._cached_key = None
    crypto._last_error = None


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


# ─── v1.0076: ajuda ACIONÁVEL quando a chave não existe ──────────────────────
# Caso real: o cliente, no workspace DELE, tentou salvar uma conexão e recebeu só
# "Configure o secret … e o READ do SP do app no scope" — sem saber o que rodar
# nem qual SP. A mensagem agora traz causa + comandos com scope/SP preenchidos.


class PermissionDenied(Exception):
    """Mesmo NOME da exceção do databricks.sdk.errors (o mapeamento é por nome)."""


class _RaisingWS:
    def __init__(self, exc: Exception, client_id: str | None = None):
        class _Secrets:
            def get_secret(_self, scope, key):
                raise exc

        self.secrets = _Secrets()
        self.config = type("C", (), {"client_id": client_id})()


def test_help_traz_comandos_com_scope_e_sp_preenchidos():
    msg = crypto.missing_key_help("meu-scope", "sp-123", "PermissionDenied")
    assert "Causa provável: o Service Principal do app não tem permissão READ" in msg
    assert "databricks secrets create-scope meu-scope" in msg
    assert "databricks secrets put-secret meu-scope conn_enc_key" in msg
    assert "databricks secrets put-acl meu-scope sp-123 READ" in msg
    assert "não precisa reiniciar" in msg
    # com o SP conhecido, não manda o usuário procurá-lo
    assert "service_principal_client_id" not in msg


def test_help_sem_sp_conhecido_explica_como_achar():
    msg = crypto.missing_key_help("nuclea-modeler", None, None)
    assert "put-acl nuclea-modeler <CLIENT_ID_DO_SP_DO_APP> READ" in msg
    assert "service_principal_client_id" in msg
    assert "Causa provável" not in msg  # sem erro registrado, não inventa causa


def test_help_erro_desconhecido_mostra_a_classe():
    msg = crypto.missing_key_help("s", "sp", "TimeoutError")
    assert "falha ao ler o secret (TimeoutError)" in msg


def test_falha_registra_a_causa_e_sp_vem_do_client(monkeypatch):
    monkeypatch.delenv("NUCLEA_CONN_ENC_KEY", raising=False)
    ws = _RaisingWS(PermissionDenied("no READ"), client_id="sp-abc")
    assert crypto.is_configured(ws) is False
    assert crypto.last_error() == "PermissionDenied"
    assert crypto.app_sp_client_id(ws) == "sp-abc"


def test_sp_client_id_cai_na_env_do_apps(monkeypatch):
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "sp-env")
    assert crypto.app_sp_client_id(object()) == "sp-env"


def test_falha_nao_e_cacheada_dispensa_restart(monkeypatch):
    # Promessa feita na mensagem: depois de criar secret+grant, basta salvar de
    # novo. Só o SUCESSO é cacheado — a falha anterior não "gruda".
    monkeypatch.delenv("NUCLEA_CONN_ENC_KEY", raising=False)
    assert crypto.is_configured(_RaisingWS(PermissionDenied("x"))) is False
    key = Fernet.generate_key().decode()
    assert crypto.is_configured(_FakeWS(key)) is True
    assert crypto.last_error() is None
