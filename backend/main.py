from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.core.exceptions import (
    AuthError,
    ConfigError,
    PostbellError,
    QuotaExceededError,
    RoutingError,
    UploadError,
)
from backend.core.logging import setup_logging
from sqlalchemy import text
from backend.database import Base, engine
from backend.api.projects import router as projects_router
from backend.api.accounts import router as accounts_router
from backend.api.channels import router as channels_router
from backend.api.channel_groups import router as channel_groups_router
from backend.api.uploads import router as uploads_router
from backend.api.language import router as language_router
from backend.api.ws import router as ws_router
from backend.api.quota import router as quota_router
from backend.api.settings import router as settings_router
from backend.api.analytics import router as analytics_router
from backend.api.language_schedules import router as language_schedules_router
import backend.models  # noqa: F401 — registers all models with Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    settings.tokens_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(settings.logs_dir)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE channels ADD COLUMN default_description TEXT NOT NULL DEFAULT ''"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE channels ADD COLUMN default_comment TEXT NOT NULL DEFAULT ''"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE channels ADD COLUMN group_id INTEGER"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE channels ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE uploads ADD COLUMN verification_error TEXT"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE uploads ADD COLUMN thumbnail_error TEXT"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE uploads ADD COLUMN comment_error TEXT"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE channels ADD COLUMN custom_schedule_time VARCHAR(5)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE channels ADD COLUMN default_tags TEXT"))
            conn.commit()
        except Exception:
            pass
    yield


app = FastAPI(title="Postbell", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # The Electron static server binds to a random localhost port at startup,
    # so we can't enumerate exact origins. Allow any localhost/127.0.0.1
    # origin (with or without a port). The dev Vite server (5173) also matches.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ERROR_STATUS: dict[type[PostbellError], int] = {
    AuthError: 401,
    QuotaExceededError: 429,
    UploadError: 500,
    RoutingError: 400,
    ConfigError: 500,
}


@app.exception_handler(PostbellError)
async def postbell_error_handler(request: Request, exc: PostbellError) -> JSONResponse:
    status_code = _ERROR_STATUS.get(type(exc), 500)
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.message, "error_type": type(exc).__name__},
    )


app.include_router(projects_router)
app.include_router(accounts_router)
app.include_router(channels_router)
app.include_router(channel_groups_router)
app.include_router(uploads_router)
app.include_router(language_router)
app.include_router(ws_router)
app.include_router(quota_router)
app.include_router(settings_router)
app.include_router(analytics_router)
app.include_router(language_schedules_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
