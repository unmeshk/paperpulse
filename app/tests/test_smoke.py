def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_renders_for_anonymous(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/login"' in response.text


def test_login_page_renders_for_anonymous(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Continue with Google" in response.text
    assert 'href="/auth/login"' in response.text


def test_logout_redirects_to_blog_with_banner_param(client):
    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("/?logged_out=1")
    from app.config import settings

    assert response.headers["location"] == f"{settings.blog_url}/?logged_out=1"


def test_logout_clears_login_indicator_cookie(client):
    response = client.get("/auth/logout", follow_redirects=False)
    cookie_headers = [v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"]
    indicator = [h for h in cookie_headers if h.startswith("pp_logged_in=")]
    assert indicator, "logout must clear the pp_logged_in indicator cookie"
    assert 'pp_logged_in=""' in indicator[0]


def test_login_indicator_helper_sets_shared_domain_cookie():
    from fastapi.responses import RedirectResponse

    from app.auth import set_login_indicator
    from app.config import settings

    response = RedirectResponse(url="/")
    set_login_indicator(response)
    header = response.headers["set-cookie"]
    assert "pp_logged_in=1" in header
    assert f"Max-Age={settings.session_max_age}" in header
    if settings.indicator_cookie_domain:
        assert f"Domain={settings.indicator_cookie_domain}" in header
    assert "HttpOnly" not in header  # blog JS must be able to read it
