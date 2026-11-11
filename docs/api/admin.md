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

## Chats

Admins have **no access** to student <-> faculty conversations: there is no `/api/admin/chats*` route (404) and the
`/api/chat/*` routes answer `403` to an admin. Admins talk to faculty only through Admin Connect (`/api/admin-messages`,
see [chat.md](chat.md)).

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
  "is_active": true, "is_you": true, "is_primary": true, "created_at": "...", "last_login_at": "..." }
```
Every admin may read this list. **Only the primary admin** (`PRIMARY_ADMIN_EMAIL`) may add admins, manage
registrations or deactivate/reactivate admins; any other admin gets 403 `forbidden`. The primary admin is itself
protected: it cannot be deactivated or deleted (400 `validation_error`), and public signup cannot claim its e-mail
or any e-mail with a pending registration. Admins have **no password**: they sign in with their e-mail and the shared
admin ID (see [auth.md](auth.md)); the account is created on first sign-in.

### Admin registrations (primary admin only; path `admin-invitations`)

| Endpoint | Effect |
|---|---|
| `GET /api/admin/admin-invitations` | `{items, total}`, newest first, at most 200 |
| `POST /api/admin/admin-invitations` (201) | register an admin e-mail (nothing is e-mailed) |
| `POST /api/admin/admin-invitations/{id}/resend` | renew the registration window (`INVITE_TTL_HOURS`, default 30 days). 60 s cooldown |
| `DELETE /api/admin/admin-invitations/{id}` | revoke a pending registration |

`POST` body (unknown keys rejected): `{ "email": "second@college.edu", "full_name": "Second Admin" }`
(`email` required, `full_name` optional, max 120). Errors: 400 `validation_error` (`fields.email`),
`409 conflict` (`fields.email`) when an account with that e-mail exists or a non-expired invitation for it is pending.

Registration item:
```json
{ "id": 3, "email": "second@college.edu", "full_name": "Second Admin", "status": "PENDING",
  "created_at": "...", "expires_at": "...", "last_sent_at": "...", "accepted_at": null }
```
`status` is `PENDING`, `ACCEPTED` (the person has signed in once), `REVOKED` or `EXPIRED` (a `PENDING` row past `expires_at`).

`POST` (create) and `POST .../resend` answer `{"ok": true, "message": "...", "invitation": {...}}`. Nothing is e-mailed:
the primary admin tells the person to sign in at Admin Login with their e-mail and the admin ID. Resend/revoke of a
non-pending row, or an unknown id, answers 400 `validation_error`; the resend cooldown answers 400 as well.

### Managing admins
| Endpoint | Effect |
|---|---|
| `POST /api/admin/admins/{id}/active` `{"active": bool}` | deactivate / reactivate -> `{ok, message, admin}`. You cannot deactivate yourself or the primary admin. Deactivation bumps the account's `session_version`, which ends all its sessions, and sign-in is refused. |

Invitations and (de)activations are written to the audit trail (table `audit_log`: actor, action such as
`admin_invite.create` / `admin.deactivate`, target, IP, time).

Removed: `POST /api/admin/admins` (temporary passwords), `POST /api/admin/admins/{id}/reset-password` and every
passkey endpoint (`/api/admin/passkeys*`, `/api/auth/admin-passkey/*`, `DELETE /api/admin/admins/{id}/passkeys`).

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
