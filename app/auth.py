from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_302_FOUND

from app.config import settings
from app.db import get_conn

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, str(redirect_uri))


@router.get("/google/callback", name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as err:
        return RedirectResponse(url=f"/?auth_error={err.error}", status_code=HTTP_302_FOUND)

    userinfo = token.get("userinfo") or {}
    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not google_sub or not email:
        return RedirectResponse(url="/?auth_error=missing_claims", status_code=HTTP_302_FOUND)

    display_name = userinfo.get("name")
    picture_url = userinfo.get("picture")

    user_id = _upsert_user(google_sub, email, display_name, picture_url)
    request.session["user_id"] = user_id
    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)


def _upsert_user(google_sub: str, email: str, display_name: str | None, picture_url: str | None) -> int:
    with get_conn() as conn:
        cur = conn.execute("SELECT id FROM users WHERE google_sub = ?", (google_sub,))
        row = cur.fetchone()
        if row:
            conn.execute(
                "UPDATE users SET email = ?, display_name = ?, picture_url = ?, "
                "updated_at = CURRENT_TIMESTAMP, deleted_at = NULL WHERE id = ?",
                (email, display_name, picture_url, row["id"]),
            )
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO users (google_sub, email, display_name, picture_url) VALUES (?, ?, ?, ?)",
            (google_sub, email, display_name, picture_url),
        )
        return int(cur.lastrowid)


def current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT id, email, display_name, picture_url FROM users WHERE id = ? AND deleted_at IS NULL",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
