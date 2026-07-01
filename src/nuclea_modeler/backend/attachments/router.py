"""Anexos — endpoints HTTP (upload/list/download/delete). Pedido do cliente #7.

Bytes vão para um UC Volume via o service principal do app (Dependencies.Client);
o e-mail do ator e o RBAC saem do usuário (Dependencies.UserClient).
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from ..._metadata import api_prefix
from ..core import Dependencies
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import (
    ROLE_ADMIN,
    ROLE_DATA_ARCHITECT,
    ROLE_DATA_STEWARD,
    require_role,
)
from .models import AttachmentListOut, AttachmentOut
from .service import (
    delete_attachment,
    download_bytes,
    get_attachment,
    list_attachments,
    save_attachment,
)

router = APIRouter(prefix=f"{api_prefix}/attachments", tags=["attachments"])

# Mutações (anexar/remover) exigem papel de curadoria; leitura é livre p/ logados.
_MUTATORS = (ROLE_DATA_STEWARD, ROLE_DATA_ARCHITECT, ROLE_ADMIN)


@router.post("", response_model=AttachmentOut, operation_id="uploadAttachment")
async def upload_attachment(
    sql: SqlDependency,
    ws: Dependencies.Client,
    user_ws: Dependencies.UserClient,
    owner_kind: str = Form(...),
    owner_id: str = Form(...),
    description: str | None = Form(None),
    file: UploadFile = File(...),
) -> AttachmentOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *_MUTATORS)
    data = await file.read()
    return save_attachment(
        ws,
        sql,
        owner_kind=owner_kind,
        owner_id=owner_id,
        filename=file.filename or "arquivo",
        content_type=file.content_type,
        data=data,
        description=description,
        actor=actor,
    )


@router.get("", response_model=list[AttachmentListOut], operation_id="listAttachments")
def list_attachments_endpoint(
    sql: SqlDependency,
    owner_kind: str = Query(...),
    owner_id: str = Query(...),
) -> list[AttachmentListOut]:
    return list_attachments(sql, owner_kind, owner_id)


@router.get("/{attachment_id}/download", operation_id="downloadAttachment")
def download_attachment_endpoint(
    attachment_id: str,
    sql: SqlDependency,
    ws: Dependencies.Client,
) -> Response:
    meta = get_attachment(sql, attachment_id)
    if not meta:
        raise HTTPException(404, "anexo não encontrado")
    data = download_bytes(ws, sql, attachment_id)
    filename = meta.original_filename or "arquivo"
    return Response(
        content=data,
        media_type=meta.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.delete("/{attachment_id}", operation_id="deleteAttachment")
def delete_attachment_endpoint(
    attachment_id: str,
    sql: SqlDependency,
    ws: Dependencies.Client,
    user_ws: Dependencies.UserClient,
) -> dict:
    require_role(sql, _current_email(user_ws), *_MUTATORS)
    delete_attachment(ws, sql, attachment_id)
    return {"ok": True}
