from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.auth import current_user
from app.config import APP_DIR
from app.db import get_conn

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = current_user(request)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user, "auth_error": request.query_params.get("auth_error")},
    )


@router.get("/healthz")
async def healthz():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as err:
        return JSONResponse({"status": "error", "detail": str(err)}, status_code=500)
    return {"status": "ok"}
