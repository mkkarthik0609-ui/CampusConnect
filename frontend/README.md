# Campus Connect frontend

React 19 (JavaScript, no TypeScript) + Vite 8 + Tailwind CSS v4 + shadcn/ui (Radix, hand-themed) + TanStack Query +
React Router 7 + Framer Motion (`motion`, landing page only). The backend is the FastAPI JSON API in `../api`
(contract: `../docs/api/CONVENTIONS.md`, wiring: `../docs/api/ARCHITECTURE.md`, per-area endpoint docs in `../docs/api/*.md`).

## Run it

```
cd frontend
npm install
npm run dev            # http://localhost:5173, proxies /api /uploads /healthz -> http://127.0.0.1:5000
npm run dev:mock       # same, but with an in-memory API mock (src/lib/mock.js) - no backend needed
npm run build          # -> frontend/dist  (FastAPI serves it when present; every non-API GET falls back to index.html)
npm run preview        # serve dist on :4173 with the same proxy
npm run lint
```

Backend for `npm run dev` (from the repo root), with a throw-away database:

```
$env:DATABASE_PATH="$env:TEMP\cc_fe_dev.db"; $env:UPLOAD_ROOT="$env:TEMP\cc_fe_uploads"
venv\Scripts\python.exe -m uvicorn api.main:app --port 5000
```

`VITE_BACKEND_URL` overrides the proxy target. `dev:mock` sign-in: `student`, `faculty` or `admin`, password `Passw0rd!`.
The mock is imported only behind `import.meta.env.DEV`, so it never ships in a production build.

## Versions and decisions

- Tailwind **v4** with `@tailwindcss/vite` (no `tailwind.config`; theme lives in `src/index.css`). shadcn CLI
  (`npx shadcn@latest add <component>`) works in JS mode (`components.json` has `"tsx": false`) and generates `.jsx`.
- Alias `@` -> `src` (`vite.config.js` + `jsconfig.json`).
- Fonts are self-hosted from npm (`@fontsource-variable/*`): Bricolage Grotesque (headings, numerals), Figtree (UI), JetBrains Mono (IDs, codes only).
- **Do not create a directory named `public`** anywhere under `frontend/src`: the repo's root `.gitignore` ignores `public/`, which hides the files from git *and* from Tailwind's class scanner. (The landing/login pages live in `src/pages/site/`; the favicon is `src/assets/favicon.svg`.)

## File map

```
index.html                 pre-paint theme script, favicon
vite.config.js             alias, dev/preview proxy, manual chunks (motion, query, router, radix)
components.json            shadcn config (JS, aliases)
src/
  main.jsx                 entry (mock gate for dev:mock)
  App.jsx                  providers: QueryClient > Auth > Theme > Tooltip > Dialogs > Router + Toaster
  routes.jsx               THE route table (lazy pages, guards)           <- feature agents edit this
  index.css                design tokens + Tailwind theme + base styles
  lib/
    api.js                 fetch client, CSRF, ApiError, upload helper, unauthorized handler
    endpoints.js           typed-by-convention wrappers for auth/account/academic/notifications
    queryClient.js         QueryClient defaults + `queryKeys`
    theme.jsx / themeStorage.js   light/dark provider + storage helpers
    nav.js                 sidebar entries per role, ROLE_HOME
    format.js              date/time, initials, safeNext, pluralize
    notificationTarget.js  notification -> route mapping
    mock.js                dev-only API mock
  auth/
    AuthProvider.jsx       useAuth(): session, role helpers, unread counters (30 s poll), login/logout
    guards.jsx             RequireAuth, RequireRole, GuestOnly, AppRedirect
  hooks/                   usePageTitle, useDebouncedValue, useMediaQuery, useAcademicTree, useFacultyDepartments, useMeta
  components/
    ui/                    shadcn primitives, themed (button, input, select, dialog, sheet, table, tabs, ...)
    app/                   shared Campus Connect components (below)
    landing/               landing-page sections (Framer Motion lives only here)
  pages/
    site/                  Landing, Login, SignupStudent, SignupFaculty         (public)
    shared/                Notifications, ChangePassword, NotFound, Forbidden, ServerError
    student/ faculty/ admin/   one file per page; currently <PagePlaceholder/>
```

## Routes

| URL | Guard | Page file |
|---|---|---|
| `/` | none (header shows "Open dashboard" when signed in) | `pages/site/Landing.jsx` |
| `/login`, `/signup/student`, `/signup/faculty` | `GuestOnly` + `AuthLayout` (signed-in users go to `?next=` or their home) | `pages/site/*` |
| `/app` | redirects to the role's home (`ROLE_HOME` in `lib/nav.js`) | - |
| `/notifications`, `/account/password` | `RequireAuth` + `AppShell` | `pages/shared/*` |
| `/student/*` | `RequireRole STUDENT`: `dashboard profile chat chat/:id meetings meetings/request/:facultyId find-faculty` | `pages/student/*` |
| `/faculty/*` | `RequireRole FACULTY`: `dashboard classes classes/:sectionId profile chat chat/:id meetings find-students approvals` | `pages/faculty/*` |
| `/admin/*` | `RequireRole ADMIN`: `dashboard academics assignments assignment-requests classes classes/:sectionId students faculty meetings chats chats/:id approvals admins research` | `pages/admin/*` |
| `*` | 404 (inside the shell when signed in) | `pages/shared/NotFound.jsx` |

`/student`, `/faculty`, `/admin` alone redirect to `dashboard`. A wrong role sees the 403 page inside the shell.

### How to add or build a page

1. Open the placeholder (`src/pages/<role>/<Name>.jsx`) and replace its default export with the real page. Keep the path and the default export; `routes.jsx` already imports it lazily.
2. New URL? Add **one line** to the role's array in `src/routes.jsx`:
   `{ path: "reports", element: page(() => import("@/pages/admin/Reports")) },`
   and, if it needs a sidebar entry, one object in `src/lib/nav.js`.
3. Start the page with `<PageHeader title="..." />` (renders the single `<h1>`, sets `document.title`). Do **not** add your own page padding or max-width; `AppShell` provides them.
4. Put API calls in `src/lib/<area>Api.js` (same style as `endpoints.js`), data fetching in `useQuery` / `useMutation`, query keys in `queryKeys` (`lib/queryClient.js`).
5. Document the endpoints you used in your area's `docs/api/*.md` (the backend agent owns those files; add a "Frontend usage" note only if something is surprising).

## API client (`src/lib/api.js`)

```js
import { api, ApiError, errorMessage, toFormData } from "@/lib/api";

const { items } = await api.get("/api/meetings", { params: { status: "PENDING" } });
await api.post("/api/meetings", { faculty_id: 4, reason: "Project review" });
await api.upload("/api/chats/3/messages", formData);                    // multipart POST
await api.upload("/api/account/photo", toFormData({ file }), { method: "PUT" });
```

- Same-origin `fetch` with the session cookie. JSON in/out; `multipart/form-data` via `api.upload`.
- CSRF: the token comes from `GET /api/auth/session`; every non-GET sends `X-CSRFToken`. A `400 csrf_failed` refreshes the token once and retries. Login/logout re-read the session.
- Errors are always `ApiError { status, code, message, fields }` (`err.fields.<name>` for per-field messages, `err.isForbidden`, `err.isRateLimited`, ...). Network failures are `status 0`, HTML error pages are never surfaced.
- `401` on any call clears the auth state; the guards redirect to `/login?next=<current page>`. Pass `{ skipAuthRedirect: true }` for calls that legitimately return 401 (login).
- In a mutation: `onError: (err) => toast.error(errorMessage(err))`; on forms: `setErrors(err.fields)`.
- Uploaded files: `uploadUrl(path)` -> `/uploads/<path>` (the API auth-checks reads).

### Foundation endpoints (checked against `api/routers/`)

| Call | Endpoint |
|---|---|
| session + counters | `GET /api/auth/session` -> `{ authenticated, user, csrf_token, unread_notifications, unread_messages }` |
| sign in / out | `POST /api/auth/login { identifier, password }`, `POST /api/auth/logout` |
| captcha | `GET /api/auth/captcha` (single-use image; send `captcha_id` + `captcha_answer`) |
| student signup | `POST /api/auth/signup/student` (`section_id` from the class picker, plus the captcha fields) |
| faculty signup | `POST /api/auth/signup/faculty`, `GET /api/auth/faculty-departments` |
| account | `POST /api/account/password`, `POST /api/account/theme` |
| classes | `GET /api/academic/tree` (public) |
| notifications | `GET /api/notifications`, `POST /api/notifications/:id/read`, `POST /api/notifications/read-all` |
| meta | `GET /api/meta` (`app`) |

## Auth (`useAuth()`)

```js
const { user, role, status, isAuthenticated, isStudent, isFaculty, isAdmin, hasRole, unread, login, logout, refresh, patchUser } = useAuth();
```
`status`: `loading | authenticated | unauthenticated | error`. The session query refetches every 30 s (also on window focus),
so `unread.notifications` / `unread.messages` stay current; after an action that changes them call
`queryClient.invalidateQueries({ queryKey: queryKeys.session })`.

## Theme and design tokens

Direction: **ink & saffron**: deep ink-navy chrome, cobalt for action, saffron only for what needs attention, cool paper
surfaces (light) / ink-blue surfaces (dark). Tokens are CSS variables in `src/index.css` (`:root` and `.dark`) exposed to
Tailwind through `@theme inline`:

| Use | Tailwind classes |
|---|---|
| page / card / sunken / quiet surface | `bg-background` `bg-card` `bg-sunken` `bg-surface-2` |
| text | `text-foreground` (ink), `text-ink-2`, `text-muted-foreground` |
| lines | `border-line` (default border), `border-line-strong`, `border-input` |
| action | `bg-primary` `hover:bg-primary-hover` `text-primary-foreground`, soft: `bg-primary-soft text-primary-ink` |
| attention | `bg-saffron text-on-saffron`, soft: `bg-saffron-soft text-saffron-ink` |
| semantic | `bg-ok text-ok-ink`, `bg-warn text-warn-ink`, `bg-danger text-danger-ink`, `bg-info text-info-ink`, `bg-neutral text-neutral-ink` (+ `border-*-line`) |
| dark chrome (sidebar, landing bands) | `bg-nav text-nav-ink text-nav-muted bg-nav-hover bg-nav-active border-nav-line` |
| type | `font-sans` (Figtree), `font-display` (Bricolage), `font-mono` (IDs/codes only) |
| depth | `shadow-sm` (cards), `shadow-md` (popovers / floating) |
| radii | `rounded-md` 10px (controls), `rounded-lg` 12px (cards), `rounded-xl` 18px (auth card / dialogs) |

Rules: never hard-code hex in components (use tokens so dark mode works); saffron text on light surfaces fails AA, use
`text-saffron-ink` there; one primary (cobalt) action per view; headings are `font-display`; IDs (USN, Faculty ID, codes) are
`font-mono`. Dark mode is the `.dark` class on `<html>`: signed in -> the user's saved `theme` (toggle calls
`POST /api/account/theme`); signed out -> `prefers-color-scheme`. A pre-paint script in `index.html` avoids a flash.
`useTheme()` gives `{ theme, setTheme, toggle }`.

## Shared components (`src/components/app/`)

| Component | Use |
|---|---|
| `AppShell` | signed-in layout (sidebar >= 60rem; top bar + slide-out menu below). Rendered by the route table, not by pages |
| `PageHeader`, `SectionHeading` | page `<h1>` (+ description, actions, back link, sets `document.title`) / `<h2>` rows |
| `EmptyState` | empty lists: icon, what is empty, the next step (`compact` for inside cards) |
| `StatusPill` | `PENDING ACCEPTED APPROVED ACTIVE REJECTED COMPLETED CANCELLED` (+ `tone`, `label`) |
| `UserAvatar` | profile picture or initials palette (`size` xs/sm/md/lg/xl) |
| `ClassPath` | "Branch -> Department -> Year -> Section" breadcrumb pills; accepts the API class object or `label` |
| `ClassPicker` | cascading class select fed by `GET /api/academic/tree`; `onChange(sectionId, info)` |
| `DataTable` | table that becomes labelled cards below 40rem; loading / error / empty built in |
| `useConfirm()`, `usePrompt()`, `ConfirmDialog`, `PromptDialog` | replace `window.confirm` / `window.prompt` (e.g. meeting-cancel reason: `await prompt({ title, label: "Reason", required: true })`) |
| `FormField` | label + control + hint + error with correct `for`/`aria-describedby`/`aria-invalid` |
| `PasswordInput`, `SubmitButton`, `Notice`, `StatTile`, `Spinner`/`ListSkeleton`/`PageLoader` | form and feedback pieces |
| `ThemeToggle`, `NotificationBell`, `UserMenu`, `Brand`/`BrandMark` | chrome |
| `PagePlaceholder` | the stand-in on unbuilt pages |

Conventions: one `<h1>` per page (via `PageHeader`); icons are `lucide-react` only, with `aria-hidden` when decorative;
buttons keep 44px touch targets on coarse pointers; toasts (`sonner`) report the result of an action, `Notice` shows standing
context; destructive actions go through `useConfirm`; lists show skeletons while loading, an `EmptyState` when empty, an
inline `Notice` on error; never rely on colour alone (pills carry text); respect reduced motion (global CSS rule + `useReducedMotion` in motion code).
Add a shadcn component with `npx shadcn@latest add <name>` and then re-theme it to the tokens (see `ui/button.jsx`, `ui/input.jsx`).

## Landing page

`pages/site/Landing.jsx` + `components/landing/*`. Hero load sequence (word reveal, class-path pills landing, chat and meeting
status), pointer parallax (springs, transform only), a scroll-scrubbed "how it works" story (pinned stage on desktop, stacked
stages on narrow screens), hover-widening role panels, and `prefers-reduced-motion` fallbacks (final states, no scrubbing).
The `motion` chunk loads only with this route (`LazyMotion` + `m` components).

## Accessibility checklist (already handled by the foundation)

Skip link in every layout, landmarks (`header`, `nav`, `main#main`, `aside`), route-change announcements (`RouteAnnouncer`),
visible 3px focus outline, labelled controls, `aria-live` toasts, AA colour pairs in both themes, 44px targets, no horizontal
scroll down to 360px. Keep these when adding pages.

## Known gaps / notes for feature agents

- All `student/*`, `faculty/*`, `admin/*` pages are placeholders.
- Notification deep links (`lib/notificationTarget.js`) are best-effort until the chat/meeting routes exist; adjust the mapping when entity ids are final.
- The 30 s unread poll uses the session endpoint; swap to a lighter counters endpoint if the backend adds one.
- The shell's first load is ~80 kB gzip of app code + shared vendor chunks (router, query, radix); lazy-load heavy page-specific libraries.
