"""Starlette middleware that persists an audit_log row per mutation.

Captures every non-GET request to /api/* and inserts a row into the
catalog.schema.audit_log Delta table. The middleware must never break the
request flow — failures are logged to stderr and swallowed.
"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from typing import Any

from databricks.sdk import WorkspaceClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql, SqlConfig


_METHOD_TO_ACTION = {
    "POST": "CREATE",
    "PUT": "UPDATE",
    "PATCH": "UPDATE",
    "DELETE": "DELETE",
}

# Bytes — truncate the captured request body to avoid huge audit rows.
_MAX_BODY_BYTES = 4 * 1024

# Path segment that "looks like" an ID (UUID, prefixed id, slug).
_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{6,}$")


class AuditMiddleware(BaseHTTPMiddleware):
    """Insert an audit_log row for every mutating /api/* request."""

    def __init__(self, app, *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        self._sql: Sql | None = None
        self._sql_init_failed = False

    # ------------------------------------------------------------------
    # Lazy SQL client
    # ------------------------------------------------------------------
    def _get_sql(self) -> Sql | None:
        if self._sql is not None:
            return self._sql
        if self._sql_init_failed:
            return None
        try:
            ws = WorkspaceClient()
            cfg = SqlConfig()  # ty: ignore[missing-argument]
            self._sql = Sql(config=cfg, api=ws.statement_execution)
            return self._sql
        except Exception as exc:
            print(f"[audit] Failed to init SQL client: {exc}", file=sys.stderr)
            self._sql_init_failed = True
            return None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path

        should_audit = (
            method in _METHOD_TO_ACTION
            and path.startswith("/api/")
            # don't audit the audit endpoints themselves to avoid recursion
            and not path.startswith("/api/audit")
        )

        body_bytes = b""
        if should_audit:
            try:
                body_bytes = await request.body()
            except Exception:
                body_bytes = b""

            # Make the body available to downstream handlers by re-injecting.
            async def receive_body() -> dict[str, Any]:
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            request._receive = receive_body  # type: ignore[attr-defined]

        started = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)

        if should_audit:
            try:
                self._record(
                    request=request,
                    response=response,
                    method=method,
                    path=path,
                    body_bytes=body_bytes,
                    duration_ms=duration_ms,
                )
            except Exception as exc:  # never break the request
                print(f"[audit] write failed for {method} {path}: {exc}", file=sys.stderr)

        return response

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _record(
        self,
        *,
        request: Request,
        response: Response,
        method: str,
        path: str,
        body_bytes: bytes,
        duration_ms: int,
    ) -> None:
        # Only record successful or client-error mutations? We record everything
        # >= 200 and < 500 to capture failed validation, but skip 5xx since the
        # mutation might not have committed.
        status = int(getattr(response, "status_code", 0) or 0)
        if status >= 500:
            return

        sql = self._get_sql()
        if sql is None:
            return

        # actor
        actor_email = request.headers.get("X-Forwarded-Email") or "anonymous"
        # Prefer the request id stamped by RequestIdMiddleware (kept in a
        # contextvar), then the inbound header, finally a fresh UUID. This keeps
        # logs and audit rows aligned for the same request.
        try:
            from ..core.logging import get_request_id
            request_id = get_request_id() or request.headers.get("X-Request-Id") or uuid.uuid4().hex
        except Exception:
            request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        client_ip = _extract_client_ip(request)
        user_agent = (request.headers.get("user-agent") or "")[:512]

        action = _METHOD_TO_ACTION.get(method, method)
        object_type, object_id = _parse_object(path)

        # truncate body
        body_repr: str | None
        if body_bytes:
            head = body_bytes[:_MAX_BODY_BYTES]
            try:
                body_repr = head.decode("utf-8")
            except UnicodeDecodeError:
                body_repr = head.decode("utf-8", errors="replace")
            if len(body_bytes) > _MAX_BODY_BYTES:
                body_repr += "...(truncated)"
        else:
            body_repr = None

        # attach status_code / duration for forensics
        after_payload: dict[str, Any] = {
            "status_code": status,
            "duration_ms": duration_ms,
            "query": dict(request.query_params),
        }
        if body_repr is not None:
            after_payload["body"] = body_repr

        s = get_settings()
        delta.insert(
            sql,
            s.fq_table("audit_log"),
            {
                "audit_id": delta.new_id("audit-"),
                # occurred_at has a default of current_timestamp() in the DDL
                "actor_email": actor_email,
                "actor_role": None,
                "action": action,
                "object_type": object_type or "unknown",
                "object_id": object_id,
                "before_json": None,
                "after_json": json.dumps(after_payload, ensure_ascii=False, default=str),
                "request_id": request_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
            },
        )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _extract_client_ip(request: Request) -> str | None:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        # take the first hop only
        return fwd.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return None


def _parse_object(path: str) -> tuple[str | None, str | None]:
    """Parse `/api/<module>/<rest...>` to derive object_type and object_id."""
    # Strip the prefix
    p = path.split("?", 1)[0]
    parts = [seg for seg in p.split("/") if seg]
    # parts[0] == 'api'
    if len(parts) < 2 or parts[0] != "api":
        return None, None
    object_type = parts[1]
    object_id: str | None = None
    if len(parts) >= 3:
        candidate = parts[-1]
        if _ID_RE.match(candidate):
            object_id = candidate[:128]
    return object_type, object_id
