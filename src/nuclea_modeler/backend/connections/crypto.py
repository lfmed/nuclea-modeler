"""Criptografia em repouso das senhas de conexão (Módulo 1, v1.0058).

Contexto / porquê
-----------------
A partir da rodada 8 o cliente cadastra conexões de banco de forma self-service:
digita URL, usuário e **senha** direto no app (ver `connections/router.py`). A
senha é dado sensível do cliente dele e NÃO pode ficar em texto plano na tabela
Delta `connections` (que, inclusive, é exibida na UI via `config_json`).

Decisão (aprovada): cifrar a senha **em repouso** com Fernet (AES-128-CBC +
HMAC-SHA256, da lib `cryptography`), usando UMA chave-mestra do app. A chave vive
num Databricks Secret (`nuclea-modeler/conn_enc_key`) injetado como a env
`NUCLEA_CONN_ENC_KEY` (ver `app.yml`). Assim:
- Uma única chave habilita conexões self-service ilimitadas (sem redeploy por
  conexão, ao contrário do modelo antigo de "chave de secret por conexão").
- A senha só é decifrada no instante do teste/uso da conexão.
- Sem a chave (env ausente), o app **falha fechado** ao cifrar — nunca grava
  senha em claro.

Gotchas para quem mantém depois
--------------------------------
- `cryptography` é importado de forma **lazy** para não quebrar `py_compile`/boot
  caso o wheel não esteja presente (padrão dos testers). Em produção ele está nas
  deps (`requirements.txt`), com wheel manylinux.
- Uma Fernet key é `base64.urlsafe_b64encode(32 bytes)`. Gere com:
  `python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
  (não precisa da lib `cryptography` só para gerar).
- Rotação de chave: dá para evoluir para `MultiFernet` (lista de chaves) sem mudar
  o schema — os tokens carregam o timestamp e a 1ª chave que decifra vence. Hoje é
  chave única para manter simples.
"""
from __future__ import annotations

import os

from ..core._config import logger

_ENV_KEY = "NUCLEA_CONN_ENC_KEY"


def is_configured() -> bool:
    """True se a chave-mestra está presente no ambiente."""
    return bool(os.getenv(_ENV_KEY))


def _fernet():
    """Instancia um Fernet a partir da env. Erros são explícitos e acionáveis.

    Import lazy de `cryptography` para não falhar no boot/py_compile quando o
    wheel não estiver instalado (mesmo racional dos drivers em `testers.py`).
    """
    key = os.getenv(_ENV_KEY)
    if not key:
        raise RuntimeError(
            f"{_ENV_KEY} não configurada: defina o Databricks Secret "
            "'nuclea-modeler/conn_enc_key' e o recurso correspondente no app.yml "
            "para cifrar/decifrar senhas de conexão."
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
        # Chave malformada (não é uma Fernet key base64 de 32 bytes).
        raise RuntimeError(
            f"{_ENV_KEY} inválida: esperado uma Fernet key "
            "(base64 urlsafe de 32 bytes)."
        ) from exc


def encrypt(plaintext: str) -> str:
    """Cifra uma senha em claro → token Fernet (str). Falha fechado sem a chave."""
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(token: str) -> str:
    """Decifra um token Fernet → senha em claro. Levanta se o token for inválido.

    Não logamos o valor; apenas um aviso genérico em caso de falha, pois isso
    normalmente indica troca de chave ou dado corrompido.
    """
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.warning(f"[connections] falha ao decifrar senha (token inválido?): {type(exc).__name__}")
        raise
