"""HTTP tests for /api/research/* (admin-only scheduling research). Uses the shared `app`, `client`
and `admin_client` fixtures from tests/conftest.py."""
import pytest

from api.routers import research as research_router
from tests.conftest import api_post, find_section, login_client, register_faculty, register_student

METHODS = {"fcfs", "rule_based", "intelligent"}


@pytest.fixture
def student_client(app):
    stu = register_student(app, usn="1AB21CS001", section_id=find_section("CSE", "AIML", "3rd Year", "A", app=app))
    return login_client(app, stu["email"], stu["password"])


@pytest.fixture
def faculty_client(app):
    fac = register_faculty(app, code="FAC001")
    return login_client(app, fac["email"], fac["password"])


# ------------------------------------------------------------------ auth

@pytest.mark.parametrize("method,url", [("get", "/api/research/results"), ("post", "/api/research/run")])
def test_anonymous_gets_401(client, method, url):
    r = client.get(url) if method == "get" else api_post(client, url, json={})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("who", ["student_client", "faculty_client"])
def test_non_admin_gets_403_on_both_endpoints(request, who):
    c = request.getfixturevalue(who)
    for r in (c.get("/api/research/results"), api_post(c, "/api/research/run", json={"seeds": 1})):
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "forbidden"


# ------------------------------------------------------------------ GET /results

def test_results_returns_committed_file(admin_client):
    r = admin_client.get("/api/research/results")
    assert r.status_code == 200
    body = r.json()
    assert set(body["levels"]) == {"low", "medium", "high"}
    assert set(body["methods"]) == METHODS
    cell = body["levels"]["medium"]["table"]["intelligent"]["success_rate"]
    assert {"mean", "sd", "ci95", "n"} <= set(cell)
    assert len(body["conclusions"]) == 5


def test_results_generated_on_the_fly_when_file_missing(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(research_router, "RESULTS_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(research_router, "_fallback_cache", {})
    r = admin_client.get("/api/research/results")
    assert r.status_code == 200
    body = r.json()
    assert body["generated_on_the_fly"] is True
    assert body["levels"]["medium"]["table"]["fcfs"]["success_rate"]["n"] == research_router.FALLBACK_SEEDS


# ------------------------------------------------------------------ POST /run

def test_run_returns_table_and_timeline_for_all_three_methods(admin_client):
    r = api_post(admin_client, "/api/research/run", json={"seeds": 2, "load": "low", "num_requests": 80})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["load"] == "low" and body["num_requests"] == 80
    assert body["seeds_run"] == 2 and body["truncated"] is False
    assert set(body["table"]) == METHODS
    assert body["table"]["fcfs"]["avg_wait_min"]["n"] == 2
    assert set(body["improvement"]) >= {"intelligent_vs_fcfs", "intelligent_vs_rule_based"}
    tl = body["timeline"]
    assert len(tl["faculty"]) == 4 and tl["time_axis"]["day_minutes"] == 480
    assert set(tl["methods"]) == METHODS
    block = next(b for blocks in tl["methods"].values() for b in blocks)
    assert {"faculty_id", "start_min", "end_min", "kind", "request_id", "priority"} <= set(block)
    assert body["elapsed_ms"] < 3000


def test_run_defaults_and_determinism(admin_client):
    a = api_post(admin_client, "/api/research/run", json={"seeds": 1, "num_requests": 50}).json()
    b = api_post(admin_client, "/api/research/run", json={"seeds": 1, "num_requests": 50}).json()
    assert a["load"] == "medium"
    a.pop("elapsed_ms"), b.pop("elapsed_ms")
    assert a == b


def test_run_with_max_seeds_stays_within_time_budget(admin_client):
    r = api_post(admin_client, "/api/research/run", json={"seeds": 30, "load": "high", "num_requests": 600})
    assert r.status_code == 200
    body = r.json()
    assert body["elapsed_ms"] < 3000
    assert 1 <= body["seeds_run"] <= 30 and body["truncated"] == (body["seeds_run"] < 30)


@pytest.mark.parametrize("payload,field", [
    ({"seeds": 0}, "seeds"),
    ({"seeds": 31}, "seeds"),
    ({"load": "extreme"}, "load"),
    ({"num_requests": 5}, "num_requests"),
    ({"num_requests": 100000}, "num_requests"),
    ({"seeds": "many"}, "seeds"),
    ({"bogus": 1}, "bogus"),
])
def test_run_rejects_invalid_input(admin_client, payload, field):
    r = api_post(admin_client, "/api/research/run", json=payload)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "validation_error" and field in err["fields"]


def test_run_busy_returns_429(admin_client, monkeypatch):
    class Busy:
        def acquire(self, blocking=True):
            return False

        def release(self):
            raise AssertionError("must not release a slot that was never acquired")

    monkeypatch.setattr(research_router, "_run_slots", Busy())
    r = api_post(admin_client, "/api/research/run", json={"seeds": 1})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
