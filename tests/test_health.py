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


def test_healthz_is_database_free_unless_deep_is_requested(client, monkeypatch):
    import api.db as dbmod
    real = dbmod._checkout

    def boom(*_a, **_k):
        raise AssertionError("/healthz must not query the database")
    monkeypatch.setattr(dbmod, "_checkout", boom)
    assert client.get("/healthz").json() == {"status": "ok"}
    monkeypatch.setattr(dbmod, "_checkout", real)
    assert client.get("/healthz?deep=1").json() == {"status": "ok"}


def test_deep_healthz_reports_503_when_the_database_is_down(client, monkeypatch):
    import api.db as dbmod

    def down(*_a, **_k):
        raise RuntimeError("db down")
    monkeypatch.setattr(dbmod, "_checkout", down)
    resp = client.get("/healthz?deep=1")
    assert resp.status_code == 503 and resp.json() == {"status": "error"}
