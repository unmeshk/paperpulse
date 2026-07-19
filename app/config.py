import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent

load_dotenv(APP_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    google_client_id: str
    google_client_secret: str
    session_secret: str
    db_path: Path
    content_dir: Path
    cookie_secure: bool
    blog_url: str
    indicator_cookie_domain: str | None
    session_max_age: int


def _require(name: str) -> str:
    value = get_secret(name.lower()) or ""
    value = value.strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}. See app/.env.example.")
    return value


def get_secret(name):
    """Read a secret from /run/secrets/<name> if present, else fall back to os.getenv(NAME.upper()).

    Lets prod use Docker Compose secrets while local dev keeps reading from .env via os.getenv.
    """
    secret_path = Path("/run/secrets") / name
    if secret_path.exists():
        return secret_path.read_text().strip()
    return os.getenv(name.upper())


def load_settings() -> Settings:
    return Settings(
        google_client_id=_require("GOOGLE_OAUTH_CLIENT_ID"),
        google_client_secret=_require("GOOGLE_OAUTH_CLIENT_SECRET"),
        session_secret=_require("SESSION_SECRET"),
        db_path=Path(os.getenv("DB_PATH", str(APP_DIR / "paperpulse.sqlite"))),
        content_dir=Path(os.getenv("CONTENT_DIR", str(REPO_ROOT / "content"))),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        blog_url=os.getenv("BLOG_URL", "https://paperpulse.ukurup.com").rstrip("/"),
        # Domain for the non-sensitive pp_logged_in indicator cookie so the
        # static blog can reflect login state. Empty string => host-only
        # cookie (local dev, where localhost cookies span ports anyway).
        indicator_cookie_domain=os.getenv("INDICATOR_COOKIE_DOMAIN", "paperpulse.ukurup.com") or None,
        session_max_age=60 * 60 * 24 * 30,
    )


settings = load_settings()
