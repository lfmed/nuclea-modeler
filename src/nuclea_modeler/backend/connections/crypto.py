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
_cached_key: str | None = None


def _read_from_secrets(ws: Any) -> str | None:
    """Lê a chave-mestra de Databricks Secrets via o WorkspaceClient (SP do app)."""
    if ws is None:
        return None
    scope = get_settings().secrets_scope
    try:
        resp = ws.secrets.get_secret(scope=scope, key=_SECRET_KEY_NAME)
        val = getattr(resp, "value", None)
        if not val:
            return None
        try:
            return base64.b64decode(val).decode("utf-8")
        except Exception:
            return val
    except Exception as exc:
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
