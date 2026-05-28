"""Global exception handler — structured logging + safe error responses.

When a route handler raises something we didn't catch, the default FastAPI
behaviour is to return a generic 500 with the exception text in the response.
That's bad on two counts:

1. The user sees a Python stack trace / internal error — useless and leaks
   implementation details.
2. The log line is unstructured — hard to correlate with a request.

This handler:
- Generates a short `error_id` and returns it in both the response body and
  the `X-Error-ID` header. Users can quote this ID when reporting bugs.
- Logs the full traceback at ERROR level with the request_id from the
  contextvar, the route, method and the error_id.
- HTTPException (raised by FastAPI itself, e.g. 404 from path params) is left
  alone — only truly uncaught exceptions are intercepted here.
"""
from __future__ import annotations

import logging
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from .logging import get_request_id


logger = logging.getLogger("nuclea_modeler.exceptions")


def install_exception_handlers(app: FastAPI) -> None:
    """Register the global uncaught-exception handler on the app."""

    @app.exception_handler(Exception)
    async def _handle_uncaught(request: Request, exc: Exception) -> JSONResponse:
        # Let FastAPI's own HTTPException pass through — it knows the status
        # code and detail, and shouldn't be reframed as a 500.
        if isinstance(exc, HTTPException):
            raise exc

        error_id = uuid.uuid4().hex[:12]
        request_id = get_request_id() or "?"

        logger.error(
            "Uncaught exception: %s",
            exc,
            extra={
                "error_id": error_id,
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "exception_type": type(exc).__name__,
            },
            exc_info=True,
        )

        # User-facing payload — deliberately spartan. NEVER include the raw
        # exception message, which can contain DB errors / file paths / etc.
        return JSONResponse(
            status_code=500,
            headers={"X-Error-ID": error_id},
            content={
                "detail": "Erro interno do servidor. Cite o error_id ao reportar.",
                "error_id": error_id,
                "request_id": request_id,
            },
        )


def install_for_test(app: FastAPI) -> tuple:
    """Test helper: patch the handler to also return the underlying exception
    type in the response, so tests can assert without parsing logs. Returns
    the list that captures logged exceptions for inspection."""
    captured: list[tuple[str, str]] = []

    @app.exception_handler(Exception)
    async def _handle_for_test(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            raise exc
        error_id = uuid.uuid4().hex[:12]
        captured.append((type(exc).__name__, str(exc)))
        return JSONResponse(
            status_code=500,
            headers={"X-Error-ID": error_id},
            content={
                "detail": "internal error",
                "error_id": error_id,
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            },
        )

    return captured
