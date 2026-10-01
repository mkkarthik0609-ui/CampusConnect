# `/api/meetings/*` — meeting requests

Roles: **STUDENT** and **FACULTY** (anonymous → 401, ADMIN → 403; endpoint-specific role limits below).
Router: `api/routers/meetings.py`. A student only sees/acts on their own meetings; a faculty member only on
meetings addressed to them. Requesting and responding additionally require that the student is currently
reachable (ACTIVE class assignment or ACCEPTED supporting relationship) — removing the assignment closes both
immediately (`can_respond` becomes `false`, requests/responses return 403).

Status lifecycle: `PENDING → ACCEPTED | REJECTED | CANCELLED`, `ACCEPTED → COMPLETED | CANCELLED`.

## Meeting item
```json
{
  "id": 1,
  "status": "PENDING",                       // PENDING | ACCEPTED | REJECTED | COMPLETED | CANCELLED
  "reason": "Doubt in trees",
  "student_message": "Please explain AVL rotations",   // the student's details ("" when none)
  "faculty_response": null,
  "meeting_time_text": null,                 // free text set by the faculty member when accepting
  "requested_at": "2026-10-01 03:12:49",
  "responded_at": null, "completed_at": null, "completed_by": null,        // "STUDENT" | "FACULTY" | null
  "cancelled_at": null, "cancelled_by": null, "cancellation_reason": null,
  "student": { "id": 1, "usn": "1AB21CS001", "full_name": "Asha Rao", "profile_picture_url": null,
               "class": { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year",
                          "section": "A", "label": "CSE → AIML → 3rd Year → A" } },
  "faculty": { "id": 1, "faculty_code": "FAC001", "department": "AIML", "full_name": "Dr. Meera Nair",
               "profile_picture_url": null },
  "counterpart": { /* the OTHER party from the viewer's side: the faculty card (role "FACULTY") for students,
                      the student card (role "STUDENT") for faculty */ },
  "counterpart_name": "Dr. Meera Nair",
  "counterpart_code": "FAC001",              // faculty code for students, USN for faculty
  "can_respond": false,                      // faculty only: PENDING and the student is still reachable
  "can_cancel": true,                        // PENDING or ACCEPTED
  "can_complete": false                      // ACCEPTED
}
```

## GET `/api/meetings?status=`
My meetings, newest first. `status` is optional: one status or a comma-separated list, case-insensitive
(`?status=pending`, `?status=accepted,completed`).
`{"items": [ { /* meeting item */ } ], "total": 1}`. Error: 400 `validation_error` with `fields.status` for an unknown status.

## POST `/api/meetings` — student only (FACULTY → 403)
```json
{ "faculty_id": 1, "reason": "Doubt in trees", "details": "Please explain AVL rotations" }
```
`reason` required (1–200 chars after trimming), `details` optional (<= 2000). Unknown fields are rejected.

201 `{"ok": true, "message": "Meeting request sent.", "id": 1, "meeting": { /* item */ }}` — the faculty member is notified.

Errors: 400 `validation_error` (blank/missing reason, bad ids, extra fields); 403 `forbidden`
`You do not have permission to request a meeting with this faculty member.` (no class assignment / supporting
relationship — also for unknown faculty ids).

## GET `/api/meetings/{meeting_id}`
`{"meeting": { /* item */ }}`. 403 `forbidden` (`You do not have access to this meeting.`) for anyone but the two
parties, 404 `not_found` for unknown ids.

## POST `/api/meetings/{meeting_id}/respond` — faculty only (STUDENT → 403)
```json
{ "decision": "accept", "faculty_response": "Come to my cabin", "meeting_time_text": "Tomorrow 3 PM" }
```
`decision` is `accept` or `reject`. `meeting_time_text` is **required when accepting** (<= 200); `faculty_response`
is optional (<= 1000). The student is notified.

200 `{"ok": true, "message": "Meeting request accepted.", "status": "ACCEPTED", "meeting": { /* item */ }}`
(`"Meeting request rejected."` / `"REJECTED"`).

Errors: 400 `validation_error` (`fields.meeting_time_text` when accepting without a time; bad `decision`);
403 `forbidden` (meeting addressed to another faculty member; `This student is no longer in one of your assigned classes.`);
404 `not_found`; 409 `conflict` (`This meeting request has already been responded to.`).

## POST `/api/meetings/{meeting_id}/cancel` — student or faculty party
```json
{ "reason": "Clash with a lab session" }
```
Body is optional for faculty; a **student must give a non-empty `reason`** (`fields.reason`). Allowed while
PENDING or ACCEPTED.

200 `{"ok": true, "message": "Meeting cancelled.", "status": "CANCELLED", "meeting": { /* item with cancelled_by, cancellation_reason */ }}`

Errors: 400 (`Please provide a reason for cancelling this meeting.`, `This meeting cannot be cancelled from its current status.`);
403 (not a party); 404.

## POST `/api/meetings/{meeting_id}/complete` — student or faculty party
No body. Only ACCEPTED meetings. 200 `{"ok": true, "message": "Meeting marked completed.", "status": "COMPLETED", "meeting": { /* item, completed_by */ }}`.
Errors: 400 `Only an accepted meeting can be marked completed.`; 403 (not a party); 404.

The other party is notified for every transition; open meetings get periodic reminder notifications from the scheduler.
