"""Isolated design preview. Run from repo root; never uses production accounts.

Command: PYTHONPATH=. app/.venv/bin/python app/tests/preview_design.py
The /preview/login route exists only in this loopback-only test server.
"""
import os
import tempfile
from pathlib import Path

PREVIEW_DIR = Path(tempfile.mkdtemp(prefix="paperpulse-design-"))
os.environ.update({
    "GOOGLE_OAUTH_CLIENT_ID": "design-preview", "GOOGLE_OAUTH_CLIENT_SECRET": "design-preview",
    "SESSION_SECRET": "local-design-preview-only", "DB_PATH": str(PREVIEW_DIR / "preview.sqlite"),
    "CONTENT_DIR": str(PREVIEW_DIR / "content"), "COOKIE_SECURE": "false",
    "BLOG_URL": "http://127.0.0.1:8765/reference", "INDICATOR_COOKIE_DOMAIN": "",
})

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import get_conn, init_db
from app.main import create_app

app = create_app()
init_db()
with get_conn() as conn:
    conn.execute("INSERT INTO users (google_sub, email, display_name) VALUES (?, ?, ?)",
                 ("design-reader", "reader@example.test", "Design Reader"))
    conn.executemany("INSERT INTO user_categories (user_id, category_slug) VALUES (1, ?)",
                     [("cs.AI",), ("cs.LG",), ("stat.ML",)])

for day in ["2026-10-05", "2026-10-02", "2026-09-30"]:
    directory = PREVIEW_DIR / "content" / day
    directory.mkdir(parents=True)
    for slug in ["cs.AI", "cs.LG"]:
        (directory / f"{slug}.md").write_text(
            "## Theme 1: Learning and reasoning\n\n"
            "[A Study of Learning](https://arxiv.org/abs/2601.00001) explores how models learn "
            "from examples. These findings connect improved reasoning with efficient training.\n\n"
            "## Theme 2: Evaluation\n\nNew benchmarks measure generalization across tasks.\n",
            encoding="utf-8",
        )

reference = Path(__file__).resolve().parents[2] / "blog" / "_site"
if reference.is_dir():
    app.mount("/reference", StaticFiles(directory=reference, html=True))


@app.get("/preview/login")
def preview_login(request: Request):
    request.session["user_id"] = 1
    return RedirectResponse("/feed")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
