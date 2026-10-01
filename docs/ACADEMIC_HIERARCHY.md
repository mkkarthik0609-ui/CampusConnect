# Academic Hierarchy

Campus Connect models the college structure as a strict, **Admin-controlled** tree:

```
Branch  ->  Department  ->  Academic Year  ->  Section
  CSE   ->     AIML     ->   3rd Year      ->     A
```

A *class* (also called a "combination") is one leaf of this tree, i.e. one row in the
`sections` table. Every student belongs to exactly one section; every faculty member can be
assigned to many sections, and a section can have several faculty.

## 1. Default structure (seeded on first start)

`services/academic_service.seed_default_structure()` runs once, only while the `branches`
table is empty:

| Level | Default values |
|---|---|
| Branch | `CSE` |
| Departments (under CSE) | `AIML`, `AIDE`, `GenAI`, `Cybersecurity`, `Blockchain`, `IoT` |
| Academic years (per department) | `1st Year`, `2nd Year`, `3rd Year`, `4th Year` |
| Sections (per year) | `A`, `B`, `C` (single letters only) |

That is 1 x 6 x 4 x 3 = **72 classes** out of the box. Admin can then add branches, departments,
years (1 to 9) and sections, or deactivate / delete them. Because seeding only runs when no branch
exists, it never overwrites Admin edits.

Section labels are a single letter (`SECTION_RE = ^[A-Za-z]$`). Free text such as `3A` is not
accepted for new data; legacy values like `3A` are normalised to `A` when backfilled.

## 2. Admin authority

Only `ADMIN` users (routes in `api/routers/admin_academic.py`, all guarded by
`require_role("ADMIN")`) can:

- add a branch, department, year, or sections (`/admin/academics/...`);
- deactivate / reactivate any level (hides it from new registrations; existing data is kept);
- delete a level **only if** no student and no faculty assignment sits beneath it
  (`academic_service.delete_unused`), otherwise Admin must deactivate it;
- assign or remove a faculty member from a class (`/admin/assignments/...`);
- approve or reject a faculty request to join a class (`/admin/assignment-requests/...`);
- remove a student's registration (section 4).

Students and faculty can only *select* existing, active rows. Every client-supplied section id is
re-validated server-side by `academic_service.resolve_section()`, which rejects ids that do not exist
or whose chain (section, year, department, branch) is not fully active.

A level is "effectively active" only when it and all its ancestors are active
(`chain_active` in `models/academic_queries.py`). Deactivating CSE therefore hides every class
beneath it without touching their rows.

## 3. Student registration

1. Student opens `/signup/student` (college email + password + captcha).
2. On the details page they pick **Branch, Department, Year, Section** from the Admin-defined tree
   (`/academic/tree.json` supplies the active options) and submit a `section_id`.
3. `auth_service.register_student()` calls `resolve_section()` and stores `students.section_id`;
   the human-readable `branch / department / year / section` columns are kept in sync as a snapshot.

### No self-service class change

A student cannot edit their class, and the profile-change workflow cannot be used to move class:

- `permission_service.STUDENT_EDITABLE_FIELDS = {"phone", "personal_email"}`; `api/routers/student.py`
  only forwards those two fields, and the service drops anything outside the allow-list.
- If a student registered in the wrong class, Admin uses **Remove registration**
  (`POST /admin/students/<id>/remove-registration`, `aq.archive_student_registration`). This
  deactivates the account and *tombstones* the login email and USN (`removed-<id>+...`,
  `<usn>~removed-<id>`), which frees both so the person can register again with the correct class.
  Chats, meetings and notifications are kept; the old account simply cannot log in any more.

## 4. Faculty assignments

- Table `faculty_assignments (faculty_id, section_id, is_active)` with `UNIQUE(faculty_id, section_id)`.
- A faculty member may hold many assignments (for example CSE/AIML/3rd Year/A and CSE/AIML/3rd Year/B).
- A section may have several faculty (`SELECT ... WHERE section_id = ?` returns FAC001, FAC002, ...).
- Removing an assignment is a soft delete (`is_active = 0`, `deactivated_at` set); re-assigning
  re-activates the same row (`aq.upsert_assignment`). History is never lost.
- Faculty signup no longer picks classes. A new faculty account starts with **no** assignments and
  therefore no access to any student until Admin assigns (or approves) classes.

### Request / approve flow

1. Faculty opens **My classes** (`/faculty/classes`) and requests a class
   (`assignment_service.faculty_request`). Duplicate requests and classes they already hold are
   rejected. Every Admin gets a notification.
2. Admin reviews `/admin/assignment-requests`
   (`assignment_service.decide_request`): *approve* creates/re-activates the assignment, *reject*
   only records the decision. A request grants nothing while `PENDING`.
3. If Admin assigns the same combination directly, the matching pending request is auto-approved.
4. The faculty member is notified of the outcome either way.

## 5. Enforced access rules (server-side)

All rules are enforced on the server; hiding links in the UI is never relied upon.

| Rule | Implemented in |
|---|---|
| A faculty member "owns" a student only if the student's `section_id` has an **active** assignment for that faculty, and the whole section/year/department/branch chain is active | `models/academic_queries.py` -> `is_student_in_faculty_scope(faculty_id, student_id)` |
| Faculty may open a class page only for an active assignment of their own (otherwise HTTP 403) | `api/routers/faculty.py` (class endpoints; HTTP 403 unless `aq.is_faculty_assigned_to_section`) |
| Student <-> faculty reachability = class scope **or** an ACCEPTED supporting relationship | `models/queries.py` -> `is_faculty_accessible_to_student` / `is_student_accessible_to_faculty`; mirrored in `services/assignment_service.py` -> `faculty_can_access_student` / `student_can_access_faculty` |
| Only Admin can grant or revoke assignments; faculty can only *request* | `services/assignment_service.py` (`admin_assign`, `admin_remove`, `faculty_request`, `decide_request`) + `api/routers/admin_academic.py` (`require_role("ADMIN")`) |
| Opening / reading / sending in a chat requires participation **and** current scope (a student moved out of the faculty's classes becomes unreadable to that faculty) | `services/chat_service.py` -> `open_chat`, `open_chat_as_faculty`, `get_chat_for_participant` |
| Meeting requests need scope or accepted supporting link; faculty can respond only for students still in scope | `services/meeting_service.py` -> `request_meeting`, `respond_to_meeting` |
| Faculty may only send a supporting-relationship request to students in their classes | `services/supporting_service.py` -> `faculty_request_student` |
| Only the student's own in-scope faculty may approve that student's profile-change request | `services/permission_service.py` -> `decide_permission_request` |
| Faculty student search is limited to their assigned classes | `models/academic_queries.py` -> `search_students_in_faculty_scope` |
| Client-supplied section ids must exist and be fully active | `services/academic_service.py` -> `resolve_section` |
| Student class cannot be self-edited | `services/permission_service.py` (`STUDENT_EDITABLE_FIELDS`), `api/routers/student.py` |

Consequences worth knowing:

- Removing a faculty assignment immediately cuts that faculty off from the section's students for
  new chats, meetings and existing conversations. The data stays; it just becomes inaccessible
  to them.
- Two faculty on the same section each have their own 1:1 chat with each student
  (`chats` is `UNIQUE(student_id, faculty_id)`); they cannot read each other's chats.
- A supporting relationship is the only way to reach a student *outside* the assigned classes and
  requires the other party to accept.

## 6. How Admin views relationships

- **Structure tree:** `/admin/academics` shows Branch -> Department -> Year -> Section with
  activate / deactivate / delete controls and "add" forms at each level.
- **Class directory:** `/admin/classes` lists every combination with student and active-faculty
  counts, for example

  ```
  CSE -> AIML -> 3rd Year -> A      students: 58    faculty: FAC001, FAC002
  CSE -> AIML -> 3rd Year -> B      students: 61    faculty: FAC001
  CSE -> IoT  -> 2nd Year -> C      students: 0     faculty: (none)
  ```

- **Class detail:** `/admin/classes/<section_id>` lists the section's faculty and students.
- **Faculty view:** `/admin/assignments` shows each faculty member's classes and any pending
  requests, with assign / remove controls.
- **Unmapped students:** students created before the hierarchy existed, whose old free-text class
  did not match any Admin structure, have `section_id IS NULL`; the admin dashboard counts them
  so Admin can fix them (remove registration, have the student re-register).

## 7. Migration of pre-hierarchy databases

`models/database.init_db()` is additive and idempotent (safe on every start):

1. `schema.sql` creates the new tables with `CREATE TABLE IF NOT EXISTS`.
2. `_migrate()` adds `students.section_id` (+ index) and `users.last_login_at` if missing.
3. `seed_default_structure()` seeds CSE only when no branch exists.
4. `backfill_legacy_data()` links old `students` rows to a section when their free-text
   branch / department / year / section match an Admin structure, and converts legacy
   `faculty_classes` rows into `faculty_assignments`. Rows that do not match are left untouched.

The legacy `faculty_classes` table is kept for history but is **superseded**: no access decision
reads it any more.
