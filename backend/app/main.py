from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import Settings
from .db import build_engine, build_session_factory
from .demo import capture_demo_protected_ids
from .migrations import run_migrations
from .observability import configure_logging, install_request_logging
from .seeds import seed_database, seed_demo_database


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    configure_logging(app_settings.log_level)
    engine = build_engine(app_settings)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        run_migrations(app_settings)
        with session_factory() as db:
            seed_database(db)
            if app_settings.demo_mode:
                seed_demo_database(db)
                _app.state.demo_protected_ids = capture_demo_protected_ids(db)
        yield
        engine.dispose()

    app = FastAPI(title="Filter Coffee Club API", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.demo_protected_ids = {}
    install_request_logging(app)
    app.include_router(router)

    app.mount("/uploads", StaticFiles(directory=app_settings.upload_dir), name="uploads")

    @app.get("/health/live", include_in_schema=False)
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def health_ready() -> dict[str, str]:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return {"status": "ready"}

    frontend_dir = Path(app_settings.frontend_dir)
    if frontend_dir.exists():
        assets = frontend_dir / "_app"
        if assets.exists():
            app.mount("/_app", StaticFiles(directory=assets), name="frontend-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def frontend(full_path: str):
            root = frontend_dir.resolve()
            candidate = (frontend_dir / full_path).resolve()
            if full_path and candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dir / "index.html")

    return app


app = create_app()
