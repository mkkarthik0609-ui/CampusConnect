# Account API (`/api/account/*`)

Requires a signed-in user (any role) and the `X-CSRFToken` header. See `auth.md` for the session/CSRF flow.

## `POST /api/account/password`
Body `{"current_password": "...", "new_password": "...", "confirm_password": "..."}`.
Success 200 `{"ok": true, "message": "Your password has been changed."}`. The session stays signed in.

Errors (400 `validation_error` unless noted; `fields` names the input):
| situation | field | message |
|---|---|---|
| wrong current password | `current_password` | `Your current password is incorrect.` |
| new != confirm | `confirm_password` | `New password and confirmation do not match.` |
| new == current | `new_password` | `Your new password must be different from the current one.` |
| weak password / equals e-mail | `new_password` | password policy message (see `auth.md`) |
| missing field | that field | `This field is required.` |

* 429 `rate_limited` after 5 wrong current-password attempts (15 minute window).
* 401 `unauthenticated` when not signed in.

## `POST /api/account/theme`
Body `{"theme": "light" | "dark"}`. Success 200 `{"ok": true, "message": "Theme updated.", "theme": "dark"}`.
The value is stored on the user (`user.theme` in later session responses). Anything else -> 400 `validation_error`
(`fields.theme`).
