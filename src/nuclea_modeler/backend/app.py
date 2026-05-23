from .core import create_app
from .router import router as base_router
from .connections.router import router as connections_router
from .systems.router import router as systems_router
from .entities.router import router as entities_router

app = create_app(
    routers=[
        base_router,
        systems_router,
        connections_router,
        entities_router,
    ]
)
