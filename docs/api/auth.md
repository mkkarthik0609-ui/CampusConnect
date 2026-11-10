# Auth API (`/api/auth/*`)

All endpoints are JSON. Session = HttpOnly cookie `cc_session` (SameSite=Lax; Secure in production). Every
POST/PUT/PATCH/DELETE (including login/logout/signup) needs header `X-CSRFToken: <csrf_token>`; get the token
from `GET /api/auth/session`. A missing/wrong token -> `400 {"error": {"code": "csrf_failed", ...}}`. The token
**rotates on login and logout** (both responses contain the new `csrf_token`; use it immediately).
Errors always have the shape `{"error": {"code", "message", "fields"?}}`.

## `GET /api/auth/session`
Public. Always 200. Creates the CSRF token in the session when absent; call it on app start and after a 401.

```json
{ "authenticated": true,
  "user": { "id": 3, "role": "STUDENT", "full_name": "Asha K", "email": "asha@college.edu", "theme": "light",
            "profile_picture_url": null, "student_id": 5, "faculty_id": null },
  "csrf_token": "p3xV...", "unread_notifications": 2, "unread_messages": 0 }
```
Anonymous: `{"authenticated": false, "user": null, "csrf_token": "...", "unread_notifications": 0, "unread_messages": 0}`.
A session that exceeded the idle timeout (60 min) / absolute lifetime (12 h) or whose user was deactivated or
deleted is reported as anonymous (and the cookie is cleared). Role/name/ids always come from the database.

## `POST /api/auth/login`
Public. Body: `{"identifier": "<email | Faculty ID | USN>", "password": "..."}` (identifier is case-insensitive).
Success 200:
```json
{ "ok": true, "message": "Welcome back!", "user": { ...user object... }, "csrf_token": "new-token" }
```
The session is replaced (fixation-safe) and a new CSRF token issued.
Errors:
* 401 `invalid_credentials` - `"Invalid email or password."` Identical for unknown user, wrong password and
  deactivated account (no enumeration).
* 429 `rate_limited` - `"Too many unsuccessful attempts. Please wait a few minutes and try again."` (5 failures per
  identifier or 150 per IP within 15 minutes; even the correct password is refused while locked. The per-IP limit is
  high on purpose: campus Wi-Fi shares one address).
* 400 `captcha_required` (`fields.captcha`) - once an identifier has 3 recent failures, or the client IP has 10, the
  next login must include `captcha_id` + `captcha_answer` (see `GET /api/auth/captcha`).
* 400 `validation_error` (`fields.identifier` / `fields.password`), 400 `csrf_failed`.

Passwords are hashed with **Argon2id** (OWASP profile). A legacy werkzeug hash still verifies and is replaced by an
Argon2id hash at the next successful login. The session stores the account's `session_version`; a password change,
password reset or deactivation increments it, so every other session of that user is rejected (reported as
anonymous) from then on. There is no passkey / WebAuthn sign-in.

## `POST /api/auth/admin-login`
Public. Body `{"identifier": "<email>", "password": "..."}`; same response, throttling and errors as
`/api/auth/login` but only an **active admin** account can sign in here (the password is always verified; failures
are `401 invalid_credentials`).

## `POST /api/auth/admin-invite/inspect`
Public. Body `{"token": "<token from the invitation link>"}` (a POST, so the token never appears in a URL).
200 `{"email": "second@college.edu", "full_name": "Second Admin" | null, "expires_at": "..."}`, `Cache-Control: no-store`.
An unknown, expired, revoked or already used token answers 400 with
`"This invitation link is invalid or has expired. Ask the primary administrator to send a new one."`; repeated bad
tokens from one IP are throttled (429 `rate_limited`).

## `POST /api/auth/admin-invite/accept`  (201)
Public. Body `{"token": "...", "full_name": "...", "password": "...", "confirm_password": "..."}` (`full_name` may be
omitted when the inviter supplied one). Atomically consumes the single-use invitation and creates an **active ADMIN**
account in one transaction. The user is *not* signed in: 201 `{"ok": true, "message": "Your administrator account is
ready. Please sign in."}`; then use `/api/auth/admin-login`. Errors: 400 `validation_error` (`fields.password`,
`fields.confirm_password`, `fields.full_name`), 400 for an invalid/used/expired token, 429 when throttled.
Invitations are created by the primary admin, see [admin.md](admin.md).

## `POST /api/auth/logout`
Public (idempotent). No body. 200 `{"ok": true, "message": "You have been signed out.", "csrf_token": "new-token"}`.

## `GET /api/auth/captcha`
Public. A fresh **image captcha** (distorted letters + digits, case-insensitive). No-store.
```json
{ "captcha_id": "Qk3...", "image": "data:image/png;base64,iVBOR...", "expires_in_seconds": 300 }
```
Each challenge is **single use**: it is consumed by the first check, right or wrong, and expires after 5 minutes.
Only an HMAC of the answer is stored server-side. Errors: 429 `rate_limited` (60 captchas per IP per hour).
Send the answer as `captcha_id` + `captcha_answer` in the signup / login bodies. A missing, wrong, expired or
reused captcha is `400 validation_error` with `fields.captcha`; after any such error fetch a new captcha.

## `POST /api/auth/signup/student`
Public, one step (no e-mail OTP). Body:
```json
{ "college_email": "asha@college.edu", "full_name": "Asha K", "usn": "1AB21CS001", "section_id": 19,
  "phone": "9876543210", "personal_email": "asha@gmail.com", "password": "Str0ngPass!", "confirm_password": "Str0ngPass!",
  "captcha_id": "Qk3...", "captcha_answer": "K7M2XQ" }
```
`section_id` comes from `GET /api/academic/tree`. Success **201** `{"ok": true, "message": "Registration successful. Please sign in."}`
(the user is *not* logged in). The captcha is checked **first**, so accounts cannot be probed without solving one.
Public signup cannot claim the primary admin's e-mail or any e-mail with a pending admin invitation (409 `conflict`). A class that is not listed may be typed in via `custom_class`; it is stored unverified (`is_verified=0`) and hidden from the public pickers until an admin verifies it. Registration is atomic.
Errors: 400 `validation_error` with `fields` (`captcha`, `full_name`, `usn`, `section_id`, `phone`, `personal_email`,
`college_email`, `password`, `confirm_password`), 409 `conflict` (USN or e-mail taken; `fields.usn` /
`fields.college_email`). Unknown extra fields are rejected with 400.

## `POST /api/auth/signup/faculty`
Public. Body:
```json
{ "full_name": "Prof Rao", "faculty_code": "FAC001", "department": "AIML", "professional_email": "rao@college.edu",
  "subjects": ["DSA", "OS"], "password": "Str0ngPass!", "confirm_password": "Str0ngPass!",
  "captcha_id": "Qk3...", "captcha_answer": "K7M2XQ" }
```
`subjects` may also be a comma-separated string (`"DSA, OS"`); at least one is required. `department` must be one of
`GET /api/auth/faculty-departments` (case-insensitive). Classes are never chosen here; the admin assigns them.
Success **201** `{"ok": true, "message": "Registration successful. Please sign in."}`.
Errors: 400 `validation_error` (`fields.department`, `fields.subjects`, `fields.password`, `fields.confirm_password`, ...),
409 `conflict` (`fields.faculty_code` already registered / `fields.professional_email` taken).

## `GET /api/auth/faculty-departments`
Public. `{"items": ["AIML", "AIDE", "GenAI", "Cybersecurity", "Blockchain", "IoT"]}` (active departments only).

## Password policy (all signups, password change, admin bootstrap)
At least 8 characters (max 128) with an uppercase letter, a lowercase letter and a digit; must not equal the e-mail,
the part of the e-mail before `@`, the USN or the Faculty ID. Violations -> 400 `validation_error`, `fields.password`
(`fields.new_password` for a change) = `"Password must be at least 8 characters and include an uppercase letter, a lowercase letter and a digit."`
or `"Password must not be the same as your email, username or ID."`.

## Other cross-cutting errors
401 `unauthenticated` (any protected endpoint without a valid session), 403 `forbidden`, 400 `csrf_failed`,
400 `validation_error` / `bad_request` (malformed JSON), 413 `payload_too_large` (request > 10 MB).
