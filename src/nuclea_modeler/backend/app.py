from .core import create_app
from .router import router as base_router
from .connections.router import router as connections_router
from .systems.router import router as systems_router
from .schemas.router import router as schemas_router
from .diagrams.router import router as diagrams_router
from .entities.router import router as entities_router
from .entities.indexes_router import router as entities_indexes_router
from .entities.global_listings_router import (
    attributes_router as attributes_listing_router,
    indexes_router as indexes_listing_router,
)
from .glossary.router import attr_glossary_router, router as glossary_router
from .rbac.router import router as rbac_router
from .tickets.router import router as tickets_router
from .sync.router import router as sync_router
from .flags.router import (
    router as flags_router,
    entity_router as entity_flags_router,
    attribute_router as attribute_flags_router,
)
from .ddl.router import router as ddl_router
from .versions.router import router as versions_router
from .lakebase.router import router as lakebase_router
from .extractions.router import router as extractions_router
from .lineage.router import router as lineage_router
from .diagram.router import router as diagram_router
from .relationships.router import router as relationships_router
from .code_objects.router import (
    views_router,
    procedures_router,
    triggers_router,
    sequences_router,
)
from .audit.router import router as audit_router
from .audit.middleware import AuditMiddleware
from .sessions.router import router as sessions_router
from .uc.router import router as uc_router
from .admin.router import router as admin_router
from .dashboard.router import router as dashboard_router
import os

from fastapi.middleware.cors import CORSMiddleware

from .core.exceptions import install_exception_handlers
from .core.logging import RawAsgiLogMiddleware, RequestIdMiddleware, configure_logging
from .core.metrics import MetricsMiddleware
from .core.security import RateLimitMiddleware, SecurityHeadersMiddleware
from .search.router import router as search_router
from .attachments.router import router as attachments_router

# Install logging FIRST so every other module's logger inherits the config.
configure_logging()

app = create_app(
    routers=[
        base_router,
        systems_router,
        schemas_router,
        diagrams_router,
        connections_router,
        entities_router,
        entities_indexes_router,
        attributes_listing_router,
        indexes_listing_router,
        glossary_router,
        attr_glossary_router,
        rbac_router,
        tickets_router,
        sync_router,
        flags_router,
        entity_flags_router,
        attribute_flags_router,
        ddl_router,
        versions_router,
        lakebase_router,
        extractions_router,
        lineage_router,
        diagram_router,
        relationships_router,
        views_router,
        procedures_router,
        triggers_router,
        sequences_router,
        audit_router,
        search_router,
        sessions_router,
        uc_router,
        admin_router,
        dashboard_router,
        attachments_router,
    ]
)

# Middleware order matters: Starlette executes them in REVERSE add order, so
# add the outermost-first. We want:
#   request  →  RequestId → SecurityHeaders → RateLimit → Audit → app
#   response ←  RequestId ← SecurityHeaders ← RateLimit ← Audit ← app
# RequestIdMiddleware is added LAST so it runs FIRST on the way in: every
# downstream middleware and handler sees the request_id in the contextvar.
app.add_middleware(MetricsMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

# Raw ASGI logger — OUTERMOST (added last = runs first). Off unless
# NUCLEA_RAW_ASGI_LOG=true. When on, logs every valid connection's raw scope
# (http_version/scheme/client/path) + response status, before any other
# middleware. Diagnostic for "App unavailable" while uvicorn is up.
app.add_middleware(RawAsgiLogMiddleware)

# CORS — only needed if the frontend ever runs on a different origin than the
# API. Today the UI is served from the same FastAPI process, so same-origin
# requests don't trip CORS. We still declare the middleware explicitly so
# future split deployments (mobile, B2B) require only an env tweak.
_cors_origins = os.getenv("NUCLEA_CORS_ALLOW_ORIGINS", "").strip()
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Error-ID", "Retry-After"],
        max_age=600,
    )

# Global exception handler — must be installed AFTER the app is created.
# Logs uncaught exceptions with request_id + traceback, returns a sanitised
# 500 to the client with a quotable error_id.
install_exception_handlers(app)
