"""Data access for the academic hierarchy (Branch > Department > Year > Section),
faculty assignments and assignment requests. All SQL is parameterized."""
from models.database import get_db

# One row per academic combination, with the full chain of names + chain-active flag.
_COMBO_SELECT = """
    SELECT s.id AS section_id, s.name AS section_name,
           y.id AS year_id, y.name AS year_name, y.sort_order AS year_order,
           d.id AS department_id, d.name AS department_name,
           b.id AS branch_id, b.name AS branch_name,
           (s.is_active AND y.is_active AND d.is_active AND b.is_active) AS chain_active
    FROM sections s
    JOIN academic_years y ON y.id = s.academic_year_id
    JOIN departments d ON d.id = y.department_id
    JOIN branches b ON b.id = d.branch_id
"""
_COMBO_ORDER = " ORDER BY b.name, d.name, y.sort_order, y.name, s.name"

_CHAIN_ACTIVE_JOINS = """
    JOIN academic_years y ON y.id = s.academic_year_id
    JOIN departments d ON d.id = y.department_id
    JOIN branches b ON b.id = d.branch_id
"""
_CHAIN_ACTIVE_WHERE = "s.is_active AND y.is_active AND d.is_active AND b.is_active"


# ---------- hierarchy ----------

def list_branches():
    return get_db().execute("SELECT * FROM branches ORDER BY name").fetchall()


def get_branch(branch_id):
    return get_db().execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()


def get_branch_by_name(name):
    return get_db().execute("SELECT * FROM branches WHERE name = ?", (name,)).fetchone()


def create_branch(name):
    db = get_db()
    cur = db.execute("INSERT INTO branches (name) VALUES (?)", (name,))
    db.commit()
    return cur.lastrowid


def list_departments(branch_id=None):
    if branch_id is None:
        return get_db().execute("SELECT * FROM departments ORDER BY name").fetchall()
    return get_db().execute(
        "SELECT * FROM departments WHERE branch_id = ? ORDER BY name", (branch_id,)
    ).fetchall()


def list_active_department_names():
    return [r["name"] for r in get_db().execute(
        """SELECT DISTINCT d.name FROM departments d JOIN branches b ON b.id = d.branch_id
           WHERE d.is_active = 1 AND b.is_active = 1 ORDER BY d.name"""
    ).fetchall()]


def get_department(department_id):
    return get_db().execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()


def create_department(branch_id, name):
    db = get_db()
    cur = db.execute("INSERT INTO departments (branch_id, name) VALUES (?, ?)", (branch_id, name))
    db.commit()
    return cur.lastrowid


def list_years(department_id):
    return get_db().execute(
        "SELECT * FROM academic_years WHERE department_id = ? ORDER BY sort_order, name", (department_id,)
    ).fetchall()


def get_year(year_id):
    return get_db().execute("SELECT * FROM academic_years WHERE id = ?", (year_id,)).fetchone()


def create_year(department_id, name, sort_order):
    db = get_db()
    cur = db.execute(
        "INSERT INTO academic_years (department_id, name, sort_order) VALUES (?, ?, ?)",
        (department_id, name, sort_order),
    )
    db.commit()
    return cur.lastrowid


def list_sections(year_id):
    return get_db().execute(
        "SELECT * FROM sections WHERE academic_year_id = ? ORDER BY name", (year_id,)
    ).fetchall()


def get_section(section_id):
    return get_db().execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()


def create_section(year_id, name):
    db = get_db()
    cur = db.execute("INSERT INTO sections (academic_year_id, name) VALUES (?, ?)", (year_id, name))
    db.commit()
    return cur.lastrowid


_LEVEL_TABLES = {
    "branch": "branches", "department": "departments", "year": "academic_years", "section": "sections",
}
_LEVEL_WHERE = {
    "branch": "b.id = ?", "department": "d.id = ?", "year": "y.id = ?", "section": "s.id = ?",
}


def set_level_active(level, row_id, active):
    table = _LEVEL_TABLES[level]  # allow-list; never interpolate user input
    db = get_db()
    db.execute(f"UPDATE {table} SET is_active = ? WHERE id = ?", (1 if active else 0, row_id))
    db.commit()


def delete_level(level, row_id):
    table = _LEVEL_TABLES[level]
    db = get_db()
    db.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    db.commit()


def count_students_under(level, row_id):
    row = get_db().execute(
        f"""SELECT COUNT(*) AS c FROM students st
            JOIN sections s ON s.id = st.section_id {_CHAIN_ACTIVE_JOINS}
            WHERE {_LEVEL_WHERE[level]}""",
        (row_id,),
    ).fetchone()
    return row["c"]


def count_assignments_under(level, row_id):
    row = get_db().execute(
        f"""SELECT COUNT(*) AS c FROM faculty_assignments fa
            JOIN sections s ON s.id = fa.section_id {_CHAIN_ACTIVE_JOINS}
            WHERE {_LEVEL_WHERE[level]}""",
        (row_id,),
    ).fetchone()
    return row["c"]


def get_combo(section_id):
    return get_db().execute(_COMBO_SELECT + " WHERE s.id = ?", (section_id,)).fetchone()


def list_combos(active_only=False):
    sql = _COMBO_SELECT
    if active_only:
        sql += f" WHERE {_CHAIN_ACTIVE_WHERE}"
    return get_db().execute(sql + _COMBO_ORDER).fetchall()


def find_combo_by_names(branch, department, year, section):
    return get_db().execute(
        _COMBO_SELECT + " WHERE b.name = ? AND d.name = ? AND y.name = ? AND s.name = ?",
        (branch, department, year, section),
    ).fetchone()


def list_combos_with_counts():
    return get_db().execute(
        """SELECT c.*,
              (SELECT COUNT(*) FROM students st JOIN users su ON su.id = st.user_id
                 WHERE st.section_id = c.section_id AND su.is_active = 1) AS student_count,
              (SELECT COUNT(*) FROM faculty_assignments fa
                 WHERE fa.section_id = c.section_id AND fa.is_active = 1) AS faculty_count
           FROM (""" + _COMBO_SELECT + ") c ORDER BY c.branch_name, c.department_name, c.year_order, c.section_name"
    ).fetchall()


# ---------- faculty assignments ----------

def get_assignment(assignment_id):
    return get_db().execute("SELECT * FROM faculty_assignments WHERE id = ?", (assignment_id,)).fetchone()


def get_assignment_for(faculty_id, section_id):
    return get_db().execute(
        "SELECT * FROM faculty_assignments WHERE faculty_id = ? AND section_id = ?", (faculty_id, section_id)
    ).fetchone()


def upsert_assignment(faculty_id, section_id, assigned_by):
    """Create the assignment or re-activate a previously deactivated one."""
    db = get_db()
    existing = get_assignment_for(faculty_id, section_id)
    if existing:
        db.execute(
            """UPDATE faculty_assignments SET is_active = 1, deactivated_at = NULL, assigned_by = ?
               WHERE id = ?""",
            (assigned_by, existing["id"]),
        )
        db.commit()
        return existing["id"]
    cur = db.execute(
        "INSERT INTO faculty_assignments (faculty_id, section_id, assigned_by) VALUES (?, ?, ?)",
        (faculty_id, section_id, assigned_by),
    )
    db.commit()
    return cur.lastrowid


def deactivate_assignment(assignment_id):
    db = get_db()
    db.execute(
        "UPDATE faculty_assignments SET is_active = 0, deactivated_at = datetime('now') WHERE id = ?",
        (assignment_id,),
    )
    db.commit()


def list_assignments_for_faculty(faculty_id, active_only=True):
    sql = """SELECT fa.id AS assignment_id, fa.is_active AS assignment_active, fa.created_at AS assigned_at, c.*,
                    (SELECT COUNT(*) FROM students st JOIN users su ON su.id = st.user_id
                      WHERE st.section_id = c.section_id AND su.is_active = 1) AS student_count
             FROM faculty_assignments fa
             JOIN (""" + _COMBO_SELECT + """) c ON c.section_id = fa.section_id
             WHERE fa.faculty_id = ?"""
    if active_only:
        sql += " AND fa.is_active = 1 AND c.chain_active = 1"
    sql += " ORDER BY c.branch_name, c.department_name, c.year_order, c.year_name, c.section_name"
    return get_db().execute(sql, (faculty_id,)).fetchall()


def list_faculty_for_section(section_id, active_only=True):
    sql = """SELECT fa.id AS assignment_id, fa.is_active AS assignment_active, f.id AS faculty_id,
                    f.faculty_code, u.full_name, u.profile_picture_path
             FROM faculty_assignments fa
             JOIN faculty f ON f.id = fa.faculty_id
             JOIN users u ON u.id = f.user_id
             WHERE fa.section_id = ?"""
    if active_only:
        sql += " AND fa.is_active = 1"
    return get_db().execute(sql + " ORDER BY f.faculty_code", (section_id,)).fetchall()


def is_faculty_assigned_to_section(faculty_id, section_id):
    row = get_db().execute(
        f"""SELECT 1 FROM faculty_assignments fa
            JOIN sections s ON s.id = fa.section_id {_CHAIN_ACTIVE_JOINS}
            WHERE fa.faculty_id = ? AND fa.section_id = ? AND fa.is_active = 1 AND {_CHAIN_ACTIVE_WHERE}""",
        (faculty_id, section_id),
    ).fetchone()
    return row is not None


def is_student_in_faculty_scope(faculty_id, student_id):
    """True when the student's registered section is an ACTIVE assignment of the faculty and the
    student's account is still active (a removed registration is unreachable)."""
    row = get_db().execute(
        f"""SELECT 1 FROM students st
            JOIN users su ON su.id = st.user_id AND su.is_active = 1
            JOIN faculty_assignments fa ON fa.section_id = st.section_id
            JOIN sections s ON s.id = fa.section_id {_CHAIN_ACTIVE_JOINS}
            WHERE st.id = ? AND fa.faculty_id = ? AND fa.is_active = 1 AND {_CHAIN_ACTIVE_WHERE}""",
        (student_id, faculty_id),
    ).fetchone()
    return row is not None


def list_assigned_faculty_for_student(student_id):
    return get_db().execute(
        f"""SELECT f.id, f.faculty_code, f.department, u.full_name, u.profile_picture_path
            FROM students st
            JOIN sections s ON s.id = st.section_id {_CHAIN_ACTIVE_JOINS}
            JOIN faculty_assignments fa ON fa.section_id = st.section_id AND fa.is_active = 1
            JOIN faculty f ON f.id = fa.faculty_id
            JOIN users u ON u.id = f.user_id AND u.is_active = 1
            WHERE st.id = ? AND {_CHAIN_ACTIVE_WHERE} ORDER BY u.full_name""",
        (student_id,),
    ).fetchall()


def list_students_for_section(section_id):
    return get_db().execute(
        """SELECT st.id, st.usn, st.phone, st.college_email, u.full_name, u.profile_picture_path
           FROM students st JOIN users u ON u.id = st.user_id
           WHERE st.section_id = ? AND u.is_active = 1 ORDER BY st.usn""",
        (section_id,),
    ).fetchall()


def search_students_in_faculty_scope(faculty_id, query, limit=30):
    like = f"%{query}%"
    return get_db().execute(
        f"""SELECT DISTINCT st.id, st.usn, st.branch, st.department, st.year, st.section,
                   u.full_name, u.profile_picture_path
            FROM students st
            JOIN users u ON u.id = st.user_id AND u.is_active = 1
            JOIN faculty_assignments fa ON fa.section_id = st.section_id AND fa.is_active = 1
            JOIN sections s ON s.id = fa.section_id {_CHAIN_ACTIVE_JOINS}
            WHERE fa.faculty_id = ? AND {_CHAIN_ACTIVE_WHERE} AND (st.usn LIKE ? OR u.full_name LIKE ?)
            ORDER BY st.usn LIMIT ?""",
        (faculty_id, like, like, limit),
    ).fetchall()


# ---------- assignment requests ----------

def create_assignment_request(faculty_id, section_id, note):
    db = get_db()
    cur = db.execute(
        "INSERT INTO faculty_assignment_requests (faculty_id, section_id, note) VALUES (?, ?, ?)",
        (faculty_id, section_id, note),
    )
    db.commit()
    return cur.lastrowid


def get_assignment_request(request_id):
    return get_db().execute(
        "SELECT * FROM faculty_assignment_requests WHERE id = ?", (request_id,)
    ).fetchone()


def has_pending_request(faculty_id, section_id):
    return get_db().execute(
        """SELECT 1 FROM faculty_assignment_requests
           WHERE faculty_id = ? AND section_id = ? AND status = 'PENDING'""",
        (faculty_id, section_id),
    ).fetchone() is not None


def decide_assignment_request(request_id, status, reviewer_user_id):
    db = get_db()
    db.execute(
        """UPDATE faculty_assignment_requests
           SET status = ?, reviewed_at = datetime('now'), reviewed_by = ? WHERE id = ?""",
        (status, reviewer_user_id, request_id),
    )
    db.commit()


def list_assignment_requests(status=None, faculty_id=None):
    sql = """SELECT r.*, f.faculty_code, f.department AS faculty_department, u.full_name AS faculty_name,
                    u.profile_picture_path AS faculty_picture, c.branch_name, c.department_name,
                    c.year_name, c.section_name, c.chain_active
             FROM faculty_assignment_requests r
             JOIN faculty f ON f.id = r.faculty_id
             JOIN users u ON u.id = f.user_id
             JOIN (""" + _COMBO_SELECT + """) c ON c.section_id = r.section_id
             WHERE 1 = 1"""
    params = []
    if status:
        sql += " AND r.status = ?"
        params.append(status)
    if faculty_id:
        sql += " AND r.faculty_id = ?"
        params.append(faculty_id)
    sql += " ORDER BY (r.status = 'PENDING') DESC, r.created_at DESC, r.id DESC"
    return get_db().execute(sql, params).fetchall()


def count_pending_assignment_requests():
    return get_db().execute(
        "SELECT COUNT(*) AS c FROM faculty_assignment_requests WHERE status = 'PENDING'"
    ).fetchone()["c"]


# ---------- students (hierarchy-linked) ----------

def set_student_section(student_id, section_id, branch, department, year, section):
    db = get_db()
    db.execute(
        """UPDATE students SET section_id = ?, branch = ?, department = ?, year = ?, section = ?,
           updated_at = datetime('now') WHERE id = ?""",
        (section_id, branch, department, year, section, student_id),
    )
    db.commit()


def list_students_admin(section_id=None):
    sql = """SELECT st.*, u.full_name, u.email, u.is_active, u.profile_picture_path
             FROM students st JOIN users u ON u.id = st.user_id"""
    params = ()
    if section_id:
        sql += " WHERE st.section_id = ?"
        params = (section_id,)
    return get_db().execute(sql + " ORDER BY u.is_active DESC, u.full_name", params).fetchall()


REMOVED_MARK = "~removed-"


def is_removed_usn(usn):
    """True for a USN that carries the tombstone written by archive_student_registration()."""
    return REMOVED_MARK in (usn or "")


def archive_student_registration(student_id):
    """Deactivate the account and free its login email / USN so the person can register again.
    Chats, meetings and notifications are kept; only the identifiers are tombstoned.

    Idempotent: returns True only for the call that actually removed the registration; unknown ids and
    already-removed students return False and are left untouched (never tombstoned twice). The
    tombstone is claimed with a single conditional UPDATE, so two concurrent calls cannot both win."""
    db = get_db()
    st = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not st or is_removed_usn(st["usn"]):
        return False
    tag = f"removed-{st['id']}"
    claimed = db.execute(
        "UPDATE students SET usn = ?, college_email = ?, updated_at = datetime('now') "
        "WHERE id = ? AND usn NOT LIKE '%~removed-%'",
        (f"{st['usn']}~{tag}", f"{tag}+{st['college_email']}", st["id"]),
    )
    if claimed.rowcount != 1:
        db.rollback()
        return False
    db.execute("UPDATE users SET is_active = 0, email = ?, updated_at = datetime('now') WHERE id = ?",
               (f"{tag}+{st['college_email']}", st["user_id"]))
    db.execute("DELETE FROM supporting_relationships WHERE student_id = ? AND status = 'PENDING'", (st["id"],))
    db.execute(
        "UPDATE meeting_requests SET status = 'CANCELLED', cancelled_by = 'FACULTY', "
        "cancellation_reason = 'Student registration removed by Admin', cancelled_at = datetime('now') "
        "WHERE student_id = ? AND status IN ('PENDING', 'ACCEPTED')", (st["id"],))
    db.commit()
    return True
