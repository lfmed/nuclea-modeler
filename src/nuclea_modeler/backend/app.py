from .core import create_app
from .router import router as base_router
from .connections.router import router as connections_router
from .systems.router import router as systems_router
from .entities.router import router as entities_router
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

app = create_app(
    routers=[
        base_router,
        systems_router,
        connections_router,
        entities_router,
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
    ]
)
