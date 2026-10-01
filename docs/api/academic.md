# Academic hierarchy API

## `GET /api/academic/tree`
Public (no auth), active rows only. Branches, departments and years with no active children are omitted.
```json
{ "branches": [
  { "id": 1, "name": "CSE", "departments": [
    { "id": 2, "name": "AIDE", "years": [
      { "id": 5, "name": "1st Year", "sections": [ { "id": 13, "name": "A" }, { "id": 14, "name": "B" } ] }
    ] }
  ] }
] }
```
Use `section.id` as `section_id` in student signup and in every API that takes a class. Admin edits live under
`/api/admin/academic/*` (documented in the admin docs).

Related: `GET /api/auth/faculty-departments` returns the active department names for faculty signup.
