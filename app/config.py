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


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}. See app/.env.example.")
    return value


def load_settings() -> Settings:
    return Settings(
        google_client_id=_require("GOOGLE_OAUTH_CLIENT_ID"),
        google_client_secret=_require("GOOGLE_OAUTH_CLIENT_SECRET"),
        session_secret=_require("SESSION_SECRET"),
        db_path=Path(os.getenv("DB_PATH", str(APP_DIR / "paperpulse.sqlite"))),
        content_dir=Path(os.getenv("CONTENT_DIR", str(REPO_ROOT / "content"))),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    )


settings = load_settings()
