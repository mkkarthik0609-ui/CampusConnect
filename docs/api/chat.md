# `/api/chat/*` — student ↔ faculty conversations

Roles: **STUDENT** or **FACULTY** (anonymous → 401, ADMIN → 403). Router: `api/routers/chat.py`.
One chat per (student, faculty) pair. Only the two participants can read or write it.

**Access rule** (checked by the server on *every* call, never cached): a student and a faculty member may chat
while the student's registered section is an **ACTIVE assignment** of the faculty member (Admin-controlled) **or**
they have an **ACCEPTED supporting relationship**. When that stops being true (assignment removed, class
deactivated, student registration removed) the chat is closed for **both** sides immediately: `GET /{chat_id}`,
sending and editing return 403, the chat disappears from `GET /api/chat` and no longer counts towards
`unread_messages`. History is kept and comes back if access is restored.

All shapes use ids as integers and timestamps as `YYYY-MM-DD HH:MM:SS` (UTC).

## Shapes

```jsonc
// other party ("other"), role-specific
{ "role": "FACULTY", "id": 1, "code": "FAC001", "faculty_code": "FAC001", "department": "AIML",
  "full_name": "Dr. Meera Nair", "profile_picture_url": "/uploads/profile/faculty/x.png" }
{ "role": "STUDENT", "id": 1, "code": "1AB21CS001", "usn": "1AB21CS001", "full_name": "Asha Rao",
  "profile_picture_url": null,
  "class": { "section_id": 7, "branch": "CSE", "department": "AIML", "year": "3rd Year", "section": "A",
             "label": "CSE → AIML → 3rd Year → A" } }

// message
{ "id": 2, "is_mine": true, "message_text": "Notes attached",       // null for an attachment without caption
  "attachment": { "url": "/uploads/chat/<uuid>.pdf", "name": "notes.pdf", "type": "pdf", "is_image": false } /* or null */,
  "is_seen": false,        // has the OTHER side read it (for incoming messages: always true once you fetched them)
  "is_edited": false,
  "can_edit": false,       // is_mine && !is_seen && no attachment
  "created_at": "2026-10-01 03:12:49", "updated_at": "2026-10-01 03:12:49" }
```
Attachments are downloaded with `GET attachment.url` (session cookie; only the two participants and Admins can read it).

---

## GET `/api/chat`
My conversations, newest activity first (chats without messages last). Chats whose access was revoked are omitted.
```json
{
  "items": [
    { "chat_id": 1,
      "other": { "role": "STUDENT", "id": 1, "code": "1AB21CS001", "usn": "1AB21CS001", "full_name": "Asha Rao",
                 "profile_picture_url": null, "class": { "section_id": 7, "branch": "CSE", "department": "AIML",
                 "year": "3rd Year", "section": "A", "label": "CSE → AIML → 3rd Year → A" } },
      "unread_count": 1,
      "last_message": "Notes attached",          // text, "Attachment: <name>" or null
      "last_message_at": "2026-10-01 03:12:49",  // null when empty
      "last_message_is_mine": true,              // null when empty
      "updated_at": "2026-10-01 03:12:49" }
  ],
  "total": 1,
  "total_unread": 1
}
```
`unread_count` = incoming messages not yet seen by me. Listing does **not** mark anything as seen.

## POST `/api/chat/open`
Get-or-create the conversation. Does not mark messages as seen.
* Student: `{ "faculty_id": 1 }`   * Faculty: `{ "student_id": 1 }`

200 `{"ok": true, "message": "Chat opened.", "chat_id": 1}`

Errors: 400 `validation_error` — the required id is missing, or the *other role's* id was sent
(`fields.student_id` for a student, `fields.faculty_id` for a faculty member), non-integer ids;
403 `forbidden` — no ACTIVE class assignment / ACCEPTED supporting relationship:
`You do not have permission to message this faculty member.` (student) /
`You can only message students in your assigned classes or supporting students.` (faculty).
Unknown ids also give 403 (no existence oracle).

## GET `/api/chat/{chat_id}?after_id=0`
Participant only. **Marks every incoming message of this chat as seen** (so `is_seen` of the sender's messages flips
for them on their next fetch). `after_id` (optional, default 0) returns only messages with a larger id — use
`last_id` for polling.
```json
{
  "chat": { "id": 1, "other": { /* other party */ }, "created_at": "2026-10-01 03:12:49", "updated_at": "2026-10-01 03:12:49" },
  "messages": [ { /* message */ } ],            // oldest first
  "last_id": 2                                  // id of the last returned message (= after_id when none)
}
```
Errors: 403 `forbidden` (`You do not have access to this conversation.` for non-participants;
`This faculty member is no longer assigned to your class.` / `This student is no longer in one of your assigned classes.`),
404 `not_found` (`Conversation not found.`), 400 (non-integer id).

## POST `/api/chat/{chat_id}/messages`
Either **JSON** `{ "message_text": "Good morning sir" }` (1–4000 chars after trimming) **or** `multipart/form-data` with
field `attachment` (PDF / PNG / JPG / JPEG / DOCX, <= 8 MB, magic bytes checked) and an optional `message_text` caption.
Access is checked before any file is stored.

201
```json
{ "ok": true, "message": "Message sent.",
  "item": { "id": 1, "is_mine": true, "message_text": "Good morning sir", "attachment": null,
            "is_seen": false, "is_edited": false, "can_edit": true,
            "created_at": "2026-10-01 03:12:49", "updated_at": "2026-10-01 03:12:49" } }
```
The recipient gets a `NEW_MESSAGE` notification.

Errors: 400 `validation_error` — empty message and no file (`fields.message_text`: `Please enter a message or attach a file.`),
over 4000 chars, unsupported / mismatching / empty file, unknown JSON fields (e.g. `sender_user_id`), malformed JSON;
403 `forbidden` (not a participant, or access revoked); 404 `not_found` (unknown chat); 413 `payload_too_large`
(file > 8 MB or request > 10 MB).

## POST `/api/chat/messages/{message_id}/edit`
```json
{ "message_text": "Thank you sir" }
```
Only the **sender**, only while the message is **unseen**, only **text** messages, only while chat access exists.
200 `{"ok": true, "message": "Message updated.", "item": { /* message, is_edited: true */ }}`

Errors: 400 (`Message cannot be empty.`, too long, `Attachments cannot be edited.`);
403 `forbidden` (`You can only edit your own messages.`, non-participant, access revoked);
404 `not_found` (`Message not found.`); 409 `conflict` (`This message has already been seen and can no longer be edited.`).
