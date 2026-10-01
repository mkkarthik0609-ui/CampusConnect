# Student API (`/api/student/*`)

Role: **STUDENT** only. Anonymous -> `401 unauthenticated`; FACULTY / ADMIN -> `403 forbidden`.
All mutations need the `X-CSRFToken` header (see CONVENTIONS.md). Router: `api/routers/student.py`.

A student's class (branch / department / year / section) is chosen at signup from the admin-defined
tree and can only be changed by an administrator. There is **no** student endpoint for it and
`change-request` refuses those fields. Theme and password live in `/api/account/*`; notifications in
`/api/notifications*`; chat, meetings and supporting-faculty requests in their own areas.

Shapes used below

```jsonc
// faculty card (api.schemas.faculty_brief)
{ "id": 1, "faculty_code": "FAC001", "department": "AIML", "full_name": "Prof FAC001",
  "profile_picture_url": "/uploads/profile/faculty/x.png" | null }

// student object
{ "id": 1, "user_id": 3, "usn": "1AB21CS001", "full_name": "Student 1AB21CS001",
  "email": "1ab21cs001@college.edu", "college_email": "1ab21cs001@college.edu",
  "personal_email": "1ab21cs001@example.com", "phone": "9999999999",
  "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
  "class": { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
             "label": "CSE → AIML → 3rd Year → A" },          // null if the student has no section
  "theme": "light", "profile_picture_url": null }
```

## GET `/api/student/dashboard`

Everything the dashboard needs in one call. A student with no assigned faculty gets empty lists (200).

```json
{
  "student": { "...student object..." },
  "assigned_faculty": [ { "id": 1, "faculty_code": "FAC001", "department": "AIML",
                          "full_name": "Prof FAC001", "profile_picture_url": null } ],
  "supporting_faculty": [ { "...faculty card..." } ],
  "pending_supporting_requests": [
    { "id": 1, "status": "PENDING", "requested_by": "FACULTY", "direction": "incoming", "can_respond": true,
      "created_at": "2026-10-01 03:12:59", "updated_at": "2026-10-01 03:12:59",
      "student": { "id": 1, "usn": "1AB21CS001", "full_name": "...", "profile_picture_url": null,
                   "class": { "...class object..." } },
      "faculty": { "id": 1, "faculty_code": "FAC001", "department": "AIML", "full_name": "Prof FAC001",
                   "profile_picture_url": null },
      "counterpart": { "...faculty card...", "role": "FACULTY" } } ],
  "recent_meetings": [
    { "id": 1, "status": "PENDING", "reason": "Project review", "student_message": "Ch 3",
      "faculty_response": null, "meeting_time_text": null, "requested_at": "2026-10-01 03:12:59",
      "responded_at": null, "completed_at": null, "completed_by": null, "cancelled_at": null,
      "cancelled_by": null, "cancellation_reason": null,
      "student": { "...student card..." }, "faculty": { "...faculty card..." },
      "counterpart": { "...faculty card...", "role": "FACULTY" },
      "counterpart_name": "Prof FAC001", "counterpart_code": "FAC001",
      "can_respond": false, "can_cancel": true, "can_complete": false } ],
  "counts": { "assigned_faculty": 1, "supporting_faculty": 0, "pending_supporting_requests": 1,
              "meetings_total": 1, "meetings_pending": 1, "meetings_accepted": 0 }
}
```

* `assigned_faculty`: faculty with an **active** admin assignment to the student's section (class
  hierarchy active). Unassigning removes them immediately.
* `supporting_faculty`: accepted supporting relationships (faculty cards).
* `pending_supporting_requests`: requests *sent by faculty* awaiting this student's answer. Items use the
  exact shape of `docs/api/supporting.md` (`relationship_item`); answer with
  `POST /api/supporting/{id}/accept|reject`.
* `recent_meetings`: the 5 newest, in the exact shape of `GET /api/meetings` items (`meeting_item`,
  see `docs/api/meetings.md`); `status` is `PENDING|ACCEPTED|REJECTED|COMPLETED|CANCELLED`.
  `counts.meetings_*` cover all meetings.

Errors: 401, 403, 404 `not_found` (account has no student profile - should not happen).

## GET `/api/student/profile`

```json
{
  "student": { "...student object..." },
  "assigned_faculty": [ { "...faculty card..." } ],
  "permission_requests": [
    { "id": 1, "request_type": "STUDENT_PROFILE_CHANGE",
      "requested_changes": { "phone": "9876500000" }, "reason": "new number",
      "status": "PENDING", "created_at": "2026-10-01 03:01:47", "reviewed_at": null } ]
}
```
`permission_requests` is the student's own change-request history, newest first (`status`:
`PENDING|APPROVED|REJECTED`; `reviewed_at` set once decided).

## POST `/api/student/profile/picture`

`multipart/form-data`, part `profile_picture` (PNG/JPG/JPEG, <= 3 MB, magic bytes verified). The
`X-CSRFToken` header is required for multipart as well.

200:
```json
{ "ok": true, "message": "Profile picture updated.",
  "profile_picture_url": "/uploads/profile/students/d9e22a37....png" }
```
Errors (400 unless noted; the old picture is kept):
`{"error":{"code":"validation_error","message":"File content does not match its extension."}}`,
"Unsupported image type. Allowed: PNG, JPG, JPEG.", "Image is empty.", 413 `payload_too_large`
("Image is too large. Maximum size is 3 MB."), missing part ->
`{"error":{"code":"validation_error","message":"This field is required.","fields":{"profile_picture":"This field is required."}}}`.

## POST `/api/student/profile/change-request`

Asks the faculty assigned to the student's class to approve a change of contact details. Only `phone`
and `personal_email` can change, and only after a faculty assigned to the class approves (see
`docs/api/faculty.md`). The student record is not touched until then; all assigned faculty are notified.

Request (JSON):
```json
{ "phone": "9876500000", "personal_email": "new@example.com", "reason": "Changed SIM" }
```
* `reason` required (non-blank). `phone` and `personal_email` optional but at least one is needed.
  `phone`: 7-15 digits. `personal_email` is lower-cased.
* Any other key -> 400 (unknown key). `branch`, `department`, `year`, `section`, `section_id`, `usn`,
  `college_email` are recognised and refused with an explicit message.

201:
```json
{ "ok": true, "message": "Profile change request submitted for faculty approval.", "id": 1 }
```
Errors (all 400 `validation_error`):
```json
{"error":{"code":"validation_error","message":"Branch, department, year, section, USN and college email can only be changed by an administrator.","fields":{"branch":"Branch, department, ..."}}}
{"error":{"code":"validation_error","message":"Phone number must be 7-15 digits.","fields":{"phone":"Phone number must be 7-15 digits."}}}
{"error":{"code":"validation_error","message":"This field is required.","fields":{"reason":"This field is required."}}}
{"error":{"code":"validation_error","message":"No valid profile fields were submitted for change."}}
{"error":{"code":"validation_error","message":"No faculty is assigned to your class yet, so the request cannot be routed."}}
{"error":{"code":"validation_error","message":"Extra inputs are not permitted","fields":{"foo":"Extra inputs are not permitted"}}}
```
