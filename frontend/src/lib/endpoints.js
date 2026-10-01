/**
 * Endpoint wrappers for the areas the foundation owns (auth, account, academic tree, notifications).
 * Verified against api/routers/{auth,account,notifications,academic,system}.py (FastAPI; request models use
 * extra="forbid", so send exactly the documented keys).
 * Paths and payload shapes live HERE, never inside components. Feature agents: add your own
 * `src/lib/<area>Api.js` next to this file in the same style and document the endpoints you use in
 * the README's "API surface" table.
 *
 * Source of truth: docs/api/*.md and the routers in api/routers/. Area docs were not all published when this
 * file was written, so these calls were checked against the router code directly.
 */
import { api, fetchSession, setCsrfToken, toFormData } from "@/lib/api";

// ---- auth ---------------------------------------------------------------------------------
export const authApi = {
  /** GET /api/auth/session -> { authenticated, user, csrf_token, unread_notifications, unread_messages } (always 200) */
  session: () => fetchSession(),

  /**
   * POST /api/auth/login { identifier, password } -> { ok, message, user, csrf_token }
   * `identifier` = email, Faculty ID or USN. 401 `invalid_credentials`, 429 `rate_limited` (lockout).
   */
  async login({ identifier, password }) {
    const data = await api.post("/api/auth/login", { identifier, password }, { skipAuthRedirect: true });
    setCsrfToken(data?.csrf_token);
    return data;
  },

  /** POST /api/auth/logout -> { ok, message, csrf_token } */
  async logout() {
    const data = await api.post("/api/auth/logout", {}, { skipAuthRedirect: true });
    setCsrfToken(data?.csrf_token);
    return data;
  },

  // ---- student signup (3 steps) ----
  /** Step 1: POST /api/auth/signup/student/start { college_email } -> { ok, message, email, delivery: "email"|"demo", expires_in_minutes, demo_otp? } */
  studentStart: (college_email) => api.post("/api/auth/signup/student/start", { college_email }, { skipAuthRedirect: true }),
  /** Step 2: POST /api/auth/signup/student/verify { college_email, otp } -> { ok, email }   (error field: otp) */
  studentVerify: (college_email, otp) => api.post("/api/auth/signup/student/verify", { college_email, otp }, { skipAuthRedirect: true }),
  /**
   * Step 3: POST /api/auth/signup/student/register (201)
   * { college_email, full_name, usn, section_id, phone, personal_email, password, confirm_password }
   */
  studentRegister: (body) => api.post("/api/auth/signup/student/register", body, { skipAuthRedirect: true }),

  /** POST /api/auth/signup/faculty (201) { full_name, faculty_code, department, professional_email, subjects: string[], password, confirm_password } */
  facultySignup: (body) => api.post("/api/auth/signup/faculty", body, { skipAuthRedirect: true }),
  /** GET /api/auth/faculty-departments -> { items: string[] } active department names for the faculty signup select */
  facultyDepartments: () => api.get("/api/auth/faculty-departments", { skipAuthRedirect: true }),
};

// ---- account ------------------------------------------------------------------------------
export const accountApi = {
  /** POST /api/account/password { current_password, new_password, confirm_password } -> { ok, message } (fields: current_password, new_password, confirm_password) */
  changePassword: (body) => api.post("/api/account/password", body),
  /** POST /api/account/theme { theme: "light" | "dark" } -> { ok, theme } */
  setTheme: (theme) => api.post("/api/account/theme", { theme }),
};

// ---- app metadata -------------------------------------------------------------------------
export const metaApi = {
  /** GET /api/meta -> { app, demo_otp_enabled } */
  get: () => api.get("/api/meta", { skipAuthRedirect: true }),
};

// ---- academic hierarchy -------------------------------------------------------------------
export const academicApi = {
  /** GET /api/academic/tree (public) -> { branches: [{ id, name, departments: [{ id, name, years: [{ id, name, sections: [{ id, name }] }] }] }] } */
  tree: () => api.get("/api/academic/tree", { skipAuthRedirect: true }),
};

// ---- notifications ------------------------------------------------------------------------
export const notificationsApi = {
  /** GET /api/notifications -> { items: [{ id, type, title, message, related_entity_type, related_entity_id, is_read, created_at }], unread_count } */
  list: () => api.get("/api/notifications"),
  /** POST /api/notifications/:id/read -> { ok, unread_count } */
  markRead: (id) => api.post(`/api/notifications/${id}/read`, {}),
  /** POST /api/notifications/read-all -> { ok, unread_count: 0 } */
  markAllRead: () => api.post("/api/notifications/read-all", {}),
};

// ---- faculty (docs/api/faculty.md, supporting.md, chat.md) --------------------------------
export const facultyApi = {
  /** GET /api/faculty/dashboard -> { profile, subjects, classes, pending_class_requests, supporting_students, pending_supporting_requests, recent_meetings, pending_permission_requests, counts } */
  dashboard: () => api.get("/api/faculty/dashboard"),
  /** GET /api/faculty/profile -> { profile, subjects, classes, change_requests, departments } */
  profile: () => api.get("/api/faculty/profile"),
  /** POST /api/faculty/profile/picture (multipart, field `profile_picture`) -> { ok, message, profile_picture_url } */
  uploadPicture: (file) => api.upload("/api/faculty/profile/picture", toFormData({ profile_picture: file })),
  /** POST /api/faculty/profile/change-request { department?, professional_email?, reason } -> 201 { ok, message, id } */
  requestProfileChange: (body) => api.post("/api/faculty/profile/change-request", body),
  /** GET /api/faculty/classes -> { assignments: [class + assignment fields], requests: [{ id, status, note, class, ... }] } */
  classes: () => api.get("/api/faculty/classes"),
  /** POST /api/faculty/classes/request { section_id, note? } -> 201 { ok, message, id } (409 when assigned / already pending) */
  requestClass: (body) => api.post("/api/faculty/classes/request", body),
  /** GET /api/faculty/classes/:sectionId -> { class, students, co_faculty }  (403 unless actively assigned) */
  classDetail: (sectionId) => api.get(`/api/faculty/classes/${sectionId}`),
  /** GET /api/faculty/permission-requests -> { items: [student profile-change request], total } */
  permissionRequests: () => api.get("/api/faculty/permission-requests"),
  /** POST /api/faculty/permission-requests/:id/decide { decision: "approve" | "reject" } -> { ok, message, status } */
  decidePermissionRequest: (id, decision) => api.post(`/api/faculty/permission-requests/${id}/decide`, { decision }),
  /** GET /api/supporting/students/search?q= -> { items: [student card + relationship + can_request], total, query } */
  searchStudents: (q) => api.get("/api/supporting/students/search", { params: { q } }),
  /** POST /api/supporting/students/:studentId/request -> 201 { ok, message, id, relationship } */
  requestSupporting: (studentId) => api.post(`/api/supporting/students/${studentId}/request`, {}),
  /** POST /api/supporting/:relId/accept | reject -> { ok, message, status, relationship } */
  respondSupporting: (relId, decision) => api.post(`/api/supporting/${relId}/${decision}`, {}),
  /** POST /api/chat/open { student_id } -> { ok, message, chat_id } */
  openChat: (studentId) => api.post("/api/chat/open", { student_id: studentId }),
};

// ---- student (api/routers/student.py, docs/api/student.md) ---------------------------------
export const studentApi = {
  /** GET /api/student/dashboard -> { student, assigned_faculty[], supporting_faculty[], pending_supporting_requests[], recent_meetings[], counts } */
  dashboard: () => api.get("/api/student/dashboard"),
  /** GET /api/student/profile -> { student, assigned_faculty[], permission_requests[] } */
  profile: () => api.get("/api/student/profile"),
  /** POST /api/student/profile/picture (multipart, part `profile_picture`, PNG/JPG <= 3 MB) -> { ok, message, profile_picture_url } */
  uploadPicture: (file) => api.upload("/api/student/profile/picture", toFormData({ profile_picture: file })),
  /** POST /api/student/profile/change-request { phone?, personal_email?, reason } -> 201 { ok, message, id } (fields: phone, personal_email, reason) */
  changeRequest: (body) => api.post("/api/student/profile/change-request", body),
};

// ---- chat (api/routers/chat.py, docs/api/chat.md) -------------------------------------------
export const chatApi = {
  /** GET /api/chat -> { items: [{ chat_id, other, unread_count, last_message, last_message_at, last_message_is_mine }], total, total_unread } */
  list: () => api.get("/api/chat"),
  /** POST /api/chat/open { faculty_id } (student) | { student_id } (faculty) -> { ok, chat_id } */
  open: (body) => api.post("/api/chat/open", body),
  /** GET /api/chat/:id?after_id= -> { chat: { id, other }, messages[], last_id }. Marks incoming messages as seen. */
  get: (id, afterId = 0) => api.get(`/api/chat/${id}`, { params: { after_id: afterId || undefined } }),
  /** POST /api/chat/:id/messages  JSON { message_text } or multipart { attachment, message_text? } -> 201 { ok, item } */
  send: (id, { text, file } = {}) =>
    file
      ? api.upload(`/api/chat/${id}/messages`, toFormData({ attachment: file, message_text: text || undefined }))
      : api.post(`/api/chat/${id}/messages`, { message_text: text }),
  /** POST /api/chat/messages/:id/edit { message_text } -> { ok, item } (409 once the other side has seen it) */
  edit: (messageId, text) => api.post(`/api/chat/messages/${messageId}/edit`, { message_text: text }),
};

// ---- meetings (api/routers/meetings.py, docs/api/meetings.md) -------------------------------
export const meetingsApi = {
  /** GET /api/meetings?status= -> { items: [meeting], total } */
  list: (status) => api.get("/api/meetings", { params: { status } }),
  /** POST /api/meetings { faculty_id, reason, details? } (student) -> 201 { ok, id, meeting } (fields: reason, details) */
  create: (body) => api.post("/api/meetings", body),
  /** POST /api/meetings/:id/respond { decision: "accept"|"reject", faculty_response?, meeting_time_text? } (faculty; time required to accept) */
  respond: (id, body) => api.post(`/api/meetings/${id}/respond`, body),
  /** POST /api/meetings/:id/cancel { reason } (students must give a reason; optional for faculty) */
  cancel: (id, reason) => api.post(`/api/meetings/${id}/cancel`, { reason: reason || undefined }),
  /** POST /api/meetings/:id/complete (ACCEPTED only) */
  complete: (id) => api.post(`/api/meetings/${id}/complete`, {}),
};

// ---- supporting-faculty relationships (api/routers/supporting.py, docs/api/supporting.md) ----
export const supportingApi = {
  /** GET /api/supporting?status= -> { items: [relationship], total } (pending first) */
  list: (status) => api.get("/api/supporting", { params: { status } }),
  /** GET /api/supporting/faculty/search?q= (student) -> { items: [faculty + relationship, has_access, access_via, can_request], total, query } */
  searchFaculty: (q) => api.get("/api/supporting/faculty/search", { params: { q } }),
  /** POST /api/supporting/faculty/:facultyId/request (student) -> 201 { ok, id, relationship } (409 when pending/accepted) */
  requestFaculty: (facultyId) => api.post(`/api/supporting/faculty/${facultyId}/request`, {}),
  /** POST /api/supporting/:id/accept | /reject (the addressed party) -> { ok, status, relationship } */
  accept: (relId) => api.post(`/api/supporting/${relId}/accept`, {}),
  reject: (relId) => api.post(`/api/supporting/${relId}/reject`, {}),
};

// ---- admin console + research (implemented in lib/adminApi.js) ----
export { adminApi, researchApi, adminKeys } from "@/lib/adminApi";
