"""Read queries that join everything the chat / meeting / supporting / faculty screens need in one go
(names, codes, pictures, section ids). Pure SQL; authorization is decided by the services/routers."""
from models.database import get_db
from models.queries import CHAT_ACCESSIBLE_SQL


def _like(query):
    """``%query%`` with LIKE wildcards in the user's text escaped (pair with ``ESCAPE '\\'``)."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# ---------- students / faculty cards ----------

def get_student_card(student_id):
    return get_db().execute(
        """SELECT st.id, st.usn, st.section_id, st.user_id, u.full_name, u.profile_picture_path
           FROM students st JOIN users u ON u.id = st.user_id WHERE st.id = ?""",
        (student_id,),
    ).fetchone()


def get_faculty_card(faculty_id):
    return get_db().execute(
        """SELECT f.id, f.faculty_code, f.department, f.user_id, u.full_name, u.profile_picture_path
           FROM faculty f JOIN users u ON u.id = f.user_id WHERE f.id = ?""",
        (faculty_id,),
    ).fetchone()


# ---------- meetings ----------

_MEETING_SELECT = """
    SELECT mr.*,
           st.usn, st.section_id AS student_section_id, su.full_name AS student_name,
           su.profile_picture_path AS student_picture,
           f.faculty_code, f.department AS faculty_department, fu.full_name AS faculty_name,
           fu.profile_picture_path AS faculty_picture
    FROM meeting_requests mr
    JOIN students st ON st.id = mr.student_id JOIN users su ON su.id = st.user_id
    JOIN faculty f ON f.id = mr.faculty_id JOIN users fu ON fu.id = f.user_id
"""


def list_meetings(student_id=None, faculty_id=None, statuses=None, limit=None):
    sql = _MEETING_SELECT + " WHERE 1 = 1"
    params = []
    if student_id is not None:
        sql += " AND mr.student_id = ?"
        params.append(student_id)
    if faculty_id is not None:
        sql += " AND mr.faculty_id = ?"
        params.append(faculty_id)
    if statuses:
        sql += " AND mr.status IN (" + ",".join("?" for _ in statuses) + ")"
        params.extend(statuses)
    sql += " ORDER BY mr.requested_at DESC, mr.id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return get_db().execute(sql, params).fetchall()


def get_meeting_full(meeting_id):
    return get_db().execute(_MEETING_SELECT + " WHERE mr.id = ?", (meeting_id,)).fetchone()


# ---------- chats ----------

_CHAT_LIST_TAIL = """
    (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id AND m.is_seen = 0
       AND m.sender_user_id != ?) AS unread_count,
    lm.message_text AS last_message_text, lm.attachment_original_name AS last_attachment_name,
    lm.created_at AS last_message_at, lm.sender_user_id AS last_sender_user_id, c.updated_at AS chat_updated_at
"""
_CHAT_LIST_ORDER = " ORDER BY (lm.id IS NULL), lm.created_at DESC, c.id DESC"
_LAST_MESSAGE_JOIN = """
    LEFT JOIN messages lm ON lm.id = (SELECT m2.id FROM messages m2 WHERE m2.chat_id = c.id
                                      ORDER BY m2.created_at DESC, m2.id DESC LIMIT 1)
"""


def list_chats_for_student(student_id, viewer_user_id):
    """Chats of a student whose faculty is still reachable (see CHAT_ACCESSIBLE_SQL)."""
    return get_db().execute(
        f"""SELECT c.id AS chat_id, f.id AS faculty_id, f.faculty_code, f.department, u.full_name,
                   u.profile_picture_path, {_CHAT_LIST_TAIL}
            FROM chats c JOIN faculty f ON f.id = c.faculty_id JOIN users u ON u.id = f.user_id
            {_LAST_MESSAGE_JOIN}
            WHERE c.student_id = ? AND {CHAT_ACCESSIBLE_SQL}{_CHAT_LIST_ORDER}""",
        (viewer_user_id, student_id),
    ).fetchall()


def list_chats_for_faculty(faculty_id, viewer_user_id):
    return get_db().execute(
        f"""SELECT c.id AS chat_id, s.id AS student_id, s.usn, s.section_id, u.full_name,
                   u.profile_picture_path, {_CHAT_LIST_TAIL}
            FROM chats c JOIN students s ON s.id = c.student_id JOIN users u ON u.id = s.user_id
            {_LAST_MESSAGE_JOIN}
            WHERE c.faculty_id = ? AND {CHAT_ACCESSIBLE_SQL}{_CHAT_LIST_ORDER}""",
        (viewer_user_id, faculty_id),
    ).fetchall()


def list_messages(chat_id, after_id=0):
    return get_db().execute(
        "SELECT * FROM messages WHERE chat_id = ? AND id > ? ORDER BY created_at ASC, id ASC",
        (chat_id, after_id or 0),
    ).fetchall()


# ---------- supporting relationships ----------

def search_faculty(query, student_id, limit=20):
    """Faculty by name / code with the student's relationship to each (NULL when none)."""
    like = _like(query)
    return get_db().execute(
        """SELECT f.id, f.faculty_code, f.department, u.full_name, u.profile_picture_path,
                  sr.id AS rel_id, sr.status AS rel_status, sr.requested_by AS rel_requested_by
           FROM faculty f JOIN users u ON u.id = f.user_id AND u.is_active = 1
           LEFT JOIN supporting_relationships sr ON sr.faculty_id = f.id AND sr.student_id = ?
           WHERE f.faculty_code LIKE ? ESCAPE '\\' OR u.full_name LIKE ? ESCAPE '\\'
           ORDER BY u.full_name, f.id LIMIT ?""",
        (student_id, like, like, limit),
    ).fetchall()


def relationships_for_faculty_students(faculty_id, student_ids):
    """{student_id: row(id, status, requested_by)} for the given students."""
    if not student_ids:
        return {}
    marks = ",".join("?" for _ in student_ids)
    rows = get_db().execute(
        f"""SELECT id, student_id, status, requested_by FROM supporting_relationships
            WHERE faculty_id = ? AND student_id IN ({marks})""",
        [faculty_id, *student_ids],
    ).fetchall()
    return {r["student_id"]: r for r in rows}


_REL_SELECT = """
    SELECT sr.*, st.usn, st.section_id, su.full_name AS student_name, su.profile_picture_path AS student_picture,
           f.faculty_code, f.department AS faculty_department, fu.full_name AS faculty_name,
           fu.profile_picture_path AS faculty_picture
    FROM supporting_relationships sr
    JOIN students st ON st.id = sr.student_id JOIN users su ON su.id = st.user_id
    JOIN faculty f ON f.id = sr.faculty_id JOIN users fu ON fu.id = f.user_id
"""


def list_relationships(student_id=None, faculty_id=None, status=None):
    sql = _REL_SELECT + " WHERE su.is_active = 1 AND fu.is_active = 1"
    params = []
    if student_id is not None:
        sql += " AND sr.student_id = ?"
        params.append(student_id)
    if faculty_id is not None:
        sql += " AND sr.faculty_id = ?"
        params.append(faculty_id)
    if status:
        sql += " AND sr.status = ?"
        params.append(status)
    sql += " ORDER BY (sr.status = 'PENDING') DESC, sr.updated_at DESC, sr.id DESC"
    return get_db().execute(sql, params).fetchall()


def get_relationship_full(rel_id):
    return get_db().execute(_REL_SELECT + " WHERE sr.id = ?", (rel_id,)).fetchone()
