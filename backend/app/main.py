from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal, migrate_sqlite_app_settings, migrate_sqlite_presets
from app.core.logging import setup_logging
from app.services.preset_service import PresetService

logger = logging.getLogger(__name__)


def _validate_routes() -> None:
    critical_routes = {"/api/subtitle/preview-style"}
    registered = {route.path for route in router.routes}
    missing = critical_routes - registered
    if missing:
        logger.warning("Critical API routes missing at startup: %s", sorted(missing))
    else:
        logger.info("All critical API routes registered (%d total)", len(registered))


def create_app() -> FastAPI:
    setup_logging()
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_presets()
    migrate_sqlite_app_settings()
    with SessionLocal() as db:
        PresetService(db).seed_builtin_presets()
    app = FastAPI(title=settings.app_name, version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.include_router(router, prefix="/api")
    _validate_routes()

    frontend_dist = settings.frontend_dist_dir
    frontend_index = frontend_dist / "index.html"
    assets_dir = frontend_dist / "assets"
    if frontend_index.exists() and assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/")
        def frontend_root():
            return FileResponse(frontend_index)

        @app.get("/{full_path:path}")
        def frontend_spa(full_path: str):
            candidate = (frontend_dist / full_path).resolve()
            try:
                candidate.relative_to(frontend_dist.resolve())
            except ValueError:
                return FileResponse(frontend_index)
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_index)

        return app

    @app.get("/")
    def health():
        return {"message": f"{settings.app_name} backend đang hoạt động."}

    return app


app = create_app()
