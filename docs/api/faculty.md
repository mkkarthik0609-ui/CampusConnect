# `/api/faculty/*` — faculty dashboard, profile, classes, student-request review

Role: **FACULTY** only (anonymous → 401 `unauthenticated`, STUDENT/ADMIN → 403 `forbidden`).
Router: `api/routers/faculty.py`. All bodies are JSON unless noted; every POST needs the `X-CSRFToken` header
(see CONVENTIONS.md). Unknown body fields are rejected with 400 `validation_error` (the field name is in `fields`).

Class access is **Admin-controlled**: a class is only open to a faculty member while an *active* assignment
exists. Requesting a class grants nothing until an Admin approves it; removing the assignment closes the class
view, student search, chats, meetings and student-request review **immediately**.

## Shared shapes

```jsonc
// class object (CONVENTIONS.md) — assignments add: assignment_id, assigned_at, student_count
{ "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
  "label": "CSE → AIML → 3rd Year → A",
  "assignment_id": 1, "assigned_at": "2026-10-01 03:12:48", "student_count": 1 }

// student card (also used by chat/meetings/supporting)
{ "id": 1, "usn": "1AB21CS001", "full_name": "Asha Rao", "profile_picture_url": null,
  "class": { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
             "label": "CSE → AIML → 3rd Year → A" } }          // class is null if the section is unknown

// my class request
{ "id": 1, "section_id": 8, "status": "PENDING|APPROVED|REJECTED", "note": "I teach this section",
  "created_at": "2026-10-01 03:12:49", "reviewed_at": null, "class": { /* class object */ } }

// student profile-change request awaiting my review
{ "id": 1, "request_type": "STUDENT_PROFILE_CHANGE", "status": "PENDING",
  "requested_changes": { "phone": "9000000000" },           // phone and/or personal_email
  "reason": "New number", "created_at": "2026-10-01 03:12:49",
  "requester_name": "Asha Rao", "student": { /* student card */ } }
```

`meeting` items are documented in [meetings.md](meetings.md).

---

## GET `/api/faculty/dashboard`
Everything the dashboard needs in one call.

```json
{
  "profile": { "id": 1, "user_id": 2, "faculty_code": "FAC001", "full_name": "Dr. Meera Nair",
               "email": "fac001@college.edu", "professional_email": "fac001@college.edu",
               "department": "AIML", "theme": "light", "profile_picture_url": null },
  "subjects": ["DSA", "OS"],
  "classes": [ { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
                 "label": "CSE → AIML → 3rd Year → A", "assignment_id": 1,
                 "assigned_at": "2026-10-01 03:12:48", "student_count": 1 } ],
  "pending_class_requests": [ { "id": 1, "section_id": 8, "status": "PENDING", "note": "I teach this section",
                                "created_at": "2026-10-01 03:12:49", "reviewed_at": null, "class": { } } ],
  "supporting_students": [ { /* student card */ } ],
  "pending_supporting_requests": [ { "id": 1, "created_at": "2026-10-01 03:12:49", "student": { /* student card */ } } ],
  "recent_meetings": [ { /* meeting item, newest first, at most 5 */ } ],
  "pending_permission_requests": [ { /* student profile-change request */ } ],
  "counts": { "classes": 1, "pending_class_requests": 1, "supporting_students": 0,
              "pending_supporting_requests": 1, "pending_permission_requests": 1, "meetings_pending": 1 }
}
```
* `classes` — ACTIVE assignments only (inactive classes / deactivated hierarchy rows are omitted).
* `pending_supporting_requests[].id` is the relationship id to pass to `POST /api/supporting/{id}/accept|reject`.
* `pending_permission_requests` — pending *student* profile changes from my active classes only.
* 404 `not_found` if the signed-in FACULTY user has no faculty record.

## GET `/api/faculty/profile`
```json
{
  "profile": { /* same as dashboard.profile */ },
  "subjects": ["DSA", "OS"],
  "classes": [ { /* class object + assignment fields */ } ],
  "change_requests": [ { "id": 2, "request_type": "FACULTY_PROFILE_CHANGE", "status": "PENDING",
                         "requested_changes": { "department": "AIDE" }, "reason": "Moved departments",
                         "created_at": "2026-10-01 03:12:49", "reviewed_at": null } ],
  "departments": ["AIDE", "AIML", "Blockchain", "Cybersecurity", "GenAI", "IoT"]
}
```
`departments` = names of the active Admin departments (options for the department change request).
`change_requests` are my own requests (newest first).

## POST `/api/faculty/profile/picture` — `multipart/form-data`
Field `profile_picture`: PNG / JPG / JPEG, <= 3 MB, magic bytes checked.

200 `{"ok": true, "message": "Profile picture updated.", "profile_picture_url": "/uploads/profile/faculty/<uuid>.png"}`

Errors: 400 `validation_error` — field missing (`fields.profile_picture`), `Unsupported image type. Allowed: PNG, JPG, JPEG.`,
`File content does not match its extension.`, `Image is empty.`; 413 `payload_too_large` (> 3 MB / > 10 MB request).

## POST `/api/faculty/profile/change-request`
Asks the Admin to change the department and/or professional e-mail. Nothing changes until the Admin approves.

```json
{ "department": "AIDE", "professional_email": "new@college.edu", "reason": "Moved departments" }
```
`department` and `professional_email` are optional but at least one is required; `reason` is required (<= 500 chars).
`department` must be the name of an **active** Admin department; the e-mail must be valid and unused by another faculty.

201 `{"ok": true, "message": "Profile change request submitted for admin approval.", "id": 2}`

Errors (400 `validation_error`): missing/blank `reason` (`fields.reason`), unknown extra field (e.g. `faculty_code`),
`No valid profile fields were submitted for change.`, `Please choose a department from the list.`,
invalid e-mail (`fields.professional_email`), `That professional email is already in use.`.

## GET `/api/faculty/classes`
```json
{ "assignments": [ { /* class object + assignment fields */ } ],
  "requests": [ { /* my class request, pending first, then newest */ } ] }
```
Use the public `GET /api/academic/tree` for the class picker of the request form.

## POST `/api/faculty/classes/request`
```json
{ "section_id": 8, "note": "I teach this section" }
```
`note` optional (<= 500 chars). 201 `{"ok": true, "message": "Request sent to Admin. You will get access once it is approved.", "id": 1}`

Errors: 404 `not_found` `The selected class does not exist. Please choose from the list.` (unknown / inactive section);
409 `conflict` `You are already assigned to this class.` / `You already have a pending request for this class.`;
400 `validation_error` (bad body).

## GET `/api/faculty/classes/{section_id}`
Class roster. **403 `forbidden` unless the faculty member is actively assigned to exactly this section** — also
for unknown ids (there is no 404 oracle).

```json
{
  "class": { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
             "label": "CSE → AIML → 3rd Year → A", "student_count": 1, "assignment_id": 1 },
  "students": [ { "id": 1, "usn": "1AB21CS001", "full_name": "Asha Rao", "phone": "9999999999",
                  "college_email": "1ab21cs001@college.edu", "profile_picture_url": null } ],
  "co_faculty": [ { "id": 1, "faculty_code": "FAC001", "full_name": "Dr. Meera Nair",
                    "profile_picture_url": null, "is_me": true } ]
}
```
`students` are the active students registered in that section (`id` = student id for `POST /api/chat/open`);
`co_faculty` are all faculty actively assigned to it. Error: 403 `{"error": {"code": "forbidden", "message": "You are not assigned to this class."}}`; 400 for a non-integer id.

## GET `/api/faculty/permission-requests`
`{"items": [ { /* student profile-change request */ } ], "total": 1}` — pending STUDENT_PROFILE_CHANGE requests of
students in my **active** classes. Empty once the assignment is removed.

## POST `/api/faculty/permission-requests/{request_id}/decide`
```json
{ "decision": "approve" }          // or "reject"
```
200 `{"ok": true, "message": "Request approved.", "status": "APPROVED"}` (`"Request rejected."` / `"REJECTED"`).
Approving applies the (allow-listed) change to the student.

Errors: 400 `validation_error` (decision not `approve|reject`); 403 `forbidden` — the student is not in one of my
active classes, or the request is a faculty profile change (only an Admin may decide those); 404 `not_found`
(`Permission request not found.`); 409 `conflict` (`This request has already been reviewed.`).
