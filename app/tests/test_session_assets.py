"""Regression: late asset responses must not replace a page's CSRF session."""
import asyncio
import json
import re
from base64 import b64encode

import httpx
import pytest
from itsdangerous import TimestampSigner


@pytest.mark.parametrize("asset", ["/static/main.css", "/static/category-picker.js",
                                   "/static/missing.css", "/favicon.ico"])
def test_late_asset_response_preserves_csrf_and_category_save(client, db_user, asset):
    from app.config import settings
    from app.db import get_conn
    from app.main import app

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_app(scope, receive, send):
            async def delayed_send(message):
                if scope["path"] == asset and message["type"] == "http.response.start":
                    started.set()
                    await release.wait()
                await send(message)

            await app(scope, receive, delayed_send)

        # Use a real signed login session, with no dependency override or CSRF yet.
        session = TimestampSigner(settings.session_secret).sign(
            b64encode(json.dumps({"user_id": db_user["id"]}).encode())
        ).decode()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=delayed_app), base_url="http://testserver"
        ) as browser:
            browser.cookies.set("session", session, domain="testserver.local", path="/")
            pending_asset = asyncio.create_task(browser.get(asset))
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                page = await browser.get("/settings")
                assert page.status_code == 200
                token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
                page_cookie = browser.cookies.get("session")
                assert page_cookie != session
            finally:
                release.set()
            response = await pending_asset
            saved = await browser.post("/settings", data={"csrf_token": token, "slugs": ["cs.LG"]})
            assert saved.status_code == 302
            assert saved.headers["location"] == "/feed"
            assert not response.headers.get_list("set-cookie")

    asyncio.run(run())
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category_slug FROM user_categories WHERE user_id = ?", (db_user["id"],)
        ).fetchall()
    assert [row["category_slug"] for row in rows] == ["cs.LG"]
