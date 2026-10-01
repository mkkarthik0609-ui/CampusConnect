/**
 * Admin console + research endpoints (docs/api/admin.md, academics.md, research.md).
 * Re-exported from endpoints.js as `adminApi` / `researchApi`; keys for react-query live in `adminKeys`.
 */
import { api } from "@/lib/api";

const A = "/api/admin";

export const adminKeys = {
  all: ["admin"],
  dashboard: ["admin", "dashboard"],
  academics: ["admin", "academics"],
  assignments: ["admin", "assignments"],
  requests: (status) => ["admin", "assignment-requests", status || "ALL"],
  requestsAll: ["admin", "assignment-requests"],
  classes: ["admin", "classes"],
  classDetail: (id) => ["admin", "classes", String(id)],
  students: ["admin", "students"],
  faculty: ["admin", "faculty"],
  meetings: (status) => ["admin", "meetings", status || "ALL"],
  chats: ["admin", "chats"],
  chat: (id) => ["admin", "chats", String(id)],
  permissions: ["admin", "permission-requests"],
  admins: ["admin", "admins"],
  research: ["research", "results"],
};

export const adminApi = {
  dashboard: () => api.get(`${A}/dashboard`),

  // ---- academic structure ----
  academics: () => api.get(`${A}/academics`),
  /** level: "branch" | "department" | "year" | "section" */
  addBranch: (name) => api.post(`${A}/academics/branches`, { name }),
  addDepartment: (branch_id, name) => api.post(`${A}/academics/departments`, { branch_id, name }),
  addYear: (department_id, name) => api.post(`${A}/academics/years`, { department_id, name }),
  addSections: (year_id, names) => api.post(`${A}/academics/sections`, { year_id, names }),
  setActive: (level, id, active) => api.post(`${A}/academics/${level}/${id}/active`, { active }),
  deleteNode: (level, id) => api.delete(`${A}/academics/${level}/${id}`),

  // ---- assignments ----
  assignments: () => api.get(`${A}/assignments`),
  assign: (faculty_id, section_id) => api.post(`${A}/assignments`, { faculty_id, section_id }),
  removeAssignment: (id) => api.delete(`${A}/assignments/${id}`),
  assignmentRequests: (status) => api.get(`${A}/assignment-requests`, { params: { status } }),
  decideAssignmentRequest: (id, decision) => api.post(`${A}/assignment-requests/${id}/decide`, { decision }),

  // ---- class directory ----
  classes: () => api.get(`${A}/classes`),
  classDetail: (sectionId) => api.get(`${A}/classes/${sectionId}`),

  // ---- people ----
  students: (params) => api.get(`${A}/students`, { params }),
  removeRegistration: (id) => api.post(`${A}/students/${id}/remove-registration`, {}),
  faculty: () => api.get(`${A}/faculty`),
  admins: () => api.get(`${A}/admins`),
  createAdmin: (body) => api.post(`${A}/admins`, body),

  // ---- oversight ----
  meetings: (status) => api.get(`${A}/meetings`, { params: { status } }),
  chats: () => api.get(`${A}/chats`),
  chat: (id) => api.get(`${A}/chats/${id}`),
  permissionRequests: () => api.get(`${A}/permission-requests`),
  decidePermission: (id, decision) => api.post(`${A}/permission-requests/${id}/decide`, { decision }),
};

export const researchApi = {
  /** GET /api/research/results -> committed study (see research.md) */
  results: () => api.get("/api/research/results"),
  /** POST /api/research/run { seeds, load, num_requests? } -> metrics table + timeline */
  run: (body) => api.post("/api/research/run", body),
};
