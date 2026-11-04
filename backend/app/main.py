import logging

from fastapi import FastAPI

from app.api import admin, archive, integrations
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    # httpx는 INFO 로그에 전체 URL(access_token 쿼리 포함)을 남기므로 WARNING 이상만 내보낸다.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = settings or get_settings()
    app = FastAPI(title="HUFS 이어:잇")
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(archive.router)
    app.include_router(admin.router)
    app.include_router(integrations.router)

    return app


app = create_app()
