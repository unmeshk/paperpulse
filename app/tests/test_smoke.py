def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_renders_for_anonymous(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Sign in with Google" in response.text
