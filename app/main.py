from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.config import settings
from app.db import init_db
from app.routes import router as routes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="PaperPulse", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=settings.cookie_secure,
        same_site="lax",
        max_age=settings.session_max_age,
    )
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(auth_router)
    app.include_router(routes_router)
    return app


app = create_app()
