def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_renders_for_anonymous(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Sign in with Google" in response.text


def test_logout_redirects_to_blog_with_banner_param(client):
    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("/?logged_out=1")
    from app.config import settings

    assert response.headers["location"] == f"{settings.blog_url}/?logged_out=1"
