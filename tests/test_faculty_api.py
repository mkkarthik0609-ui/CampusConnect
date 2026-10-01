"""/api/faculty: dashboard content, profile, picture upload, class listing (authorisation is in test_access_control)."""
import io

import pytest

from services import permission_service, supporting_service
from tests.conftest import (
    api_post, assign, create_admin, create_faculty, create_student, db_one, login_client, section_id_for,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def world(app):
    admin = create_admin(app)
    sec = section_id_for(app, "AIML", "3rd Year", "A")
    fac = create_faculty(app, "FAC500", subjects=("DSA", "OS"))
    stu = create_student(app, "1AB21CS500", sec, name="Asha Rao")
    assign(app, fac, sec, admin)
    return {"admin": admin, "sec": sec, "fac": fac, "stu": stu, "fc": login_client(app, fac["email"]),
            "sc": login_client(app, stu["email"])}


def test_dashboard_is_complete(app, world):
    fc, sc, fid, stid = world["fc"], world["sc"], world["fac"]["faculty_id"], world["stu"]["student_id"]
    far = create_student(app, "1AB21CS501", section_id_for(app, "AIDE", "2nd Year", "A"), name="Far Away")
    far_client = login_client(app, far["email"])
    api_post(far_client, f"/api/supporting/faculty/{fid}/request")           # incoming supporting request
    for i in range(7):
        api_post(sc, "/api/meetings", json={"faculty_id": fid, "reason": f"topic {i}"})
    with app.app_context():
        permission_service.student_request_profile_change(world["stu"]["user_id"], {"personal_email": "n@example.com"}, "typo")
    api_post(fc, "/api/faculty/classes/request", json={"section_id": section_id_for(app, "AIML", "3rd Year", "B")})

    d = fc.get("/api/faculty/dashboard").json()
    assert d["profile"]["faculty_code"] == "FAC500" and d["profile"]["professional_email"] == "fac500@college.edu"
    assert d["subjects"] == ["DSA", "OS"]
    assert d["classes"][0]["student_count"] == 1 and d["classes"][0]["section_id"] == world["sec"]
    assert len(d["pending_class_requests"]) == 1 and d["pending_class_requests"][0]["class"]["section"] == "B"
    assert [r["student"]["usn"] for r in d["pending_supporting_requests"]] == ["1AB21CS501"]
    assert len(d["recent_meetings"]) == 5 and d["recent_meetings"][0]["reason"] == "topic 6"
    assert d["counts"]["meetings_pending"] == 7
    assert d["recent_meetings"][0]["student"]["full_name"] == "Asha Rao"
    assert len(d["pending_permission_requests"]) == 1
    assert d["pending_permission_requests"][0]["student"]["usn"] == "1AB21CS500"
    assert d["supporting_students"] == []

    rel = d["pending_supporting_requests"][0]["id"]
    assert api_post(fc, f"/api/supporting/{rel}/accept").status_code == 200
    d = fc.get("/api/faculty/dashboard").json()
    assert [s["usn"] for s in d["supporting_students"]] == ["1AB21CS501"] and d["pending_supporting_requests"] == []
    assert stid  # student ids are exposed as card ids
    assert d["counts"]["supporting_students"] == 1


def test_profile_endpoint_and_change_request_listing(app, world):
    fc = world["fc"]
    r = fc.get("/api/faculty/profile").json()
    assert r["profile"]["department"] == "AIML" and "AIDE" in r["departments"]
    assert r["change_requests"] == [] and r["classes"][0]["label"].endswith("3rd Year → A")
    assert api_post(fc, "/api/faculty/profile/change-request",
                    json={"department": " AIDE ", "professional_email": "New.Mail@College.edu", "reason": " moving "}
                    ).status_code == 201
    row = fc.get("/api/faculty/profile").json()["change_requests"][0]
    assert row["requested_changes"] == {"department": "AIDE", "professional_email": "new.mail@college.edu"}
    assert row["reason"] == "moving" and row["status"] == "PENDING"


def test_profile_picture_upload(app, world):
    fc = world["fc"]
    r = api_post(fc, "/api/faculty/profile/picture", files={"profile_picture": ("me.png", io.BytesIO(PNG), "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["profile_picture_url"]
    assert url.startswith("/uploads/profile/faculty/")
    assert fc.get("/api/faculty/profile").json()["profile"]["profile_picture_url"] == url
    assert fc.get(url).status_code == 200
    assert fc.get("/api/auth/session").json()["user"]["profile_picture_url"] == url
    assert world["sc"].get(url).status_code == 200  # pictures are visible to signed-in users
    for files in ({"profile_picture": ("me.gif", io.BytesIO(b"GIF89a"), "image/gif")},
                  {"profile_picture": ("me.png", io.BytesIO(b"not png"), "image/png")},
                  {"profile_picture": ("me.png", io.BytesIO(b""), "image/png")}):
        assert api_post(fc, "/api/faculty/profile/picture", files=files).status_code == 400
    assert api_post(fc, "/api/faculty/profile/picture").status_code == 400  # field missing
    assert db_one(app, "SELECT profile_picture_path FROM users WHERE id = ?", (world["fac"]["user_id"],))[
        "profile_picture_path"] == url[len("/uploads/"):]


def test_classes_detail_lists_students_and_co_faculty(app, world):
    other = create_faculty(app, "FAC501")
    assign(app, other, world["sec"], world["admin"])
    d = world["fc"].get(f"/api/faculty/classes/{world['sec']}").json()
    assert d["class"]["student_count"] == 1 and d["class"]["label"] == "CSE → AIML → 3rd Year → A"
    assert d["students"][0]["usn"] == "1AB21CS500" and d["students"][0]["college_email"]
    assert sorted(f["faculty_code"] for f in d["co_faculty"]) == ["FAC500", "FAC501"]
    # a pending request and its history are listed with their class
    api_post(world["fc"], "/api/faculty/classes/request", json={"section_id": section_id_for(app, "AIDE", "2nd Year", "B")})
    reqs = world["fc"].get("/api/faculty/classes").json()["requests"]
    assert reqs[0]["status"] == "PENDING" and reqs[0]["class"]["department"] == "AIDE"


def test_supporting_listing_directions(app, world):
    fid, stid = world["fac"]["faculty_id"], world["stu"]["student_id"]
    with app.app_context():
        rel = supporting_service.faculty_request_student(fid, stid)
    s_item = world["sc"].get("/api/supporting").json()["items"][0]
    f_item = world["fc"].get("/api/supporting").json()["items"][0]
    assert s_item["id"] == f_item["id"] == rel
    assert (s_item["direction"], s_item["can_respond"]) == ("incoming", True)
    assert (f_item["direction"], f_item["can_respond"]) == ("outgoing", False)
    assert s_item["counterpart"]["faculty_code"] == "FAC500" and f_item["counterpart"]["usn"] == "1AB21CS500"
    assert world["sc"].get("/api/supporting?status=ACCEPTED").json()["items"] == []
    assert world["sc"].get("/api/supporting?status=BOGUS").status_code == 400
    items = world["sc"].get("/api/supporting/faculty/search?q=FAC500").json()["items"]
    assert items[0]["relationship"] == {"id": rel, "status": "PENDING", "requested_by": "FACULTY"}
    assert items[0]["can_request"] is False and items[0]["access_via"] == "class"
