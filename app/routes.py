import secrets
from itertools import groupby
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND

from app.auth import current_user
from app.config import APP_DIR
from app.db import get_conn

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter()

MAX_CATEGORIES = 5


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: dict | None = Depends(current_user)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "auth_error": request.query_params.get("auth_error")},
    )


@router.get("/healthz")
async def healthz():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as err:
        return JSONResponse({"status": "error", "detail": str(err)}, status_code=500)
    return {"status": "ok"}


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request, user: dict | None = Depends(current_user)):
    if not user:
        return RedirectResponse(url="/auth/login", status_code=HTTP_302_FOUND)
    csrf_token = _get_or_create_csrf(request)
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {"user": user, "csrf_token": csrf_token, "grouped": _grouped_categories()},
    )


@router.post("/onboarding")
async def save_onboarding(request: Request, user: dict | None = Depends(current_user)):
    if not user:
        return RedirectResponse(url="/auth/login", status_code=HTTP_302_FOUND)

    fields = parse_qsl((await request.body()).decode("utf-8"), keep_blank_values=True)
    submitted_token = next((v for k, v in fields if k == "csrf_token"), None)
    if not _validate_csrf(request, submitted_token):
        return PlainTextResponse("Invalid CSRF token", status_code=403)

    # Dedupe while preserving order; drop empties.
    slugs = list(dict.fromkeys(v for k, v in fields if k == "slugs" and v))
    if not 1 <= len(slugs) <= MAX_CATEGORIES:
        return PlainTextResponse(
            f"Select between 1 and {MAX_CATEGORIES} categories.", status_code=400
        )

    with get_conn() as conn:
        valid = {row["slug"] for row in conn.execute("SELECT slug FROM categories WHERE active = 1")}
        unknown = [s for s in slugs if s not in valid]
        if unknown:
            return PlainTextResponse(f"Unknown categories: {', '.join(unknown)}", status_code=400)
        # Full replace, not append.
        conn.execute("DELETE FROM user_categories WHERE user_id = ?", (user["id"],))
        conn.executemany(
            "INSERT INTO user_categories (user_id, category_slug) VALUES (?, ?)",
            [(user["id"], s) for s in slugs],
        )

    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)


def _grouped_categories() -> list[tuple[str, list[dict]]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT slug, display_name, archive FROM categories WHERE active = 1 "
            "ORDER BY archive, sort_order, slug"
        ).fetchall()
    return [(archive, [dict(r) for r in items]) for archive, items in groupby(rows, key=lambda r: r["archive"])]


def _get_or_create_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def _validate_csrf(request: Request, submitted: str | None) -> bool:
    expected = request.session.get("csrf_token")
    if not expected or not submitted:
        return False
    return secrets.compare_digest(str(expected), str(submitted))
