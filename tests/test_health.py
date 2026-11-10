"""GET /health: the unauthenticated keep-alive ping must stay free of side effects."""


def test_health_ok_without_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_head_ok(client):
    assert client.head("/health").status_code == 200


def test_health_never_touches_the_database(client, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("/health must not query the database")
    monkeypatch.setattr("api.db._checkout", boom)
    assert client.get("/health").status_code == 200


def test_health_sets_no_session_cookie(client):
    assert "set-cookie" not in client.get("/health").headers
