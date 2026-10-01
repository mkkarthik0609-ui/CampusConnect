"""Central data-access layer. All SQL lives here; routes/services call these functions."""
from models.database import get_db


# ---------- users ----------

def create_user(role, email, password_hash, full_name):
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (role, email, password_hash, full_name) VALUES (?, ?, ?, ?)",
        (role, email, password_hash, full_name),
    )
    db.commit()
    return cur.lastrowid


def get_user_by_id(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_email(email):
    return get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def update_user_password(user_id, password_hash):
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
        (password_hash, user_id),
    )
    db.commit()


def update_user_profile_picture(user_id, path):
    db = get_db()
    db.execute(
        "UPDATE users SET profile_picture_path = ?, updated_at = datetime('now') WHERE id = ?",
        (path, user_id),
    )
    db.commit()


def update_user_theme(user_id, theme):
    db = get_db()
    db.execute(
        "UPDATE users SET theme_preference = ?, updated_at = datetime('now') WHERE id = ?",
        (theme, user_id),
    )
    db.commit()


def update_user_fields(user_id, fields: dict):
    if not fields:
        return
    db = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [user_id]
    db.execute(f"UPDATE users SET {set_clause}, updated_at = datetime('now') WHERE id = ?", params)
    db.commit()


# ---------- students ----------

def create_student(user_id, usn, branch, department, year, section, phone, personal_email, college_email):
    db = get_db()
    cur = db.execute(
        """INSERT INTO students
           (user_id, usn, branch, department, year, section, phone, personal_email, college_email)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, usn, branch, department, year, section, phone, personal_email, college_email),
    )
    db.commit()
    return cur.lastrowid


def get_student_by_user_id(user_id):
    return get_db().execute("SELECT * FROM students WHERE user_id = ?", (user_id,)).fetchone()


def get_student_by_id(student_id):
    return get_db().execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()


def get_student_with_user(student_id):
    return get_db().execute(
        """SELECT s.*, u.full_name, u.email, u.profile_picture_path, u.theme_preference
           FROM students s JOIN users u ON u.id = s.user_id WHERE s.id = ?""",
        (student_id,),
    ).fetchone()


def get_usn_exists(usn):
    return get_db().execute("SELECT 1 FROM students WHERE usn = ?", (usn,)).fetchone() is not None


def set_student_class_faculty(student_id, faculty_id):
    db = get_db()
    db.execute(
        "UPDATE students SET class_faculty_id = ?, updated_at = datetime('now') WHERE id = ?",
        (faculty_id, student_id),
    )
    db.commit()


def update_student_fields(student_id, fields: dict):
    if not fields:
        return
    db = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [student_id]
    db.execute(f"UPDATE students SET {set_clause}, updated_at = datetime('now') WHERE id = ?", params)
    db.commit()


def search_students_by_usn(query, limit=20):
    like = f"%{query}%"
    return get_db().execute(
        """SELECT s.id, s.usn, s.branch, s.department, s.year, s.section, u.full_name, u.profile_picture_path
           FROM students s JOIN users u ON u.id = s.user_id
           WHERE s.usn LIKE ? OR u.full_name LIKE ?
           ORDER BY s.usn LIMIT ?""",
        (like, like, limit),
    ).fetchall()


# ---------- faculty ----------

def create_faculty(user_id, faculty_code, department, professional_email):
    db = get_db()
    cur = db.execute(
        "INSERT INTO faculty (user_id, faculty_code, department, professional_email) VALUES (?, ?, ?, ?)",
        (user_id, faculty_code, department, professional_email),
    )
    db.commit()
    return cur.lastrowid


def get_faculty_by_user_id(user_id):
    return get_db().execute("SELECT * FROM faculty WHERE user_id = ?", (user_id,)).fetchone()


def get_faculty_by_id(faculty_id):
    return get_db().execute("SELECT * FROM faculty WHERE id = ?", (faculty_id,)).fetchone()


def get_faculty_with_user(faculty_id):
    return get_db().execute(
        """SELECT f.*, u.full_name, u.email, u.profile_picture_path, u.theme_preference
           FROM faculty f JOIN users u ON u.id = f.user_id WHERE f.id = ?""",
        (faculty_id,),
    ).fetchone()


def get_faculty_by_professional_email(email):
    return get_db().execute(
        "SELECT * FROM faculty WHERE professional_email = ? COLLATE NOCASE", (email,)
    ).fetchone()


def get_faculty_code_exists(faculty_code):
    return get_db().execute("SELECT 1 FROM faculty WHERE faculty_code = ?", (faculty_code,)).fetchone() is not None


def update_faculty_fields(faculty_id, fields: dict):
    if not fields:
        return
    db = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [faculty_id]
    db.execute(f"UPDATE faculty SET {set_clause}, updated_at = datetime('now') WHERE id = ?", params)
    db.commit()


def add_faculty_subject(faculty_id, subject_name):
    db = get_db()
    db.execute("INSERT INTO faculty_subjects (faculty_id, subject_name) VALUES (?, ?)", (faculty_id, subject_name))
    db.commit()


def clear_faculty_subjects(faculty_id):
    db = get_db()
    db.execute("DELETE FROM faculty_subjects WHERE faculty_id = ?", (faculty_id,))
    db.commit()


def get_faculty_subjects(faculty_id):
    return get_db().execute(
        "SELECT subject_name FROM faculty_subjects WHERE faculty_id = ? ORDER BY subject_name", (faculty_id,)
    ).fetchall()


def add_faculty_class(faculty_id, branch, department, year, section):
    db = get_db()
    db.execute(
        "INSERT INTO faculty_classes (faculty_id, branch, department, year, section) VALUES (?, ?, ?, ?, ?)",
        (faculty_id, branch, department, year, section),
    )
    db.commit()


def clear_faculty_classes(faculty_id):
    db = get_db()
    db.execute("DELETE FROM faculty_classes WHERE faculty_id = ?", (faculty_id,))
    db.commit()


def get_faculty_classes(faculty_id):
    return get_db().execute(
        "SELECT * FROM faculty_classes WHERE faculty_id = ? ORDER BY year, section", (faculty_id,)
    ).fetchall()


def search_faculty(query, limit=20):
    like = f"%{query}%"
    return get_db().execute(
        """SELECT f.id, f.faculty_code, f.department, u.full_name, u.profile_picture_path
           FROM faculty f JOIN users u ON u.id = f.user_id
           WHERE f.faculty_code LIKE ? OR u.full_name LIKE ?
           ORDER BY u.full_name LIMIT ?""",
        (like, like, limit),
    ).fetchall()


def list_all_faculty():
    return get_db().execute(
        """SELECT f.id, f.faculty_code, f.department, u.full_name, u.profile_picture_path
           FROM faculty f JOIN users u ON u.id = f.user_id ORDER BY u.full_name"""
    ).fetchall()


# ---------- supporting_relationships ----------

def create_supporting_request(student_id, faculty_id, requested_by):
    db = get_db()
    # UNIQUE(student_id, faculty_id): a previously REJECTED pair is re-opened instead of crashing.
    db.execute(
        """INSERT INTO supporting_relationships (student_id, faculty_id, requested_by, status)
           VALUES (?, ?, ?, 'PENDING')
           ON CONFLICT(student_id, faculty_id) DO UPDATE SET
               requested_by = excluded.requested_by, status = 'PENDING',
               created_at = datetime('now'), updated_at = datetime('now')""",
        (student_id, faculty_id, requested_by),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM supporting_relationships WHERE student_id = ? AND faculty_id = ?",
        (student_id, faculty_id),
    ).fetchone()["id"]


def get_supporting_relationship(student_id, faculty_id):
    return get_db().execute(
        "SELECT * FROM supporting_relationships WHERE student_id = ? AND faculty_id = ?",
        (student_id, faculty_id),
    ).fetchone()


def get_supporting_relationship_by_id(rel_id):
    return get_db().execute("SELECT * FROM supporting_relationships WHERE id = ?", (rel_id,)).fetchone()


def respond_supporting_relationship(rel_id, status):
    db = get_db()
    db.execute(
        "UPDATE supporting_relationships SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, rel_id),
    )
    db.commit()


def list_accepted_supporting_faculty_for_student(student_id):
    return get_db().execute(
        """SELECT f.id, f.faculty_code, f.department, u.full_name, u.profile_picture_path
           FROM supporting_relationships sr
           JOIN faculty f ON f.id = sr.faculty_id
           JOIN users u ON u.id = f.user_id
           WHERE sr.student_id = ? AND sr.status = 'ACCEPTED'
           ORDER BY u.full_name""",
        (student_id,),
    ).fetchall()


def list_accepted_supporting_students_for_faculty(faculty_id):
    return get_db().execute(
        """SELECT s.id, s.usn, s.branch, s.section, u.full_name, u.profile_picture_path
           FROM supporting_relationships sr
           JOIN students s ON s.id = sr.student_id
           JOIN users u ON u.id = s.user_id
           WHERE sr.faculty_id = ? AND sr.status = 'ACCEPTED' AND u.is_active = 1
           ORDER BY u.full_name""",
        (faculty_id,),
    ).fetchall()


def list_pending_supporting_requests_for_faculty(faculty_id):
    return get_db().execute(
        """SELECT sr.*, s.usn, u.full_name, u.profile_picture_path
           FROM supporting_relationships sr
           JOIN students s ON s.id = sr.student_id
           JOIN users u ON u.id = s.user_id
           WHERE sr.faculty_id = ? AND sr.status = 'PENDING' AND sr.requested_by = 'STUDENT' AND u.is_active = 1
           ORDER BY sr.created_at DESC""",
        (faculty_id,),
    ).fetchall()


def list_pending_supporting_requests_for_student(student_id):
    return get_db().execute(
        """SELECT sr.*, f.faculty_code, u.full_name, u.profile_picture_path
           FROM supporting_relationships sr
           JOIN faculty f ON f.id = sr.faculty_id
           JOIN users u ON u.id = f.user_id
           WHERE sr.student_id = ? AND sr.status = 'PENDING' AND sr.requested_by = 'FACULTY'
           ORDER BY sr.created_at DESC""",
        (student_id,),
    ).fetchall()


def is_faculty_accessible_to_student(student_id, faculty_id):
    """A student may reach a faculty member only through an ACTIVE class assignment that matches the
    student's registered section (Admin-controlled) or an accepted supporting relationship."""
    from models import academic_queries as aq
    if aq.is_student_in_faculty_scope(faculty_id, student_id):
        return True
    rel = get_db().execute(
        """SELECT 1 FROM supporting_relationships sr
           JOIN students st ON st.id = sr.student_id JOIN users u ON u.id = st.user_id AND u.is_active = 1
           WHERE sr.student_id = ? AND sr.faculty_id = ? AND sr.status = 'ACCEPTED'""",
        (student_id, faculty_id),
    ).fetchone()
    return rel is not None


def is_student_accessible_to_faculty(faculty_id, student_id):
    return is_faculty_accessible_to_student(student_id, faculty_id)


def get_user_by_identifier(identifier):
    """Login identifier: email, Faculty ID, or USN (case-insensitive)."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if "@" in identifier:
        return get_user_by_email(identifier.lower())
    db = get_db()
    row = db.execute(
        "SELECT u.* FROM users u JOIN faculty f ON f.user_id = u.id WHERE f.faculty_code = ? COLLATE NOCASE",
        (identifier,),
    ).fetchone()
    if row:
        return row
    return db.execute(
        "SELECT u.* FROM users u JOIN students s ON s.user_id = u.id WHERE s.usn = ? COLLATE NOCASE",
        (identifier,),
    ).fetchone()


# ---------- chats & messages ----------

def get_or_create_chat(student_id, faculty_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM chats WHERE student_id = ? AND faculty_id = ?", (student_id, faculty_id)
    ).fetchone()
    if row:
        return row
    cur = db.execute(
        "INSERT INTO chats (student_id, faculty_id) VALUES (?, ?)", (student_id, faculty_id)
    )
    db.commit()
    return db.execute("SELECT * FROM chats WHERE id = ?", (cur.lastrowid,)).fetchone()


def get_chat_by_id(chat_id):
    return get_db().execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()


def list_chats_for_student(student_id):
    return get_db().execute(
        """SELECT c.id AS chat_id, f.id AS faculty_id, f.faculty_code, u.full_name, u.profile_picture_path,
                  (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id AND m.is_seen = 0
                     AND m.sender_user_id != (SELECT user_id FROM students WHERE id = c.student_id)) AS unread_count,
                  (SELECT message_text FROM messages m WHERE m.chat_id = c.id ORDER BY m.created_at DESC LIMIT 1) AS last_message,
                  (SELECT created_at FROM messages m WHERE m.chat_id = c.id ORDER BY m.created_at DESC LIMIT 1) AS last_message_at
           FROM chats c
           JOIN faculty f ON f.id = c.faculty_id
           JOIN users u ON u.id = f.user_id
           WHERE c.student_id = ?
           ORDER BY last_message_at IS NULL, last_message_at DESC""",
        (student_id,),
    ).fetchall()


def list_chats_for_faculty(faculty_id):
    return get_db().execute(
        """SELECT c.id AS chat_id, s.id AS student_id, s.usn, u.full_name, u.profile_picture_path,
                  (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id AND m.is_seen = 0
                     AND m.sender_user_id != (SELECT user_id FROM faculty WHERE id = c.faculty_id)) AS unread_count,
                  (SELECT message_text FROM messages m WHERE m.chat_id = c.id ORDER BY m.created_at DESC LIMIT 1) AS last_message,
                  (SELECT created_at FROM messages m WHERE m.chat_id = c.id ORDER BY m.created_at DESC LIMIT 1) AS last_message_at
           FROM chats c
           JOIN students s ON s.id = c.student_id
           JOIN users u ON u.id = s.user_id
           WHERE c.faculty_id = ?
           ORDER BY last_message_at IS NULL, last_message_at DESC""",
        (faculty_id,),
    ).fetchall()


def create_message(chat_id, sender_user_id, message_text=None, attachment_path=None,
                    attachment_type=None, attachment_original_name=None):
    db = get_db()
    cur = db.execute(
        """INSERT INTO messages (chat_id, sender_user_id, message_text, attachment_path,
               attachment_type, attachment_original_name)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (chat_id, sender_user_id, message_text, attachment_path, attachment_type, attachment_original_name),
    )
    db.execute("UPDATE chats SET updated_at = datetime('now') WHERE id = ?", (chat_id,))
    db.commit()
    return cur.lastrowid


def get_message_by_id(message_id):
    return get_db().execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()


def list_messages_for_chat(chat_id):
    return get_db().execute(
        "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC", (chat_id,)
    ).fetchall()


def mark_messages_seen(chat_id, viewer_user_id):
    db = get_db()
    db.execute(
        """UPDATE messages SET is_seen = 1, seen_at = datetime('now')
           WHERE chat_id = ? AND sender_user_id != ? AND is_seen = 0""",
        (chat_id, viewer_user_id),
    )
    db.commit()


def edit_message(message_id, new_text):
    db = get_db()
    db.execute(
        "UPDATE messages SET message_text = ?, is_edited = 1, updated_at = datetime('now') WHERE id = ?",
        (new_text, message_id),
    )
    db.commit()


# SQL twin of is_faculty_accessible_to_student() for rows of ``chats c`` (an ACTIVE class assignment that
# matches the student's section, or an ACCEPTED supporting relationship). Keep the two in sync.
CHAT_ACCESSIBLE_SQL = """(
    EXISTS (SELECT 1 FROM students ast
            JOIN users asu ON asu.id = ast.user_id AND asu.is_active = 1
            JOIN faculty_assignments afa ON afa.section_id = ast.section_id AND afa.is_active = 1
            JOIN sections asec ON asec.id = afa.section_id
            JOIN academic_years ay ON ay.id = asec.academic_year_id
            JOIN departments ad ON ad.id = ay.department_id
            JOIN branches ab ON ab.id = ad.branch_id
            WHERE ast.id = c.student_id AND afa.faculty_id = c.faculty_id
              AND asec.is_active AND ay.is_active AND ad.is_active AND ab.is_active)
    OR EXISTS (SELECT 1 FROM supporting_relationships asr
            JOIN students ast2 ON ast2.id = asr.student_id
            JOIN users asu2 ON asu2.id = ast2.user_id AND asu2.is_active = 1
            WHERE asr.student_id = c.student_id AND asr.faculty_id = c.faculty_id AND asr.status = 'ACCEPTED')
)"""


def get_total_unread_for_user(user_id, role):
    """Unread incoming messages in chats the user can still use (a chat whose access was revoked,
    e.g. by removing the faculty assignment, no longer counts)."""
    db = get_db()
    if role == "STUDENT":
        owner_join = "JOIN students o ON o.id = c.student_id"
    else:
        owner_join = "JOIN faculty o ON o.id = c.faculty_id"
    row = db.execute(
        f"""SELECT COUNT(*) AS c FROM messages m JOIN chats c ON c.id = m.chat_id
            {owner_join}
            WHERE o.user_id = ? AND m.is_seen = 0 AND m.sender_user_id != ? AND {CHAT_ACCESSIBLE_SQL}""",
        (user_id, user_id),
    ).fetchone()
    return row["c"] if row else 0


# ---------- meeting_requests ----------

def create_meeting_request(student_id, faculty_id, reason, student_message):
    db = get_db()
    cur = db.execute(
        """INSERT INTO meeting_requests (student_id, faculty_id, reason, student_message, status)
           VALUES (?, ?, ?, ?, 'PENDING')""",
        (student_id, faculty_id, reason, student_message),
    )
    db.commit()
    return cur.lastrowid


def get_meeting_by_id(meeting_id):
    return get_db().execute("SELECT * FROM meeting_requests WHERE id = ?", (meeting_id,)).fetchone()


def respond_meeting_request(meeting_id, status, faculty_response, meeting_time_text):
    db = get_db()
    db.execute(
        """UPDATE meeting_requests
           SET status = ?, faculty_response = ?, meeting_time_text = ?, responded_at = datetime('now'),
               updated_at = datetime('now')
           WHERE id = ?""",
        (status, faculty_response, meeting_time_text, meeting_id),
    )
    db.commit()


def cancel_meeting_request(meeting_id, cancelled_by, reason):
    db = get_db()
    db.execute(
        """UPDATE meeting_requests
           SET status = 'CANCELLED', cancelled_by = ?, cancellation_reason = ?,
               cancelled_at = datetime('now'), updated_at = datetime('now')
           WHERE id = ?""",
        (cancelled_by, reason, meeting_id),
    )
    db.commit()


def complete_meeting_request(meeting_id, completed_by):
    db = get_db()
    db.execute(
        """UPDATE meeting_requests
           SET status = 'COMPLETED', completed_by = ?, completed_at = datetime('now'), updated_at = datetime('now')
           WHERE id = ?""",
        (completed_by, meeting_id),
    )
    db.commit()


def update_meeting_reminder_time(meeting_id):
    db = get_db()
    db.execute(
        "UPDATE meeting_requests SET last_reminder_at = datetime('now') WHERE id = ?", (meeting_id,)
    )
    db.commit()


def list_meetings_for_student(student_id, statuses=None):
    db = get_db()
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        return db.execute(
            f"""SELECT mr.*, f.faculty_code, u.full_name AS faculty_name
                FROM meeting_requests mr JOIN faculty f ON f.id = mr.faculty_id JOIN users u ON u.id = f.user_id
                WHERE mr.student_id = ? AND mr.status IN ({placeholders})
                ORDER BY mr.requested_at DESC""",
            [student_id, *statuses],
        ).fetchall()
    return db.execute(
        """SELECT mr.*, f.faculty_code, u.full_name AS faculty_name
           FROM meeting_requests mr JOIN faculty f ON f.id = mr.faculty_id JOIN users u ON u.id = f.user_id
           WHERE mr.student_id = ? ORDER BY mr.requested_at DESC""",
        (student_id,),
    ).fetchall()


def list_meetings_for_faculty(faculty_id, statuses=None):
    db = get_db()
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        return db.execute(
            f"""SELECT mr.*, s.usn, u.full_name AS student_name
                FROM meeting_requests mr JOIN students s ON s.id = mr.student_id JOIN users u ON u.id = s.user_id
                WHERE mr.faculty_id = ? AND mr.status IN ({placeholders})
                ORDER BY mr.requested_at DESC""",
            [faculty_id, *statuses],
        ).fetchall()
    return db.execute(
        """SELECT mr.*, s.usn, u.full_name AS student_name
           FROM meeting_requests mr JOIN students s ON s.id = mr.student_id JOIN users u ON u.id = s.user_id
           WHERE mr.faculty_id = ? ORDER BY mr.requested_at DESC""",
        (faculty_id,),
    ).fetchall()


def list_active_meetings_for_reminders():
    """Meetings that are still open (PENDING or ACCEPTED) and eligible for a reminder."""
    return get_db().execute(
        """SELECT * FROM meeting_requests WHERE status IN ('PENDING', 'ACCEPTED')"""
    ).fetchall()


def list_all_meetings_admin():
    return get_db().execute(
        """SELECT mr.*, su.full_name AS student_name, s.usn, fu.full_name AS faculty_name, f.faculty_code
           FROM meeting_requests mr
           JOIN students s ON s.id = mr.student_id JOIN users su ON su.id = s.user_id
           JOIN faculty f ON f.id = mr.faculty_id JOIN users fu ON fu.id = f.user_id
           ORDER BY mr.requested_at DESC"""
    ).fetchall()


# ---------- notifications ----------

def create_notification(user_id, notification_type, title, message, related_entity_type=None, related_entity_id=None):
    db = get_db()
    cur = db.execute(
        """INSERT INTO notifications (user_id, notification_type, title, message, related_entity_type, related_entity_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, notification_type, title, message, related_entity_type, related_entity_id),
    )
    db.commit()
    return cur.lastrowid


def list_notifications_for_user(user_id, limit=50):
    return get_db().execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
    ).fetchall()


def get_unread_notification_count(user_id):
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,)
    ).fetchone()
    return row["c"] if row else 0


def mark_notification_read(notification_id, user_id):
    db = get_db()
    cur = db.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notification_id, user_id)
    )
    db.commit()
    return cur.rowcount


def mark_all_notifications_read(user_id):
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    db.commit()


# ---------- permission_requests ----------

def create_permission_request(requester_user_id, target_approver_user_id, request_type, requested_changes_json, reason=None):
    db = get_db()
    cur = db.execute(
        """INSERT INTO permission_requests
           (requester_user_id, target_approver_user_id, request_type, requested_changes, reason, status)
           VALUES (?, ?, ?, ?, ?, 'PENDING')""",
        (requester_user_id, target_approver_user_id, request_type, requested_changes_json, reason),
    )
    db.commit()
    return cur.lastrowid


def get_permission_request_by_id(request_id):
    return get_db().execute("SELECT * FROM permission_requests WHERE id = ?", (request_id,)).fetchone()


def list_pending_permission_requests_for_approver(approver_user_id):
    """Admin: requests addressed to them. Faculty: student requests from every ACTIVELY assigned class."""
    db = get_db()
    user = db.execute("SELECT role FROM users WHERE id = ?", (approver_user_id,)).fetchone()
    if user and user["role"] == "FACULTY":
        return db.execute(
            """SELECT DISTINCT pr.*, u.full_name AS requester_name FROM permission_requests pr
               JOIN users u ON u.id = pr.requester_user_id
               JOIN students st ON st.user_id = pr.requester_user_id
               JOIN faculty_assignments fa ON fa.section_id = st.section_id AND fa.is_active = 1
               JOIN faculty f ON f.id = fa.faculty_id
               WHERE f.user_id = ? AND pr.status = 'PENDING' AND pr.request_type = 'STUDENT_PROFILE_CHANGE'
               ORDER BY pr.created_at DESC""",
            (approver_user_id,),
        ).fetchall()
    return db.execute(
        """SELECT pr.*, u.full_name AS requester_name FROM permission_requests pr
           JOIN users u ON u.id = pr.requester_user_id
           WHERE pr.target_approver_user_id = ? AND pr.status = 'PENDING'
           ORDER BY pr.created_at DESC""",
        (approver_user_id,),
    ).fetchall()


def list_permission_requests_by_requester(requester_user_id):
    return get_db().execute(
        "SELECT * FROM permission_requests WHERE requester_user_id = ? ORDER BY created_at DESC",
        (requester_user_id,),
    ).fetchall()


def decide_permission_request(request_id, status):
    db = get_db()
    db.execute(
        "UPDATE permission_requests SET status = ?, reviewed_at = datetime('now') WHERE id = ?",
        (status, request_id),
    )
    db.commit()


def list_all_permission_requests_admin():
    return get_db().execute(
        """SELECT pr.*, ru.full_name AS requester_name, au.full_name AS approver_name
           FROM permission_requests pr
           JOIN users ru ON ru.id = pr.requester_user_id
           JOIN users au ON au.id = pr.target_approver_user_id
           ORDER BY pr.created_at DESC"""
    ).fetchall()


# ---------- admin-facing listings ----------

def list_all_students_admin():
    return get_db().execute(
        """SELECT s.*, u.full_name, u.email, u.profile_picture_path
           FROM students s JOIN users u ON u.id = s.user_id ORDER BY u.full_name"""
    ).fetchall()


def list_all_faculty_admin():
    return get_db().execute(
        """SELECT f.*, u.full_name, u.email, u.profile_picture_path
           FROM faculty f JOIN users u ON u.id = f.user_id ORDER BY u.full_name"""
    ).fetchall()


def list_all_chats_admin():
    return get_db().execute(
        """SELECT c.id AS chat_id, su.full_name AS student_name, s.usn,
                  fu.full_name AS faculty_name, f.faculty_code, c.updated_at,
                  (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS message_count
           FROM chats c
           JOIN students s ON s.id = c.student_id JOIN users su ON su.id = s.user_id
           JOIN faculty f ON f.id = c.faculty_id JOIN users fu ON fu.id = f.user_id
           ORDER BY c.updated_at DESC"""
    ).fetchall()


def list_all_admins():
    return get_db().execute("SELECT * FROM users WHERE role = 'ADMIN' ORDER BY created_at").fetchall()


def count_admins():
    row = get_db().execute("SELECT COUNT(*) AS c FROM users WHERE role = 'ADMIN'").fetchone()
    return row["c"] if row else 0
