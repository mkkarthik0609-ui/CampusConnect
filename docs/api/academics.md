# Academic structure, assignments and class directory (`/api/admin/*`)

**ADMIN only** (anonymous -> `401 unauthenticated`, STUDENT/FACULTY -> `403 forbidden`; CSRF header on every
unsafe method). The rest of the admin console is in [admin.md](admin.md). Error shape:
`{"error": {"code", "message", "fields"?}}`.

The hierarchy is Branch -> Department -> Year -> Section; a **class** is one section with its chain.
Default seed (first start only): branch `CSE`; departments `AIML, AIDE, GenAI, Cybersecurity, Blockchain, IoT`;
years `1st Year` ... `4th Year`; sections `A, B, C` (72 classes). Students and faculty only ever *select* active
rows (the public, active-only tree is `GET /api/academic/tree`, see CONVENTIONS.md).

Rules enforced by the server:
* Branch / department names: 1-40 chars (letters, digits, space, `&`, `.`, `-`), unique case-insensitively
  (department: per branch). Whitespace is collapsed.
* Year: `"3"`, `"3rd"`, `"3rd year"` all become `"3rd Year"` (1-9); unique per department.
* Section labels are **a single letter** (`A`..`Z`, stored upper-case); `"3A"`, `"AB"`, `"1"` are rejected.
* Deactivating any level hides it and everything below it from the public tree and blocks new registrations /
  assignments / requests for it. Nothing is lost; reactivating restores it. A faculty assignment under a
  deactivated class stays listed (`class_active: false`) but grants no access until reactivated.
* A level can only be **deleted** when no student row and no faculty-assignment row (active or not) exists below it.

Class object (everywhere): `{"section_id", "branch", "department", "year", "section", "label"}`
with `label` = `"CSE → AIML → 3rd Year → A"`.

---

## Academic structure

### `GET /api/admin/academics`
The whole tree including inactive rows. Every node has `is_active`, usage counts rolled up from the sections below
it, and `can_delete` (= no students and no assignments below).
```json
{ "branches": [ { "id": 1, "name": "CSE", "is_active": true, "student_count": 1, "assignment_count": 1,
    "can_delete": false,
    "departments": [ { "id": 2, "name": "AIDE", "is_active": true, "student_count": 0, "assignment_count": 0,
      "can_delete": true,
      "years": [ { "id": 5, "name": "1st Year", "is_active": true, "student_count": 0, "assignment_count": 0,
        "can_delete": true,
        "sections": [ { "id": 13, "name": "A", "is_active": true, "student_count": 0, "assignment_count": 0,
                        "can_delete": true } ] } ] } ] } ] }
```
`student_count` = student rows (removed registrations included, they still reference the section);
`assignment_count` = faculty-assignment rows (active or not). Order: names for branches/departments, 1st..Nth for
years, A..Z for sections.

### `POST /api/admin/academics/branches`  (201)
Body `{"name": "ECE"}` -> `{"ok": true, "message": "Branch added.", "id": 2, "name": "ECE"}`.

### `POST /api/admin/academics/departments`  (201)
Body `{"branch_id": 2, "name": "VLSI"}` -> `{"ok": true, "message": "Department added.", "id": 7, "name": "VLSI"}`.

### `POST /api/admin/academics/years`  (201)
Body `{"department_id": 7, "name": "2"}` -> `{"ok": true, "message": "Academic year added.", "id": 25, "name": "2nd Year"}`.

### `POST /api/admin/academics/sections`  (201)
Body `{"year_id": 25, "names": "A, B"}` (`"A"`, `"A,B,C"`, `"A B C"`; all labels validated before anything is
created; labels that already exist are skipped as long as at least one is new)
-> `{"ok": true, "message": "Section(s) added: A, B.", "created": ["A", "B"]}`.

Request bodies are strict: ids must be positive JSON integers (not strings/booleans), names must be strings,
unknown keys are rejected.

Errors for the four POSTs above:

| status | code | example |
|---|---|---|
| 400 | `validation_error` | `fields.name` / `fields.names`: `"Branch name must be 1-40 characters (...)."`, `"Year must look like '1st Year' ... (1 to 9)."`, `"Section must be a single letter label such as A, B or C."`, wrong JSON type, unknown key |
| 404 | `not_found` | `"Branch not found."`, `"Department not found."`, `"Year not found."` (unknown parent id) |
| 409 | `conflict` | duplicate: `"Branch 'ece' already exists."`, `"3rd Year already exists in this department."`, `"Those sections already exist for this year."` (`fields.name` / `fields.names` is set too) |

### `POST /api/admin/academics/{level}/{id}/active`
`level` is `branch | department | year | section`. Body `{"active": true | false}` (a real boolean).
200 `{"ok": true, "message": "Section deactivated. It is hidden from new registrations.", "level": "section", "id": 73, "is_active": false}`
(`"... reactivated."` when activating). Errors: `404 not_found` (`"Item not found."`: unknown level or id),
`400 validation_error` (`fields.active`).

### `DELETE /api/admin/academics/{level}/{id}`
Deletes an **unused** item (children are deleted with it). 200
`{"ok": true, "message": "Section deleted.", "level": "section", "id": 73}`.
Errors: `404 not_found`; `409 in_use` -
`"This item has students or faculty assignments; deactivate it instead of deleting."` (nothing changes; use
`can_delete` from the tree to disable the button).

---

## Faculty assignments

An assignment = a faculty member active in one class. A faculty member may have many; a class may have many
faculty. Assigning again after a removal re-activates the same row.

### `GET /api/admin/assignments`
`{"items": [...], "total": n, "pending_count": n}`; one item per faculty member (by name):
```json
{ "faculty_id": 1, "faculty_code": "FAC001", "full_name": "Dr Rao", "department": "AIML",
  "profile_picture_url": null,
  "assignments": [ { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
                     "label": "CSE → AIML → 3rd Year → A", "assignment_id": 1, "is_active": true,
                     "class_active": true, "student_count": 1, "assigned_at": "2026-10-01 03:14:12",
                     "can_remove": true } ],
  "pending_requests": [ { "...assignment request item (below)..." } ] }
```
Class choices for the assign form come from `GET /api/academic/tree` (active classes only).

### `POST /api/admin/assignments`  (201)
Body `{"faculty_id": 2, "section_id": 8}`. Notifies the faculty member and marks any pending request of theirs for
the same class as approved.
```json
{ "ok": true, "message": "Assigned to CSE → AIML → 3rd Year → B.",
  "assignment": { "section_id": 8, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "B",
                  "label": "CSE → AIML → 3rd Year → B", "assignment_id": 2, "is_active": true,
                  "class_active": true, "student_count": 0, "assigned_at": "...", "can_remove": true } }
```
Errors: `400 validation_error` (missing / non-integer ids, unknown keys), `404 not_found` (unknown faculty;
class unknown **or inactive**: `"The selected class does not exist. Please choose from the list."`),
`409 conflict` (`"FAC001 is already assigned to CSE → AIML → 3rd Year → A."`).

### `DELETE /api/admin/assignments/{assignment_id}`
Deactivates the assignment immediately (chat / meeting / class access of that faculty to that class is revoked
server-side, history is kept) and notifies the faculty member.
200 `{"ok": true, "message": "Assignment removed: CSE → AIML → 3rd Year → A.", "assignment_id": 1}`.
Errors: `404 not_found`, `409 already_inactive` (`"This assignment was already removed."`), `400` (non-integer id).

---

## Faculty requests to join a class

A faculty member asks (via the faculty API) to be assigned to a class; **nothing is granted until an admin
approves**.

### `GET /api/admin/assignment-requests[?status=PENDING|APPROVED|REJECTED]`
Status is case-insensitive; unknown -> `400 validation_error` (`fields.status`). Pending first, then newest.
`{"items": [...], "total": n, "pending_count": n}`:
```json
{ "id": 1, "status": "PENDING", "note": "I teach DSA", "created_at": "...", "reviewed_at": null,
  "reviewed_by": null,
  "faculty": { "id": 2, "faculty_code": "FAC002", "full_name": "Dr Iyer", "department": "IoT",
               "profile_picture_url": null },
  "class": { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
             "label": "CSE → AIML → 3rd Year → A" },
  "class_active": true, "can_decide": true }
```
`can_decide` = status is `PENDING`. `class_active: false` means approving will fail until the class is reactivated
(rejecting still works). `reviewed_by` is the deciding admin's user id.

### `POST /api/admin/assignment-requests/{request_id}/decide`
Body `{"decision": "approve" | "reject"}` (anything else -> `400 validation_error`, `fields.decision`).
200 `{"ok": true, "message": "Request approved.", "status": "APPROVED"}` (`REJECTED` for reject). Approving creates
(or re-activates) the assignment; the faculty member is notified either way.
Errors: `404 not_found`; `409 conflict` (`"This request has already been reviewed."`);
`400 validation_error` (`"That class is no longer active; reactivate it before approving."`).

---

## Class directory

### `GET /api/admin/classes`
Every class (active or not), ordered by branch, department, year, section.
`{"items": [...], "total": 72}`:
```json
{ "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
  "label": "CSE → AIML → 3rd Year → A", "is_active": true, "student_count": 1, "faculty_count": 1,
  "faculty": [ { "id": 2, "assignment_id": 3, "faculty_code": "FAC002", "full_name": "Dr Iyer",
                 "profile_picture_url": null } ] }
```
`is_active` = the whole chain is active. `student_count` = live registrations (removed ones excluded);
`faculty_count` / `faculty` = active assignments.

### `GET /api/admin/classes/{section_id}`
```json
{ "class": { "section_id": 7, "...": "...", "is_active": true, "student_count": 1, "faculty_count": 1 },
  "faculty": [ { "id": 2, "assignment_id": 3, "faculty_code": "FAC002", "full_name": "Dr Iyer", "profile_picture_url": null } ],
  "students": [ { "id": 1, "user_id": 4, "full_name": "Asha Kumar", "usn": "1AB21CS001", "email": "...",
                  "personal_email": "...", "phone": "9999999999", "profile_picture_url": null,
                  "class": { "...class object..." }, "legacy_class": null, "is_active": true,
                  "is_removed": false, "is_unmapped": false, "can_remove_registration": true,
                  "registered_at": "...", "last_login_at": null } ] }
```
`students` includes removed registrations (`is_removed: true`, `is_active: false`) after the live ones.
Errors: `404 not_found` (`"Class not found."`), `400` (non-integer id).
Student removal itself is `POST /api/admin/students/{id}/remove-registration` in [admin.md](admin.md).
