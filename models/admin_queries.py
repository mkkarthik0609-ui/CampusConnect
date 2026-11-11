"""Read-only SQL behind the admin console (dashboard counts, listings with names/pictures).

Framework-agnostic: every function calls ``get_db()``. Mutations live in ``models/queries.py``,
``models/academic_queries.py`` and the services."""
from models.database import get_db

REMOVED_MARK = "~removed-"


def usage_by_section():
    """{section_id: (student_count, assignment_count)} - every student row and every assignment row
    (active or not) that blocks deleting a section / year / department / branch."""
    rows = get_db().execute(
        """SELECT s.id AS section_id,
                  (SELECT COUNT(*) FROM students st WHERE st.section_id = s.id) AS student_count,
                  (SELECT COUNT(*) FROM faculty_assignments fa WHERE fa.section_id = s.id) AS assignment_count
           FROM sections s"""
    ).fetchall()
    return {r["section_id"]: (r["student_count"], r["assignment_count"]) for r in rows}


def dashboard_counts():
    db = get_db()

    def one(sql):
        return db.execute(sql).fetchone()[0]

    return {
        # removed registrations are tombstoned + deactivated, so only live students are counted
        "student_count": one("SELECT COUNT(*) FROM students st JOIN users u ON u.id = st.user_id WHERE u.is_active = 1"),
        "removed_student_count": one(
            "SELECT COUNT(*) FROM students st JOIN users u ON u.id = st.user_id WHERE u.is_active = 0"),
        "unmapped_student_count": one(
            "SELECT COUNT(*) FROM students st JOIN users u ON u.id = st.user_id "
            "WHERE u.is_active = 1 AND st.section_id IS NULL"),
        "faculty_count": one("SELECT COUNT(*) FROM faculty f JOIN users u ON u.id = f.user_id WHERE u.is_active = 1"),
        "admin_count": one("SELECT COUNT(*) FROM users WHERE role = 'ADMIN' AND is_active = 1"),
        "meeting_count": one("SELECT COUNT(*) FROM meeting_requests"),
        "pending_permission_count": one("SELECT COUNT(*) FROM permission_requests WHERE status = 'PENDING'"),
    }


def list_students(section_id=None):
    """Every student registration (removed ones included, flagged by ``users.is_active = 0``)."""
    sql = """SELECT st.id, st.user_id, st.usn, st.phone, st.personal_email, st.college_email, st.branch,
                    st.department, st.year, st.section, st.section_id, st.created_at,
                    u.full_name, u.email, u.is_active, u.profile_picture_path, u.last_login_at
             FROM students st JOIN users u ON u.id = st.user_id"""
    params = ()
    if section_id is not None:
        sql += " WHERE st.section_id = ?"
        params = (section_id,)
    return get_db().execute(sql + " ORDER BY u.is_active DESC, lower(u.full_name), st.id LIMIT 2000", params).fetchall()


def get_student(student_id):
    return get_db().execute(
        """SELECT st.id, st.user_id, st.usn, st.phone, st.personal_email, st.college_email, st.branch,
                  st.department, st.year, st.section, st.section_id, st.created_at,
                  u.full_name, u.email, u.is_active, u.profile_picture_path, u.last_login_at
           FROM students st JOIN users u ON u.id = st.user_id WHERE st.id = ?""",
        (student_id,),
    ).fetchone()


def list_faculty():
    return get_db().execute(
        """SELECT f.id, f.user_id, f.faculty_code, f.department, f.professional_email, f.created_at,
                  u.full_name, u.email, u.is_active, u.profile_picture_path, u.last_login_at
           FROM faculty f JOIN users u ON u.id = f.user_id ORDER BY lower(u.full_name), f.id LIMIT 2000"""
    ).fetchall()


def list_meetings(status=None):
    sql = """SELECT mr.*, st.usn, st.section_id AS student_section_id, su.full_name AS student_name,
                    su.profile_picture_path AS student_picture, f.faculty_code, f.department AS faculty_department,
                    fu.full_name AS faculty_name, fu.profile_picture_path AS faculty_picture
             FROM meeting_requests mr
             JOIN students st ON st.id = mr.student_id JOIN users su ON su.id = st.user_id
             JOIN faculty f ON f.id = mr.faculty_id JOIN users fu ON fu.id = f.user_id"""
    params = ()
    if status:
        sql += " WHERE mr.status = ?"
        params = (status,)
    return get_db().execute(sql + " ORDER BY mr.requested_at DESC, mr.id DESC", params).fetchall()


def list_permission_requests():
    return get_db().execute(
        """SELECT pr.*, ru.full_name AS requester_name, ru.role AS requester_role,
                  ru.profile_picture_path AS requester_picture, au.full_name AS approver_name,
                  st.usn AS requester_usn, f.faculty_code AS requester_faculty_code
           FROM permission_requests pr
           JOIN users ru ON ru.id = pr.requester_user_id
           JOIN users au ON au.id = pr.target_approver_user_id
           LEFT JOIN students st ON st.user_id = ru.id
           LEFT JOIN faculty f ON f.user_id = ru.id
           ORDER BY (pr.status = 'PENDING') DESC, pr.created_at DESC, pr.id DESC"""
    ).fetchall()


def list_admins():
    return get_db().execute(
        "SELECT id, full_name, email, is_active, profile_picture_path, created_at, last_login_at "
        "FROM users WHERE role = 'ADMIN' ORDER BY created_at, id"
    ).fetchall()


def get_admin(user_id):
    return get_db().execute(
        "SELECT id, full_name, email, is_active, profile_picture_path, created_at, last_login_at "
        "FROM users WHERE id = ? AND role = 'ADMIN'", (user_id,)
    ).fetchone()
