# Notifications API (`/api/notifications*`)

Signed-in user (any role); the user only ever sees / changes their own notifications. POSTs need `X-CSRFToken`.

## `GET /api/notifications`
Newest first, at most 50.
```json
{ "items": [
    { "id": 12, "type": "MEETING_REQUESTED", "title": "New meeting request",
      "message": "A student has requested a meeting: Project guidance",
      "related_entity_type": "meeting", "related_entity_id": 7, "is_read": false,
      "created_at": "2026-10-01 08:15:00" } ],
  "unread_count": 3 }
```
`type` values: MEETING_REQUESTED/ACCEPTED/REJECTED/CANCELLED/COMPLETED/REMINDER, SUPPORTING_REQUESTED/RESPONDED,
PERMISSION_REQUESTED/RESPONDED, NEW_MESSAGE, ASSIGNMENT_REQUESTED/RESPONDED/CHANGED. `related_entity_*` may be `null`.
`unread_count` counts all unread notifications (not just the 50 listed).

## `POST /api/notifications/{id}/read`
200 `{"ok": true, "message": "Notification marked as read.", "unread_count": 2}`. Idempotent.
404 `not_found` if it does not exist or belongs to someone else.

## `POST /api/notifications/read-all`
200 `{"ok": true, "message": "All notifications marked as read.", "unread_count": 0}`.

401 `unauthenticated` without a session. The navigation badge counts also come with `GET /api/auth/session`
(`unread_notifications`, `unread_messages`).
