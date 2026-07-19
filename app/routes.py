import secrets
from datetime import datetime
from itertools import groupby
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from starlette.status import HTTP_302_FOUND

from app.auth import clear_login_indicator, current_user
from app.config import APP_DIR, settings
from app.db import get_conn

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter()

MAX_CATEGORIES = 5
FEED_TZ = ZoneInfo("America/New_York")

# Raw HTML disabled so LLM-generated blurbs can't inject markup.
_md = MarkdownIt("commonmark", {"html": False})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: dict | None = Depends(current_user)):
    if user:
        target = "/feed" if _user_category_slugs(user["id"]) else "/onboarding"
        return RedirectResponse(url=target, status_code=HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "auth_error": request.query_params.get("auth_error")},
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: dict | None = Depends(current_user)):
    if user:
        return RedirectResponse(url="/feed", status_code=HTTP_302_FOUND)
    return templates.TemplateResponse(request, "login.html", {"user": None})


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
    error = await _apply_category_selection(request, user)
    return error or RedirectResponse(url="/", status_code=HTTP_302_FOUND)


async def _apply_category_selection(request: Request, user: dict):
    """Validate and full-replace the user's category selection from the POST body.

    Returns a PlainTextResponse on a CSRF/validation failure, or None on success.
    Shared by POST /onboarding and POST /settings.
    """
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
    return None


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user: dict | None = Depends(current_user)):
    if not user:
        return RedirectResponse(url="/auth/login", status_code=HTTP_302_FOUND)
    csrf_token = _get_or_create_csrf(request)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "user": user,
            "csrf_token": csrf_token,
            "grouped": _grouped_categories(),
            "selected": set(_user_category_slugs(user["id"])),
        },
    )


@router.post("/settings")
async def save_settings(request: Request, user: dict | None = Depends(current_user)):
    if not user:
        return RedirectResponse(url="/auth/login", status_code=HTTP_302_FOUND)
    error = await _apply_category_selection(request, user)
    return error or RedirectResponse(url="/feed", status_code=HTTP_302_FOUND)


@router.post("/settings/delete-account")
async def delete_account(request: Request, user: dict | None = Depends(current_user)):
    if not user:
        return RedirectResponse(url="/auth/login", status_code=HTTP_302_FOUND)
    fields = parse_qsl((await request.body()).decode("utf-8"), keep_blank_values=True)
    submitted_token = next((v for k, v in fields if k == "csrf_token"), None)
    if not _validate_csrf(request, submitted_token):
        return PlainTextResponse("Invalid CSRF token", status_code=403)
    confirmed = next((v for k, v in fields if k == "confirm"), None)
    if confirmed != "yes":
        return PlainTextResponse("Deletion not confirmed", status_code=400)
    with get_conn() as conn:
        # Hard delete: removes the user row and, via ON DELETE CASCADE, all
        # category selections. Nothing about the account is retained.
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    request.session.clear()
    response = RedirectResponse(url=f"{settings.blog_url}/?account_deleted=1", status_code=HTTP_302_FOUND)
    clear_login_indicator(response)
    return response


@router.get("/feed", response_class=HTMLResponse)
async def feed(request: Request, user: dict | None = Depends(current_user)):
    if not user:
        return RedirectResponse(url="/auth/login", status_code=HTTP_302_FOUND)
    slugs = _user_category_slugs(user["id"])  # alphabetical by slug
    if not slugs:
        return RedirectResponse(url="/onboarding", status_code=HTTP_302_FOUND)

    today = datetime.now(FEED_TZ).strftime("%Y-%m-%d")
    day_dir = settings.content_dir / today
    day_dir_exists = day_dir.is_dir()
    names = _display_names(slugs)

    sections = []
    for slug in slugs:
        path = day_dir / f"{slug}.md"
        body_html = _md.render(path.read_text(encoding="utf-8")) if path.is_file() else None
        sections.append({"slug": slug, "display_name": names.get(slug, slug), "html": body_html})

    return templates.TemplateResponse(
        request,
        "feed.html",
        {"user": user, "today": today, "day_dir_exists": day_dir_exists, "sections": sections},
    )


def _user_category_slugs(user_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category_slug FROM user_categories WHERE user_id = ? ORDER BY category_slug",
            (user_id,),
        ).fetchall()
    return [row["category_slug"] for row in rows]


def _display_names(slugs: list[str]) -> dict[str, str]:
    if not slugs:
        return {}
    placeholders = ",".join("?" for _ in slugs)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT slug, display_name FROM categories WHERE slug IN ({placeholders})", slugs
        ).fetchall()
    return {row["slug"]: row["display_name"] for row in rows}


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
