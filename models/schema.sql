PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('STUDENT', 'FACULTY', 'ADMIN')),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    profile_picture_path TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    theme_preference TEXT NOT NULL DEFAULT 'light' CHECK (theme_preference IN ('light', 'dark')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS faculty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    faculty_code TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    professional_email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_faculty_code ON faculty(faculty_code);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    usn TEXT NOT NULL UNIQUE,
    branch TEXT NOT NULL,
    department TEXT NOT NULL,
    year TEXT NOT NULL,
    section TEXT NOT NULL,
    phone TEXT NOT NULL,
    personal_email TEXT NOT NULL,
    college_email TEXT NOT NULL UNIQUE,
    class_faculty_id INTEGER REFERENCES faculty(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_students_usn ON students(usn);
CREATE INDEX IF NOT EXISTS idx_students_class_faculty ON students(class_faculty_id);

CREATE TABLE IF NOT EXISTS faculty_subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    subject_name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_faculty_subjects_faculty ON faculty_subjects(faculty_id);

CREATE TABLE IF NOT EXISTS faculty_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    branch TEXT NOT NULL,
    department TEXT NOT NULL,
    year TEXT NOT NULL,
    section TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_faculty_classes_faculty ON faculty_classes(faculty_id);

CREATE TABLE IF NOT EXISTS permission_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_approver_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL CHECK (request_type IN ('STUDENT_PROFILE_CHANGE', 'FACULTY_PROFILE_CHANGE')),
    requested_changes TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_permreq_approver ON permission_requests(target_approver_user_id, status);
CREATE INDEX IF NOT EXISTS idx_permreq_requester ON permission_requests(requester_user_id);

CREATE TABLE IF NOT EXISTS supporting_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    requested_by TEXT NOT NULL CHECK (requested_by IN ('STUDENT', 'FACULTY')),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, faculty_id)
);
CREATE INDEX IF NOT EXISTS idx_supporting_student ON supporting_relationships(student_id, status);
CREATE INDEX IF NOT EXISTS idx_supporting_faculty ON supporting_relationships(faculty_id, status);

CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, faculty_id)
);
CREATE INDEX IF NOT EXISTS idx_chats_student ON chats(student_id);
CREATE INDEX IF NOT EXISTS idx_chats_faculty ON chats(faculty_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_text TEXT,
    attachment_path TEXT,
    attachment_type TEXT,
    attachment_original_name TEXT,
    is_seen INTEGER NOT NULL DEFAULT 0,
    seen_at TEXT,
    is_edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_unseen ON messages(chat_id, is_seen);

CREATE TABLE IF NOT EXISTS meeting_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    student_message TEXT,
    faculty_response TEXT,
    meeting_time_text TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'COMPLETED', 'CANCELLED')),
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    responded_at TEXT,
    completed_at TEXT,
    completed_by TEXT CHECK (completed_by IN ('STUDENT', 'FACULTY')),
    cancelled_at TEXT,
    cancelled_by TEXT CHECK (cancelled_by IN ('STUDENT', 'FACULTY')),
    cancellation_reason TEXT,
    last_reminder_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_meetings_student ON meeting_requests(student_id, status);
CREATE INDEX IF NOT EXISTS idx_meetings_faculty ON meeting_requests(faculty_id, status);
CREATE INDEX IF NOT EXISTS idx_meetings_active_reminder ON meeting_requests(status, last_reminder_at);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    related_entity_type TEXT,
    related_entity_id INTEGER,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);

-- ---------------------------------------------------------------------------
-- Academic hierarchy (Admin-controlled): Branch -> Department -> Year -> Section
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (branch_id, name)
);
CREATE INDEX IF NOT EXISTS idx_departments_branch ON departments(branch_id);

CREATE TABLE IF NOT EXISTS academic_years (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (department_id, name)
);
CREATE INDEX IF NOT EXISTS idx_years_department ON academic_years(department_id);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year_id INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (academic_year_id, name)
);
CREATE INDEX IF NOT EXISTS idx_sections_year ON sections(academic_year_id);

-- Faculty -> many academic combinations (a combination is one sections row).
CREATE TABLE IF NOT EXISTS faculty_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    is_active INTEGER NOT NULL DEFAULT 1,
    assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    deactivated_at TEXT,
    UNIQUE (faculty_id, section_id)
);
CREATE INDEX IF NOT EXISTS idx_fassign_faculty ON faculty_assignments(faculty_id, is_active);
CREATE INDEX IF NOT EXISTS idx_fassign_section ON faculty_assignments(section_id, is_active);

-- Faculty asks Admin to join a new combination; nothing is granted until APPROVED.
CREATE TABLE IF NOT EXISTS faculty_assignment_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at TEXT,
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_farq_status ON faculty_assignment_requests(status);
CREATE INDEX IF NOT EXISTS idx_farq_faculty ON faculty_assignment_requests(faculty_id, status);

-- Auth hardening: failed-login tracking for throttling / temporary lockout.
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier TEXT NOT NULL,
    ip TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ident ON login_attempts(identifier, created_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(ip, created_at);
