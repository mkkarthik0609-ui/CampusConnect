# Admin console API (`/api/admin/*`)

Every endpoint is **ADMIN only**: anonymous -> `401 unauthenticated`, STUDENT/FACULTY -> `403 forbidden`.
The role is read from the database on every request (a demoted or deactivated account loses access at once).
All unsafe methods need the `X-CSRFToken` header (see CONVENTIONS.md). Errors always use
`{"error": {"code", "message", "fields"?}}`. Dates are the stored UTC strings `YYYY-MM-DD HH:MM:SS`.

Academic structure, assignments, assignment requests and the class directory are in
[academics.md](academics.md) (same `/api/admin` prefix).

## Shared objects

`class` (class object, see CONVENTIONS.md) is `null` for a student that is not mapped to a section yet.

```json
{ "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
  "label": "CSE → AIML → 3rd Year → A" }
```

`student` item (students list, class detail, remove-registration response):

```json
{ "id": 1, "user_id": 4, "full_name": "Asha Kumar", "usn": "1AB21CS001", "email": "1ab21cs001@college.edu",
  "personal_email": "...", "phone": "9999999999", "profile_picture_url": null,
  "class": { "...class object..." } ,
  "legacy_class": null,
  "is_active": true, "is_removed": false, "is_unmapped": false, "can_remove_registration": true,
  "registered_at": "2026-10-01 03:14:12", "last_login_at": null }
```

* `is_removed: true` (and `is_active: false`) = the admin removed this registration. `usn` / `email` still show the
  *original* values (the stored ones carry a tombstone so the person can register again).
* `is_unmapped: true` = a pre-hierarchy student whose old free text did not match any class: `class` is `null` and
  `legacy_class` is `{"branch","department","year","section"}` (the old text). Otherwise `legacy_class` is `null`.

## Dashboard

### `GET /api/admin/dashboard`
```json
{ "stats": { "student_count": 1, "removed_student_count": 0, "unmapped_student_count": 0, "faculty_count": 2,
             "admin_count": 1, "meeting_count": 1, "pending_permission_count": 1, "pending_assignment_count": 1,
             "class_count": 72 } }
```
`student_count` counts live registrations only; `class_count` = classes whose whole chain is active;
`pending_permission_count` = profile-change requests waiting (all types);
`pending_assignment_count` = faculty class requests waiting.

## Students

### `GET /api/admin/students[?section_id=7]`
`{"items": [student, ...], "total": n}`. Live registrations first (by name), removed ones last.
`section_id` filters one class (400 `validation_error` if not an integer).

### `POST /api/admin/students/{student_id}/remove-registration`
No body. Deactivates the account, tombstones the USN and e-mail (the same person can register again with the same
USN / e-mail), cancels open meetings, drops pending supporting requests. Chats, messages, meetings and
notifications are kept. **Idempotent**: only the first call changes anything.

200
```json
{ "ok": true, "message": "Registration for Asha Kumar (1AB21CS001) removed. They can now register again with the correct class.",
  "student": { "...student item, is_removed: true..." } }
```
Errors: `404 not_found` (no such student), `409 already_removed`
(`"This registration was already removed."`; nothing is modified), `400 validation_error` (non-integer id).

## Faculty

### `GET /api/admin/faculty`
`{"items": [...], "total": n}` ordered by name:
```json
{ "id": 1, "user_id": 2, "faculty_code": "FAC001", "full_name": "Dr Rao", "email": "fac001@college.edu",
  "professional_email": "fac001@college.edu", "department": "AIML", "profile_picture_url": null,
  "is_active": true, "subjects": ["DSA"],
  "assignments": [ { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
                     "label": "CSE → AIML → 3rd Year → A", "assignment_id": 1, "is_active": true,
                     "class_active": true, "student_count": 1, "assigned_at": "2026-10-01 03:14:12",
                     "can_remove": true } ],
  "pending_request_count": 0, "registered_at": "...", "last_login_at": null }
```
`assignments` = the faculty member's active assignments; `class_active: false` marks an assignment whose class
(or one of its parents) is deactivated (it grants no access while suspended). `student_count` = live students.

## Meetings

### `GET /api/admin/meetings[?status=PENDING|ACCEPTED|REJECTED|COMPLETED|CANCELLED]`
Case-insensitive status; unknown -> `400 validation_error` (`fields.status`). Newest request first.
`{"items": [...], "total": n}`:
```json
{ "id": 1, "status": "PENDING", "reason": "Doubt in DSA", "student_message": "Free tomorrow?",
  "faculty_response": null, "meeting_time_text": null,
  "requested_at": "...", "responded_at": null, "completed_at": null, "completed_by": null,
  "cancelled_at": null, "cancelled_by": null, "cancellation_reason": null,
  "student": { "id": 1, "full_name": "Asha Kumar", "usn": "1AB21CS001", "profile_picture_url": null,
               "class": { "...class object or null..." } },
  "faculty": { "id": 1, "faculty_code": "FAC001", "full_name": "Dr Rao", "department": "AIML",
               "profile_picture_url": null } }
```

## Chats (read-only)

### `GET /api/admin/chats`
`{"items": [...], "total": n}`, most recently updated first:
```json
{ "id": 1,
  "student": { "id": 1, "user_id": 4, "full_name": "Asha Kumar", "usn": "1AB21CS001",
               "profile_picture_url": null, "class": { "...class object or null..." } },
  "faculty": { "id": 1, "user_id": 2, "faculty_code": "FAC001", "full_name": "Dr Rao", "department": "AIML",
               "profile_picture_url": null },
  "message_count": 1, "last_message": "hello sir", "last_message_at": "...", "created_at": "...",
  "updated_at": "..." }
```

### `GET /api/admin/chats/{chat_id}`
```json
{ "chat": { "id": 1, "student": {...}, "faculty": {...}, "message_count": 1, "created_at": "...", "updated_at": "..." },
  "messages": [ { "id": 1, "sender_user_id": 4, "sender_role": "STUDENT", "sender_name": "Asha Kumar",
                  "message_text": "hello sir", "attachment_url": null, "attachment_type": null,
                  "attachment_name": null, "is_seen": false, "seen_at": null, "is_edited": false,
                  "created_at": "..." } ] }
```
Oldest first. `attachment_url` (e.g. `/uploads/chat/<file>`) is readable by the admin through the uploads route.
Reading does **not** mark anything as seen. Errors: `404 not_found`, `400 validation_error` (non-integer id).

## Permission (profile change) requests

### `GET /api/admin/permission-requests`
Pending first, then newest. `{"items": [...], "total": n, "pending": n}`:
```json
{ "id": 1, "request_type": "FACULTY_PROFILE_CHANGE", "status": "PENDING",
  "requester": { "user_id": 2, "full_name": "Dr Rao", "role": "FACULTY", "usn": null, "faculty_code": "FAC001",
                 "profile_picture_url": null },
  "approver": { "user_id": 1, "full_name": "Admin One" },
  "requested_changes": { "department": "IoT" }, "reason": "moved dept",
  "created_at": "...", "reviewed_at": null, "can_decide": true }
```
`request_type`: `FACULTY_PROFILE_CHANGE` | `STUDENT_PROFILE_CHANGE`. **`can_decide` is true only for a pending
`FACULTY_PROFILE_CHANGE`**: student requests are routed to the faculty of the student's class and an admin
cannot decide them (the endpoint answers `403`). For students `requester.usn` is set, for faculty
`requester.faculty_code`.

### `POST /api/admin/permission-requests/{request_id}/decide`
Body `{"decision": "approve" | "reject"}` (anything else -> `400 validation_error`, `fields.decision`).
200 `{"ok": true, "message": "Request approved.", "status": "APPROVED"}` (`REJECTED` for reject). The requester is
notified and, on approve, the (allow-listed) changes are applied.
Errors: `404 not_found`, `409 conflict` (`"This request has already been reviewed."`), `403 forbidden`
(student request / not allowed).

## Admin accounts

### `GET /api/admin/admins`
`{"items": [...], "total": n}`, oldest first:
```json
{ "id": 1, "full_name": "Admin One", "email": "admin@college.edu", "profile_picture_url": null,
  "is_active": true, "is_you": true, "created_at": "...", "last_login_at": "..." }
```

### `POST /api/admin/admins`  (201)
Body (all required, unknown keys rejected):
```json
{ "full_name": "Second Admin", "email": "second@college.edu", "password": "Sup3rSecret!", "confirm_password": "Sup3rSecret!" }
```
The e-mail is lower-cased. Password policy: 8-128 chars with an upper-case letter, a lower-case letter and a digit,
and not equal to the e-mail (or its local part).
201 `{"ok": true, "message": "Admin account created.", "admin": { ...admin item... }}`.
Errors (400 `validation_error` with `fields`): `full_name`, `email` (invalid), `password` (policy),
`confirm_password` ("Passwords do not match."); `409 conflict` with `fields.email` when the e-mail is already used
by any account (case-insensitive).

## Error codes used by `/api/admin`

| status | code | when |
|---|---|---|
| 400 | `validation_error` | bad/missing/unknown body field or query/path value (`fields` names them); business-rule failures |
| 400 | `bad_request` | body is not valid JSON / not an object |
| 400 | `csrf_failed` | missing or wrong `X-CSRFToken` |
| 401 | `unauthenticated` | not signed in (or session expired) |
| 403 | `forbidden` | signed in but not an ADMIN (or action not allowed for admins) |
| 404 | `not_found` | unknown student / chat / request / assignment |
| 409 | `already_removed`, `conflict` | registration already removed; duplicate e-mail; request already decided |
