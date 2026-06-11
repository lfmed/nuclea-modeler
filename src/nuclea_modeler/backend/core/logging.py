"""Structured logging + request correlation ID.

Two pieces:

1. RequestIdMiddleware
   Generates a short request id per request (or honours an inbound
   `X-Request-ID` header), stores it in a contextvar, and stamps it on the
   response so callers can correlate client → server logs.

2. JsonFormatter (opt-in)
   When `NUCLEA_LOG_JSON=true`, all log records are emitted as single-line
   JSON objects with timestamp, level, logger, message, request_id and any
   extras. Fits cleanly into Databricks Apps log aggregation / future Lakehouse
   Monitoring sinks.

To use the request id inside a handler/service:

    from .logging import get_request_id
    logger.info("did the thing", extra={"request_id": get_request_id()})
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_request_id_var: ContextVar[str | None] = ContextVar("nuclea_request_id", default=None)


def get_request_id() -> str | None:
    """Return the current request's correlation id, or None outside a request."""
    return _request_id_var.get()


def _new_request_id() -> str:
    """Short, URL-safe correlation id (12 chars of a UUID4)."""
    return uuid.uuid4().hex[:12]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has an X-Request-ID and propagate it.

    - If the inbound request includes `X-Request-ID` we trust and reuse it
      (sanitized to alphanumeric + dash/underscore, capped at 64 chars).
    - Otherwise we generate a new one.
    - The id is stamped on the response as `X-Request-ID` and stored in a
      contextvar so logs and middlewares downstream can read it.
    """

    _ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

    @classmethod
    def _sanitize(cls, value: str | None) -> str | None:
        if not value:
            return None
        cleaned = "".join(c for c in value if c in cls._ALLOWED)
        return cleaned[:64] if cleaned else None

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = self._sanitize(request.headers.get("x-request-id")) or _new_request_id()
        token = _request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


# ─── Raw ASGI connection logger (diagnostics, opt-in) ───────────────────────


class RawAsgiLogMiddleware:
    """Outermost *pure ASGI* logger — gated by `NUCLEA_RAW_ASGI_LOG`.

    Logs the raw scope of every connection that reaches the ASGI app (before any
    HTTP middleware/routing) plus the response status. Unlike the normal access
    log, this surfaces `http_version` and `scheme`, which is the signal needed to
    diagnose "App unavailable" while uvicorn is up: e.g. a health probe hitting
    "/" and getting 404, or a proxy speaking HTTP/2 to an HTTP/1.1 server.

    Note: requests that uvicorn rejects as malformed ("Invalid HTTP request
    received") never reach ASGI, so they won't appear here — but every *valid*
    request (including platform health checks) will, with its status.

    Off by default (zero overhead). Enable by setting NUCLEA_RAW_ASGI_LOG=true
    in the app env, then redeploy.
    """

    def __init__(self, app):
        self.app = app
        self._enabled = os.getenv("NUCLEA_RAW_ASGI_LOG", "").lower() in ("true", "1", "yes")
        self._log = logging.getLogger("nuclea-modeler")

    async def __call__(self, scope, receive, send):
        if not self._enabled or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_str = f"{client[0]}:{client[1]}" if client else "?"
        self._log.info(
            "[raw-asgi] IN %s %s http=%s scheme=%s client=%s",
            scope.get("method"), scope.get("path"),
            scope.get("http_version"), scope.get("scheme"), client_str,
        )

        status: dict = {}

        async def _send(message):
            if message.get("type") == "http.response.start":
                status["code"] = message.get("status")
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            self._log.info(
                "[raw-asgi] OUT %s -> status=%s", scope.get("path"), status.get("code"),
            )


# ─── JSON log formatter ─────────────────────────────────────────────────────


_STD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render LogRecords as single-line JSON.

    Fields:
        ts        ISO 8601 UTC timestamp
        level     log level name
        logger    logger.name
        msg       formatted message
        request_id  from the contextvar (if set)
        + any extras passed via `logger.info("...", extra={...})`
        + exc_info  formatted traceback if present
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            payload["request_id"] = rid
        # Surface any extras that aren't standard LogRecord attributes.
        for key, value in record.__dict__.items():
            if key in _STD_ATTRS or key.startswith("_"):
                continue
            try:
                json.dumps(value)  # ensure serialisable
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(*, force_json: bool | None = None, level: str | None = None) -> None:
    """Install handler + formatter on the root logger.

    `NUCLEA_LOG_JSON=true` switches to the JSON formatter; otherwise a concise
    text format is used (matching what Databricks Apps already shows).
    `NUCLEA_LOG_LEVEL` overrides the level (default INFO).
    """
    use_json = force_json if force_json is not None else (
        os.getenv("NUCLEA_LOG_JSON", "").lower() in ("true", "1", "yes")
    )
    lvl = (level or os.getenv("NUCLEA_LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stdout)
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    root = logging.getLogger()
    # Clear handlers added by other libraries (uvicorn etc.) to avoid duplicate lines.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(lvl)
