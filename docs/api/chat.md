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

// message  (the same shape on /api/admin-messages)
{ "id": 2, "is_mine": true, "sender_name": "Asha Rao",
  "message_text": "Notes attached",       // null for an attachment without caption, and for an unsent message
  "attachment": { "url": "/uploads/chat/<uuid>.pdf", "name": "notes.pdf", "type": "pdf", "is_image": false } /* or null */,
  "status": "sent",        // sent (one tick) -> delivered (two grey ticks) -> seen (two blue ticks)
  "is_seen": false,        // = status == "seen" (for incoming messages: always true once you fetched them)
  "delivered_at": null, "seen_at": null,
  "is_edited": false,
  "is_unsent": false,      // "Unsend for everyone" tombstone: no text, no attachment, no quote - ever
  "unsent_at": null,
  "can_edit": false,       // is_mine && !is_unsent && no attachment && sent less than 15 minutes ago
  "can_unsend": true,      // is_mine && !is_unsent
  "reply_to": { "id": 1, "is_mine": false, "sender_user_id": 4, "sender_name": "Dr. Meera Nair",
                "text_preview": "Can we meet?", "attachment_kind": null /* "image" | "file" */,
                "attachment_name": null, "unsent": false } /* or null */,
  "created_at": "2026-10-01 03:12:49", "updated_at": "2026-10-01 03:12:49" }   // updated_at changes with every state change
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
      "unread_count": 1,                         // incoming, visible, not unsent, not yet seen
      "last_message": "Notes attached",          // text, "Attachment: <name>", "You unsent a message" / "<Name> unsent a message", or null
      "last_message_at": "2026-10-01 03:12:49",  // null when empty
      "last_message_is_mine": true,              // null when empty
      "last_message_is_unsent": false,           // null when empty
      "last_message_status": "delivered",        // ticks of MY last message (null when it is not mine)
      "updated_at": "2026-10-01 03:12:49" }
  ],
  "total": 1,
  "total_unread": 1
}
```
`other` also carries `online` (bool), `last_active_at` (UTC, null when unknown) and `typing` (bool): presence is the
other participant's last fetch/poll/send, kept in memory (see *Typing and presence* below).
Messages "deleted for me" are ignored for the preview and the unread count. `unread_count` = incoming messages not yet
seen by me. Listing marks the incoming messages of the listed chats as **delivered** (never as seen).

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

## GET `/api/chat/{chat_id}?after_id=0&updated_since=`
Participant only. **Marks every incoming message of this chat as seen** (so the sender's messages flip to `seen` on their
next fetch). Messages "deleted for me" by the viewer are omitted. Efficient polling (2.5 s while the tab is focused):
send `after_id=<last_id>` and `updated_since=<server_time>` of the previous response; the response then contains the **new**
messages (`id > after_id`) **and** older ones that changed at/after `updated_since` (ticks, edit, unsend): merge by `id`. Each response holds at most the **newest 300** matching messages (returned oldest first), so a first load of a very long thread is bounded.
`updated_since` is an ISO-8601 timestamp (`2026-10-01T03:12:49Z`, any offset; `YYYY-MM-DD HH:MM:SS` UTC also works), 400 when malformed.
```json
{
  "chat": { "id": 1, "other": { /* other party + online, last_active_at, typing */ }, "created_at": "2026-10-01 03:12:49", "updated_at": "2026-10-01 03:12:49" },
  "messages": [ { /* message */ } ],            // oldest first
  "last_id": 2,                                 // highest id returned (>= after_id)
  "server_time": "2026-10-01 03:12:55"          // pass back as updated_since
}
```
Errors: 403 `forbidden` (`You do not have access to this conversation.` for non-participants;
`This faculty member is no longer assigned to your class.` / `This student is no longer in one of your assigned classes.`),
404 `not_found` (`Conversation not found.`), 400 (non-integer id, bad `updated_since`).

## POST `/api/chat/{chat_id}/messages`
Either **JSON** `{ "message_text": "Good morning sir", "reply_to_id": 7 }` (1–4000 chars after trimming) **or** `multipart/form-data` with
field `attachment` (PDF / PNG / JPG / JPEG / DOCX, <= 8 MB, magic bytes checked), an optional `message_text` caption and an optional `reply_to_id` form field.
`reply_to_id` (optional) must be a message of **this** chat, otherwise 400. Access and the quote are checked before any file is stored.

201
```json
{ "ok": true, "message": "Message sent.",
  "item": { "id": 1, "is_mine": true, "message_text": "Good morning sir", "attachment": null,
            "status": "sent", "is_seen": false, "is_edited": false, "is_unsent": false, "can_edit": true, "can_unsend": true,
            "reply_to": null, "created_at": "2026-10-01 03:12:49", "updated_at": "2026-10-01 03:12:49" } }
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
WhatsApp rule: only the **sender**, only **text** messages (no attachments), not unsent, and only within **15 minutes** of
sending (seen or not), while chat access exists. The message gets `is_edited: true`.
200 `{"ok": true, "message": "Message updated.", "item": { /* message */ }}`

Errors: 400 (`Message cannot be empty.`, too long, `Attachments cannot be edited.`);
403 `forbidden` (`You can only edit your own messages.`, non-participant, access revoked);
404 `not_found` (`Message not found.`); 409 `conflict` (`The 15-minute edit window has already passed for this message.`,
`This message was already unsent.`).

## POST `/api/chat/messages/{message_id}/unsend`
Instagram-style **Unsend for everyone**. No body. Only the sender, at any time (even after it was seen), while chat access exists.
The message becomes a tombstone for both participants: `is_unsent: true`, `unsent_at` set, `message_text` /
`attachment` / `reply_to` gone, the stored text is wiped and the uploaded file is **deleted from storage** (its URL 404s). It can no longer be
edited, and replies that quoted it show `reply_to.unsent: true` without the text. The chat list shows `You unsent a message` /
`<Name> unsent a message`. **Idempotent**: unsending again returns 200 with the tombstone.

200 `{"ok": true, "message": "Message unsent.", "item": { /* message */ }}`.
Errors: 403 (not the sender, non-participant, access revoked), 404 (`Message not found.`).

## POST `/api/chat/messages/{message_id}/delete-for-me`
Hides the message for the caller only (a participant, access still valid). The other side keeps seeing it, and so does the admin
viewer. Hidden messages disappear from the thread, the list preview and the unread count. **Idempotent**.
200 `{"ok": true, "message": "Message deleted for you.", "id": 5}`. Errors: 403, 404.

## POST `/api/chat/{chat_id}/typing`
"I am typing" signal, valid for ~5 seconds (the client should call it at most every ~3 s while typing; sending a message clears it).
200 `{"ok": true}`. The other participant sees `chat.other.typing: true` in `GET /api/chat/{id}` and `other.typing` in the list.
Errors: 403 / 404 exactly like reading the chat.

### Typing and presence
Both live in memory (`services/presence.py`; the app runs a single worker, restart = unknown). `other.online` is true when the
other participant fetched, polled, sent or signalled typing within the last 30 seconds; `other.last_active_at` is that moment
(UTC) or `null`.

---

## Faculty <-> admin messages — `/api/admin-messages/*`
Roles: FACULTY or ADMIN (students 403). Same message shape and behaviour as the chat above (ticks, `reply_to`, 15-minute edit
window, unsend, delete-for-me, `after_id` + `updated_since`, typing, presence). The conversation id is the **faculty member's user id**
(faculty can only use their own; an admin can use any active faculty member). Router: `api/routers/admin_messages.py`.
Attachments are not supported here (text up to 5000 chars).

| Method + path | Purpose |
|---|---|
| `GET /api/admin-messages` | conversations: `{ items: [{ conversation_id, other, unread_count, last_message, last_message_at, last_message_is_mine, last_message_is_unsent, last_message_status }], total, total_unread }`. Faculty get one item (the admin); an admin gets every active faculty member, conversations with messages first. Marks incoming messages delivered. |
| `GET /api/admin-messages/{faculty_user_id}?after_id=&updated_since=` | `{ chat: { id, other }, messages, last_id, server_time }`; marks incoming messages seen. 403 for another faculty's conversation, 404 unknown faculty. |
| `POST /api/admin-messages` | send `{ message_text, reply_to_id?, recipient_user_id? }` (`recipient_user_id` required for admins) -> 201 `{ ok, id, item }`. |
| `POST /api/admin-messages/{faculty_user_id}/typing` | typing signal. |
| `POST /api/admin-messages/messages/{id}/edit` \| `/unsend` \| `/delete-for-me` | as for chat (participants only; edit / unsend sender only). |
