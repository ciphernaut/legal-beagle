from fastapi import FastAPI

from src.db import configure_sessions, get_engine


def create_app() -> FastAPI:
    app = FastAPI(title="Legal Beagle API")
    configure_sessions(get_engine())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
