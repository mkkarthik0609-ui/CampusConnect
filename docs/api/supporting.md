# `/api/supporting/*` — supporting-faculty relationships and searches

Roles: **STUDENT** and **FACULTY** (anonymous → 401, ADMIN → 403; endpoint-specific role limits below).
Router: `api/routers/supporting.py`.

A supporting relationship lets a student and a faculty member who are **not** linked by an Admin class assignment
chat and meet: one side requests, the **other** side accepts. Status: `PENDING → ACCEPTED | REJECTED`.
`ACCEPTED` grants chat/meeting access (see chat.md); `PENDING` and `REJECTED` grant nothing. A `REJECTED` pair can
request again: the **same row** is re-opened to `PENDING` and `requested_by` becomes the new requester
(`UNIQUE(student_id, faculty_id)`), so the relationship id stays the same.

## Relationship item
```json
{
  "id": 1,
  "status": "PENDING",                        // PENDING | ACCEPTED | REJECTED
  "requested_by": "STUDENT",                  // who asked
  "direction": "incoming",                    // from the VIEWER's side: "incoming" (I must answer) | "outgoing" (I asked)
  "can_respond": true,                        // PENDING and direction == incoming
  "created_at": "2026-10-01 03:12:49", "updated_at": "2026-10-01 03:12:49",
  "student": { "id": 2, "usn": "1AB21CS002", "full_name": "Kiran Das", "profile_picture_url": null,
               "class": { "section_id": 16, "branch": "CSE", "department": "AIDE", "year": "2nd Year",
                          "section": "A", "label": "CSE → AIDE → 2nd Year → A" } },
  "faculty": { "id": 1, "faculty_code": "FAC001", "department": "AIML", "full_name": "Dr. Meera Nair",
               "profile_picture_url": null },
  "counterpart": { /* faculty card + "role": "FACULTY" for students; student card + "role": "STUDENT" for faculty */ }
}
```

## GET `/api/supporting?status=`
All my relationships (pending first, then most recently updated). Optional `status=PENDING|ACCEPTED|REJECTED`
(anything else → 400). Relationships with deactivated accounts are omitted.
`{"items": [ { /* relationship item */ } ], "total": 1}`

## GET `/api/supporting/faculty/search?q=` — student only
Any active faculty member by name or Faculty ID (substring, case-insensitive; `%` and `_` are literal).
Blank `q` → `{"items": []}`; `q` max 100 chars (400 otherwise). At most 20 results.
```json
{ "items": [ { "id": 1, "faculty_code": "FAC001", "department": "AIML", "full_name": "Dr. Meera Nair",
               "profile_picture_url": null,
               "relationship": { "id": 1, "status": "PENDING", "requested_by": "STUDENT" },   // null when none
               "has_access": false,            // can the student chat/meet this faculty member right now
               "access_via": null,             // "class" | "supporting" | null
               "can_request": false } ],       // no relationship yet, or the previous one was REJECTED
  "total": 1, "query": "meera" }
```

## GET `/api/supporting/students/search?q=` — faculty only
Students by USN or name, **scoped to the classes the faculty member is actively assigned to** — students of other
classes are never returned, whatever `q` is (SQL wildcards do not widen the scope). Blank `q` → empty list; at most 30 results.
```json
{ "items": [ { "id": 1, "usn": "1AB21CS001", "full_name": "Asha Rao", "profile_picture_url": null,
               "class": { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year",
                          "section": "A", "label": "CSE → AIML → 3rd Year → A" },
               "relationship": null,           // { id, status, requested_by } when one exists
               "can_request": true } ],
  "total": 1, "query": "asha" }
```

## POST `/api/supporting/faculty/{faculty_id}/request` — student only
No body. 201 `{"ok": true, "message": "Supporting-faculty request sent.", "id": 1, "relationship": { /* item, direction "outgoing" */ }}`.
The faculty member is notified.
Errors: 404 `not_found` (`Faculty member not found.` — unknown or deactivated); 409 `conflict`
(`A supporting relationship request already exists with this faculty member.` — PENDING or ACCEPTED exists).

## POST `/api/supporting/students/{student_id}/request` — faculty only
No body. 201 `{"ok": true, "message": "Supporting-student request sent.", "id": 2, "relationship": { /* item */ }}`.
The student is notified.
Errors: 403 `forbidden` (`You can only send requests to students in your assigned classes.` — also after the
assignment was removed); 404 `not_found` (`Student not found.`); 409 `conflict` (already pending/accepted).

## POST `/api/supporting/{rel_id}/accept` and `/reject` — the ADDRESSED party only
No body. A student answers requests made by faculty, a faculty member answers requests made by students; the
requester can never answer their own request.
200 `{"ok": true, "message": "Request accepted.", "status": "ACCEPTED", "relationship": { /* item */ }}`
(`"Request rejected."` / `"REJECTED"`). The requester is notified.

Errors: 403 `forbidden` (`You are not authorized to respond to this request.` — wrong party; checked before the
state, so outsiders learn nothing about it); 404 `not_found` (`Request not found.`); 409 `conflict`
(`This request has already been responded to.`).
