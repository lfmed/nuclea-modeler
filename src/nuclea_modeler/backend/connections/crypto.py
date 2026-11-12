"""Criptografia em repouso das senhas de conexão (Módulo 1, v1.0058+).

Contexto / porquê
-----------------
A partir da rodada 8 o cliente cadastra conexões de banco de forma self-service:
digita URL, usuário e **senha** direto no app (ver `connections/router.py`). A
senha é dado sensível do cliente dele e NÃO pode ficar em texto plano na tabela
Delta `connections` (que, inclusive, é exibida na UI via `config_json`).

Decisão (aprovada): cifrar a senha **em repouso** com Fernet (AES-128-CBC +
HMAC-SHA256, da lib `cryptography`), usando UMA chave-mestra do app guardada no
Databricks Secret `nuclea-modeler/conn_enc_key`.

Como a chave é resolvida (v1.0059 — corrigido após validação ao vivo)
--------------------------------------------------------------------
1. **env `NUCLEA_CONN_ENC_KEY`** (override; usado em testes e como escape hatch);
2. senão, **lida de Databricks Secrets via o Service Principal do app** (o mesmo
   `WorkspaceClient` que os testers usam para ler secrets), e cacheada em memória.

Por que NÃO via `app.yml`/`valueFrom`: validando no app deployado, a injeção de
env por recurso `secret` do app.yml NÃO acontecia no `apps deploy` (o recurso não
chega a ser registrado) e mexer nos recursos do app é arriscado (incidente do
warehouse). Ler via SDK (com o SP tendo READ no scope — grant aditivo) é
autocontido e de baixo risco. Ver [[feedback-deploy-never-bundle-create]].

Gotchas para quem mantém depois
--------------------------------
- `cryptography` é importado de forma **lazy** para não quebrar `py_compile`/boot.
  Em produção está nas deps (`requirements.txt`), com wheel manylinux.
- Uma Fernet key é `base64.urlsafe_b64encode(32 bytes)`. Gere com:
  `python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
- O Databricks Secrets devolve o valor em **base64** — decodificamos uma vez para
  recuperar a Fernet key original (mesmo padrão de `testers._read_secret`).
- Rotação de chave: evoluir para `MultiFernet` sem mudar schema (tokens carregam
  timestamp; a 1ª chave que decifra vence).
"""
from __future__ import annotations

import base64
import os
from typing import Any

from ..core._config import logger
from ..core._nuclea_config import get_settings

_ENV_KEY = "NUCLEA_CONN_ENC_KEY"
_SECRET_KEY_NAME = "conn_enc_key"

# Cache em memória da chave resolvida (evita reler o Secret a cada operação).
# Só o SUCESSO é cacheado: enquanto a chave não existir, cada tentativa relê o
# Secret — por isso o cliente que acabou de criar o secret/grant NÃO precisa
# reiniciar nem re-deployar o app (v1.0076, documentado na mensagem de ajuda).
_cached_key: str | None = None

# Nome da classe da última exceção ao ler o Secret (ex.: "PermissionDenied",
# "ResourceDoesNotExist"). Usado só para a mensagem de AJUDA dizer a causa
# provável (`missing_key_help`). Não é estado de negócio — sem lock de propósito.
_last_error: str | None = None


def _read_from_secrets(ws: Any) -> str | None:
    """Lê a chave-mestra de Databricks Secrets via o WorkspaceClient (SP do app)."""
    if ws is None:
        return None
    global _last_error
    scope = get_settings().secrets_scope
    try:
        resp = ws.secrets.get_secret(scope=scope, key=_SECRET_KEY_NAME)
        val = getattr(resp, "value", None)
        if not val:
            _last_error = "EmptySecret"
            return None
        _last_error = None
        try:
            return base64.b64decode(val).decode("utf-8")
        except Exception:
            return val
    except Exception as exc:
        _last_error = type(exc).__name__
        logger.warning(
            f"[connections] chave de cifra indisponível via Secrets "
            f"({scope}/{_SECRET_KEY_NAME}): {type(exc).__name__}"
        )
        return None


def _resolve_key(ws: Any = None) -> str | None:
    """Resolve a Fernet key: env (override) → Databricks Secrets (via SP). Cacheia."""
    global _cached_key
    if _cached_key:
        return _cached_key
    key = os.getenv(_ENV_KEY)
    if not key:
        key = _read_from_secrets(ws)
    if key:
        _cached_key = key
    return key


def is_configured(ws: Any = None) -> bool:
    """True se a chave-mestra pôde ser resolvida (env ou Secrets)."""
    return _resolve_key(ws) is not None


def last_error() -> str | None:
    """Classe da última falha ao ler a chave do Secret (None = sem falha)."""
    return _last_error


def app_sp_client_id(ws: Any = None) -> str | None:
    """Client ID (application_id) do Service Principal do app, se descobrível.

    No Databricks Apps o runtime injeta `DATABRICKS_CLIENT_ID` (credencial M2M
    do SP do app); o `WorkspaceClient` do app expõe o mesmo em `config.client_id`.
    Serve para a mensagem de ajuda já trazer o comando `put-acl` PREENCHIDO.
    """
    cid = getattr(getattr(ws, "config", None), "client_id", None)
    return cid or os.getenv("DATABRICKS_CLIENT_ID") or None


# Causa provável por classe de exceção do SDK (databricks.sdk.errors). A API de
# Secrets responde RESOURCE_DOES_NOT_EXIST tanto p/ scope quanto p/ chave
# inexistentes; PERMISSION_DENIED quando o SP não tem READ no scope.
_CAUSES = {
    "PermissionDenied": "o Service Principal do app não tem permissão READ no scope.",
    "Unauthenticated": "o Service Principal do app não conseguiu se autenticar.",
    "ResourceDoesNotExist": "o scope ou o secret não existe neste workspace.",
    "NotFound": "o scope ou o secret não existe neste workspace.",
    "EmptySecret": "o secret existe, mas está vazio.",
}


def missing_key_help(scope: str, sp_client_id: str | None, error: str | None) -> str:
    """Mensagem ACIONÁVEL quando a chave de cifra não pôde ser resolvida (v1.0076).

    Antes a mensagem era só "Configure o secret 'nuclea-modeler/conn_enc_key' e o
    READ do SP do app no scope" — o cliente (no workspace DELE) não sabia o que
    rodar nem qual era o SP. Agora: causa provável + os 4 comandos da CLI com o
    scope REAL (`NUCLEA_SECRETS_SCOPE`) e o client ID do SP já preenchidos, e o
    aviso de que não precisa reiniciar (só o sucesso é cacheado, ver acima).
    Função pura — testada em `tests/test_conn_crypto_help.py`.
    """
    cause = _CAUSES.get(error or "", f"falha ao ler o secret ({error})." if error else "")
    sp = sp_client_id or "<CLIENT_ID_DO_SP_DO_APP>"
    lines = [
        "Chave de cifra indisponível — a senha não foi salva (o app nunca grava "
        "senha em texto puro).",
    ]
    if cause:
        lines.append(f"Causa provável: {cause}")
    lines += [
        "",
        "Como resolver (um admin do workspace roda na CLI do Databricks):",
        f"  1) databricks secrets create-scope {scope}    # pule se já existir",
        "  2) KEY=$(python3 -c \"import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())\")",
        f"     databricks secrets put-secret {scope} {_SECRET_KEY_NAME} --string-value \"$KEY\"",
        f"  3) databricks secrets put-acl {scope} {sp} READ",
    ]
    if not sp_client_id:
        lines.append(
            "     (client ID do SP: databricks apps get <nome-do-app> → service_principal_client_id)"
        )
    lines += [
        "",
        "Depois é só salvar de novo — não precisa reiniciar nem re-deployar o app.",
        "Atenção: não troque nem apague essa chave depois; senhas já salvas deixariam "
        "de abrir (seria preciso recadastrá-las).",
    ]
    return "\n".join(lines)


def _fernet(ws: Any = None):
    """Instancia um Fernet a partir da chave resolvida. Erros são acionáveis.

    Import lazy de `cryptography` para não falhar no boot/py_compile quando o
    wheel não estiver instalado (mesmo racional dos drivers em `testers.py`).
    """
    key = _resolve_key(ws)
    if not key:
        raise RuntimeError(
            "chave de cifra de conexão indisponível: defina a env "
            f"{_ENV_KEY} OU o Databricks Secret 'nuclea-modeler/{_SECRET_KEY_NAME}' "
            "(e conceda READ ao SP do app no scope)."
        )
    try:
        from cryptography.fernet import Fernet  # import lazy proposital
    except ImportError as exc:  # pragma: no cover - deps garantem em prod
        raise RuntimeError(
            "biblioteca 'cryptography' indisponível no runtime (necessária para "
            "cifrar senhas de conexão)."
        ) from exc
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "chave de cifra inválida: esperado uma Fernet key "
            "(base64 urlsafe de 32 bytes)."
        ) from exc


def encrypt(plaintext: str, ws: Any = None) -> str:
    """Cifra uma senha em claro → token Fernet (str). Falha fechado sem a chave."""
    return _fernet(ws).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str, ws: Any = None) -> str:
    """Decifra um token Fernet → senha em claro. Levanta se o token for inválido."""
    try:
        return _fernet(ws).decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.warning(f"[connections] falha ao decifrar senha (token inválido?): {type(exc).__name__}")
        raise
