"""Serviço de anexos — bytes em UC Volume, metadados em Delta.

Fluxo:
  - upload: grava o arquivo em /Volumes/<cat>/<schema>/attachments/<kind>/<owner>/<id>__<nome>
    (via app SP, que precisa de WRITE VOLUME) e insere a linha de metadados.
  - list/get: lê os metadados da tabela Delta.
  - download: baixa os bytes do Volume.
  - delete: apaga o arquivo do Volume (best-effort) e remove a linha.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

from databricks.sdk import WorkspaceClient
from fastapi import HTTPException

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .models import AttachmentListOut, AttachmentOut

# Cap de tamanho por arquivo (proteção contra DoS / estouro de memória).
ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB

_ALLOWED_KINDS = {"entity", "schema", "diagram", "system"}
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")

_ATT_COLS = [
    "attachment_id", "owner_kind", "owner_id", "original_filename",
    "mime_type", "file_size_bytes", "volume_path", "description",
    "created_at", "created_by",
]


def _sanitize_filename(name: str) -> str:
    """Remove separadores de path e caracteres perigosos do nome do arquivo."""
    base = (name or "arquivo").replace("\\", "/").split("/")[-1].strip()
    safe = re.sub(r"[^A-Za-z0-9._\- ]+", "_", base).strip() or "arquivo"
    return safe[:200]


def _validate_owner(owner_kind: str, owner_id: str) -> None:
    if owner_kind not in _ALLOWED_KINDS:
        raise HTTPException(400, f"owner_kind inválido: {owner_kind}")
    if not _ID_RE.match(owner_id or ""):
        raise HTTPException(400, "owner_id inválido")


def _volume_base() -> str:
    s = get_settings()
    return f"/Volumes/{s.catalog}/{s.schema_}/attachments"


# Cache de "Volume já garantido" por processo — evita tentar criar a cada upload.
_volume_ready = False


def _ensure_volume(ws: WorkspaceClient) -> None:
    """Cria o Volume gerenciado de anexos sob demanda (idempotente).

    Deliberadamente FORA das migrations: criar Volume exige grant CREATE VOLUME
    que o SP pode não ter; fazê-lo no boot derrubaria o app inteiro. Aqui, a
    falta de permissão vira um erro só do recurso de anexos (HTTP 502 com
    orientação), sem afetar o resto do app.
    """
    global _volume_ready
    if _volume_ready:
        return
    s = get_settings()
    try:
        from databricks.sdk.service.catalog import VolumeType

        ws.volumes.create(
            catalog_name=s.catalog,
            schema_name=s.schema_,
            name="attachments",
            volume_type=VolumeType.MANAGED,
        )
        _volume_ready = True
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "already exists" in msg or "exists" in msg:
            _volume_ready = True
            return
        raise HTTPException(
            502,
            "Volume de anexos indisponível — peça ao admin: "
            f"GRANT CREATE VOLUME ON SCHEMA {s.catalog}.{s.schema_} ao SP do app. ({exc})",
        ) from exc


def _row_to_out(r: list) -> AttachmentOut:
    return AttachmentOut(
        attachment_id=r[0],
        owner_kind=r[1],
        owner_id=r[2],
        original_filename=r[3],
        mime_type=r[4],
        file_size_bytes=int(r[5]) if r[5] is not None else None,
        description=r[7],
        created_at=r[8],
        created_by=r[9],
    )


def save_attachment(
    ws: WorkspaceClient,
    sql: Sql,
    *,
    owner_kind: str,
    owner_id: str,
    filename: str,
    content_type: str | None,
    data: bytes,
    description: str | None,
    actor: str,
) -> AttachmentOut:
    _validate_owner(owner_kind, owner_id)
    if not data:
        raise HTTPException(400, "arquivo vazio")
    if len(data) > ATTACHMENT_MAX_BYTES:
        raise HTTPException(
            413, f"arquivo excede o limite de {ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB"
        )

    s = get_settings()
    attachment_id = delta.new_id("att-")
    safe_name = _sanitize_filename(filename)
    volume_path = f"{_volume_base()}/{owner_kind}/{owner_id}/{attachment_id}__{safe_name}"

    # Garante o Volume (sob demanda — ver _ensure_volume) antes de gravar.
    _ensure_volume(ws)
    # Grava os bytes no Volume (app SP precisa de WRITE VOLUME).
    try:
        ws.files.upload(volume_path, io.BytesIO(data), overwrite=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"falha ao gravar o arquivo no Volume: {exc}") from exc

    created_at = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("attachments"),
        {
            "attachment_id": attachment_id,
            "owner_kind": owner_kind,
            "owner_id": owner_id,
            "original_filename": safe_name,
            "mime_type": content_type,
            "file_size_bytes": len(data),
            "volume_path": volume_path,
            "description": description,
            "created_at": created_at,
            "created_by": actor,
        },
    )
    return AttachmentOut(
        attachment_id=attachment_id,
        owner_kind=owner_kind,  # type: ignore[arg-type]
        owner_id=owner_id,
        original_filename=safe_name,
        mime_type=content_type,
        file_size_bytes=len(data),
        description=description,
        created_at=created_at,
        created_by=actor,
    )


def list_attachments(sql: Sql, owner_kind: str, owner_id: str) -> list[AttachmentListOut]:
    _validate_owner(owner_kind, owner_id)
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {', '.join(_ATT_COLS)}
        FROM {s.fq_table('attachments')}
        WHERE owner_kind = :k AND owner_id = :o
        ORDER BY created_at DESC
        """,
        [delta.param("k", owner_kind), delta.param("o", owner_id)],
    )
    return [
        AttachmentListOut(
            attachment_id=r[0],
            owner_kind=r[1],
            owner_id=r[2],
            original_filename=r[3],
            mime_type=r[4],
            file_size_bytes=int(r[5]) if r[5] is not None else None,
            description=r[7],
            created_at=r[8],
            created_by=r[9],
        )
        for r in rows
    ]


def get_attachment(sql: Sql, attachment_id: str) -> AttachmentOut | None:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_ATT_COLS)} FROM {s.fq_table('attachments')} "
        f"WHERE attachment_id = :id",
        [delta.param("id", attachment_id)],
    )
    return _row_to_out(row) if row else None


def _volume_path_of(sql: Sql, attachment_id: str) -> str | None:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT volume_path FROM {s.fq_table('attachments')} WHERE attachment_id = :id",
        [delta.param("id", attachment_id)],
    )
    return row[0] if row else None


def download_bytes(ws: WorkspaceClient, sql: Sql, attachment_id: str) -> bytes:
    path = _volume_path_of(sql, attachment_id)
    if not path:
        raise HTTPException(404, "anexo não encontrado")
    try:
        resp = ws.files.download(path)
        return resp.contents.read()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"falha ao ler o arquivo do Volume: {exc}") from exc


def delete_attachment(ws: WorkspaceClient, sql: Sql, attachment_id: str) -> None:
    s = get_settings()
    path = _volume_path_of(sql, attachment_id)
    if not path:
        raise HTTPException(404, "anexo não encontrado")
    # Apaga o arquivo do Volume (best-effort — não bloqueia a remoção do metadado).
    try:
        ws.files.delete(path)
    except Exception:  # noqa: BLE001
        pass
    delta.delete_by_id(sql, s.fq_table("attachments"), "attachment_id", attachment_id)
