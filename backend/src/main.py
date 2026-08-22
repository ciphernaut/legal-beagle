from fastapi import FastAPI

from src.api import nodes, tree
from src.db import configure_sessions, get_engine


def create_app() -> FastAPI:
    app = FastAPI(title="Legal Beagle API")
    configure_sessions(get_engine())
    app.include_router(nodes.router)
    app.include_router(tree.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
