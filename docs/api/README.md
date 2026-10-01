# Campus Connect API docs

FastAPI backend (`api/`), JSON under `/api/*` plus authenticated file serving under `/uploads/*`.
Start with the two cross-cutting documents, then the per-area contract.

| Document | Covers |
|---|---|
| [CONVENTIONS.md](CONVENTIONS.md) | Transport, session cookie, CSRF header, error shape, pagination |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Settings, middleware, dependencies, services/models layering, deployment shape |
| [auth.md](auth.md) | Captcha, signup, login (email / Faculty ID / USN), logout, session |
| [account.md](account.md) | Profile, change password, profile photo |
| [academic.md](academic.md) | Public academic tree (Branch → Department → Year → Section) |
| [academics.md](academics.md) | Admin: tree editor, faculty assignments, class directory |
| [student.md](student.md) | Student dashboard, faculty search, profile-change requests |
| [faculty.md](faculty.md) | Faculty dashboard, classes, student search, class requests |
| [chat.md](chat.md) | Threads, messages, attachments |
| [meetings.md](meetings.md) | Meeting requests, responses, availability |
| [supporting.md](supporting.md) | Supporting-faculty relationships |
| [notifications.md](notifications.md) | In-app notifications |
| [admin.md](admin.md) | Admin console: users, requests, remove registration |
| [research.md](research.md) | Scheduling research results and runs |
| [system.md](system.md) | `/healthz`, uploads, misc |
