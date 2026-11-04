from fastapi.testclient import TestClient

from api.db import db_session
from api.main import create_app
from models import queries
from services import auth_service
from tests.conftest import ADMIN_EMAIL, PASSWORD, api_post, make_admin, make_settings


def test_dedicated_admin_login_accepts_any_password_only_for_owner(app):
    make_admin(app, email=ADMIN_EMAIL)

    owner = TestClient(app)
    response = api_post(owner, "/api/auth/admin-login", json={
        "identifier": ADMIN_EMAIL.upper(),
        "password": "not-the-stored-password",
    })
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "ADMIN"

    other = TestClient(app)
    response = api_post(other, "/api/auth/admin-login", json={
        "identifier": "someone@example.com",
        "password": "anything",
    })
    assert response.status_code == 401


def test_production_admin_login_still_verifies_password(tmp_path):
    settings = make_settings(
        tmp_path,
        environment="production",
        secret_key="production-secret-key-long-enough-123",
    )
    production_app = create_app(settings)
    with db_session(settings):
        queries.create_user("ADMIN", ADMIN_EMAIL, auth_service.hash_password(PASSWORD), "Owner")

    client = TestClient(production_app)
    response = api_post(client, "/api/auth/admin-login", json={
        "identifier": ADMIN_EMAIL,
        "password": "wrong-password",
    })
    assert response.status_code == 401
