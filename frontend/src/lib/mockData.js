/**
 * DEV-ONLY fixtures for the non-chat endpoints of the mock API (see mock.js): dashboards, classes, meetings,
 * profile, people search, supporting requests, admin console and research. Shapes follow docs/api/*.md.
 */
const cls = (section_id, branch, department, year, section) => ({ section_id, branch, department, year, section, label: `${branch} → ${department} → ${year} → ${section}` });
const C7 = cls(3, "CSE", "AIML", "3rd Year", "A");
const C8 = cls(4, "CSE", "AIML", "3rd Year", "B");
const C9 = cls(1, "CSE", "AIML", "2nd Year", "A");
const C10 = cls(5, "CSE", "Cyber Security", "1st Year", "A");
const ts = (hoursAgo) => new Date(Date.now() - hoursAgo * 3600_000).toISOString().slice(0, 19).replace("T", " ");

const FAC = [
  { id: 5, user_id: 2, faculty_code: "FAC001", department: "AIML", full_name: "Dr. Meera Iyer", profile_picture_url: null },
  { id: 6, user_id: 4, faculty_code: "FAC002", department: "AIML", full_name: "Prof. Rahul Verma", profile_picture_url: null },
  { id: 7, user_id: 8, faculty_code: "FAC003", department: "Cyber Security", full_name: "Dr. Subramaniam Venkataraghavan Natarajan", profile_picture_url: null },
];
const STU = [
  { id: 3, user_id: 1, usn: "1AB21CS014", full_name: "Ananya Rao", profile_picture_url: null, class: C7 },
  { id: 7, user_id: 6, usn: "1AB21CS031", full_name: "Karthik N", profile_picture_url: null, class: C7 },
  { id: 8, user_id: 9, usn: "1AB22CS101", full_name: "Priyadarshini Venkateswaran Subramanian", profile_picture_url: null, class: C9 },
  { id: 9, user_id: 10, usn: "1AB23CY007", full_name: "Mohammed Faizan", profile_picture_url: null, class: C10 },
];

const studentObj = {
  id: 3, user_id: 1, usn: "1AB21CS014", full_name: "Ananya Rao", email: "ananya@college.edu", college_email: "ananya@college.edu",
  personal_email: "ananya.rao@example.com", phone: "9876543210", branch: "CSE", department: "AIML", year: "3rd Year", section: "A",
  class: C7, theme: "light", profile_picture_url: null,
};

const meeting = (id, status, reason, who, extra = {}) => ({
  id, status, reason, student_message: "Please review my project abstract and suggest improvements before the internal review.",
  faculty_response: status === "ACCEPTED" ? "Come to my cabin." : status === "REJECTED" ? "Not available this week." : null,
  meeting_time_text: status === "ACCEPTED" || status === "COMPLETED" ? "Thursday, 11:30 AM" : null,
  requested_at: ts(id * 7), responded_at: status === "PENDING" ? null : ts(id * 6), completed_at: status === "COMPLETED" ? ts(id * 5) : null, completed_by: status === "COMPLETED" ? "FACULTY" : null,
  cancelled_at: status === "CANCELLED" ? ts(id * 5) : null, cancelled_by: status === "CANCELLED" ? "STUDENT" : null, cancellation_reason: status === "CANCELLED" ? "Clash with a lab session" : null,
  student: STU[who.s], faculty: FAC[who.f],
  can_respond: false, can_cancel: status === "PENDING" || status === "ACCEPTED", can_complete: status === "ACCEPTED", ...extra,
});
const MEETINGS = [
  meeting(1, "PENDING", "Project review", { s: 0, f: 0 }),
  meeting(2, "ACCEPTED", "Doubt in dynamic programming", { s: 0, f: 0 }),
  meeting(3, "COMPLETED", "Internship letter", { s: 0, f: 1 }),
  meeting(4, "REJECTED", "Lab record signature", { s: 0, f: 1 }),
  meeting(5, "CANCELLED", "Career guidance and higher studies planning discussion for the final year", { s: 0, f: 2 }),
  meeting(6, "PENDING", "Semester attendance shortage", { s: 1, f: 0 }),
];
const forViewer = (m, user) => {
  const student = user.role === "STUDENT";
  const counterpart = student ? { ...m.faculty, role: "FACULTY" } : { ...m.student, role: "STUDENT" };
  return {
    ...m, counterpart, counterpart_name: counterpart.full_name, counterpart_code: student ? m.faculty.faculty_code : m.student.usn,
    can_respond: user.role === "FACULTY" && m.status === "PENDING",
  };
};

const rel = (id, status, requested_by, direction, s, f) => ({
  id, status, requested_by, direction, can_respond: status === "PENDING" && direction === "incoming", created_at: ts(30), updated_at: ts(30),
  student: STU[s], faculty: FAC[f], counterpart: direction === "incoming" && requested_by === "FACULTY" ? { ...FAC[f], role: "FACULTY" } : { ...STU[s], role: "STUDENT" },
});

const adminClasses = [
  { ...C9, is_active: true, student_count: 58, faculty_count: 1, faculty: [{ id: 5, assignment_id: 1, faculty_code: "FAC001", full_name: "Dr. Meera Iyer", profile_picture_url: null }] },
  { ...C7, is_active: true, student_count: 62, faculty_count: 2, faculty: [{ id: 5, assignment_id: 2, faculty_code: "FAC001", full_name: "Dr. Meera Iyer", profile_picture_url: null }, { id: 6, assignment_id: 3, faculty_code: "FAC002", full_name: "Prof. Rahul Verma", profile_picture_url: null }] },
  { ...C8, is_active: true, student_count: 0, faculty_count: 0, faculty: [] },
  { ...C10, is_active: false, student_count: 12, faculty_count: 1, faculty: [{ id: 7, assignment_id: 4, faculty_code: "FAC003", full_name: "Dr. Subramaniam Venkataraghavan Natarajan", profile_picture_url: null }] },
];
const adminStudent = (s, i) => ({
  id: s.id, user_id: s.user_id, full_name: s.full_name, usn: s.usn, email: `${s.usn.toLowerCase()}@college.edu`, personal_email: `${s.usn.toLowerCase()}@example.com`,
  phone: "98765432" + (10 + i), profile_picture_url: null, class: s.class, legacy_class: null, is_active: i !== 3, is_removed: i === 3, is_unmapped: false,
  can_remove_registration: i !== 3, registered_at: ts(200 + i * 20), last_login_at: i === 3 ? null : ts(i + 1),
});
const adminFaculty = FAC.map((f, i) => ({
  id: f.id, user_id: f.user_id, faculty_code: f.faculty_code, full_name: f.full_name, email: `${f.faculty_code.toLowerCase()}@college.edu`, professional_email: `${f.faculty_code.toLowerCase()}@college.edu`,
  department: f.department, profile_picture_url: null, is_active: true, subjects: ["DSA", "Operating Systems", "Machine Learning"].slice(0, i + 1),
  assignments: adminClasses.filter((c) => c.faculty.some((x) => x.id === f.id)).map((c) => ({ ...c, assignment_id: c.faculty.find((x) => x.id === f.id).assignment_id, is_active: true, class_active: c.is_active, can_remove: true, assigned_at: ts(300) })),
  pending_request_count: i === 1 ? 1 : 0, registered_at: ts(500), last_login_at: ts(3),
}));
const assignRequests = [
  { id: 1, status: "PENDING", note: "I teach DSA to this section.", created_at: ts(20), reviewed_at: null, reviewed_by: null, faculty: FAC[1], class: C8, class_active: true, can_decide: true },
  { id: 2, status: "APPROVED", note: "", created_at: ts(120), reviewed_at: ts(100), reviewed_by: 3, faculty: FAC[0], class: C7, class_active: true, can_decide: false },
  { id: 3, status: "REJECTED", note: "Wrong section", created_at: ts(220), reviewed_at: ts(200), reviewed_by: 3, faculty: FAC[2], class: C10, class_active: false, can_decide: false },
];
const sec = (id, name, n, a) => ({ id, name, is_active: true, student_count: n, assignment_count: a, can_delete: n === 0 && a === 0 });
const academics = {
  branches: [
    { id: 1, name: "CSE", is_active: true, student_count: 132, assignment_count: 4, can_delete: false, departments: [
      { id: 1, name: "AIML", is_active: true, student_count: 120, assignment_count: 3, can_delete: false, years: [
        { id: 1, name: "2nd Year", is_active: true, student_count: 58, assignment_count: 1, can_delete: false, sections: [sec(1, "A", 58, 1), sec(2, "B", 0, 0)] },
        { id: 2, name: "3rd Year", is_active: true, student_count: 62, assignment_count: 2, can_delete: false, sections: [sec(3, "A", 62, 2), sec(4, "B", 0, 0)] }] },
      { id: 2, name: "Cyber Security", is_active: false, student_count: 12, assignment_count: 1, can_delete: false, years: [
        { id: 3, name: "1st Year", is_active: false, student_count: 12, assignment_count: 1, can_delete: false, sections: [{ ...sec(5, "A", 12, 1), is_active: false }] }] }] },
    { id: 2, name: "ECE", is_active: true, student_count: 0, assignment_count: 0, can_delete: true, departments: [] },
  ],
};
const chatsFacultyName = "Dr. Meera Iyer";
const permissionRequests = [
  { id: 1, request_type: "FACULTY_PROFILE_CHANGE", status: "PENDING", requester: { user_id: 4, full_name: "Prof. Rahul Verma", role: "FACULTY", usn: null, faculty_code: "FAC002", profile_picture_url: null }, approver: { user_id: 3, full_name: "Campus Admin" }, requested_changes: { department: "Cyber Security", professional_email: "rahul.v@college.edu" }, reason: "Moved departments this semester.", created_at: ts(10), reviewed_at: null, can_decide: true },
  { id: 2, request_type: "STUDENT_PROFILE_CHANGE", status: "PENDING", requester: { user_id: 1, full_name: "Ananya Rao", role: "STUDENT", usn: "1AB21CS014", faculty_code: null, profile_picture_url: null }, approver: { user_id: 2, full_name: chatsFacultyName }, requested_changes: { phone: "9876500000" }, reason: "Changed SIM", created_at: ts(30), reviewed_at: null, can_decide: false },
  { id: 3, request_type: "FACULTY_PROFILE_CHANGE", status: "APPROVED", requester: { user_id: 2, full_name: chatsFacultyName, role: "FACULTY", usn: null, faculty_code: "FAC001", profile_picture_url: null }, approver: { user_id: 3, full_name: "Campus Admin" }, requested_changes: { department: "AIML" }, reason: "Correction", created_at: ts(100), reviewed_at: ts(90), can_decide: false },
];
const stuPerm = (id, status) => ({ id, request_type: "STUDENT_PROFILE_CHANGE", status, requested_changes: { phone: "9876500000" }, reason: "Changed SIM", created_at: ts(30), reviewed_at: status === "PENDING" ? null : ts(20), requester_name: "Ananya Rao", student: STU[0] });
const ADMINS = [
  { id: 3, full_name: "Campus Admin", email: "admin@college.edu", profile_picture_url: null, is_active: true, is_you: true, is_primary: true, passkey_count: 1, created_at: ts(2000), last_login_at: ts(1) },
  { id: 11, full_name: "Second Admin", email: "second@college.edu", profile_picture_url: null, is_active: true, is_you: false, is_primary: false, passkey_count: 0, created_at: ts(900), last_login_at: null },
  { id: 12, full_name: "Retired Admin", email: "retired@college.edu", profile_picture_url: null, is_active: false, is_you: false, is_primary: false, passkey_count: 0, created_at: ts(1500), last_login_at: ts(600) },
];

const cell = (mean, sd, n = 30) => ({ mean, sd, ci95: sd * 0.37, n });
const imp = (c, b, pct, verdict = "better") => ({ candidate_mean: c, baseline_mean: b, pct_improvement: pct, paired_diff_mean: b - c, paired_diff_ci95: 0.01 * b, verdict });
const METRICS = {
  avg_wait_min: { label: "Average waiting time", unit: "min", better: "lower", headline: true },
  p90_wait_min: { label: "Waiting time, slowest 10% (p90)", unit: "min", better: "lower", headline: true },
  served_meetings: { label: "Meetings held per week", unit: "count", better: "higher", headline: true },
  success_rate: { label: "Success rate (held / requested)", unit: "fraction", better: "higher", headline: true },
  faculty_idle_min: { label: "Faculty idle time per week", unit: "min", better: "lower", headline: true },
  wasted_min: { label: "Wasted booked minutes", unit: "min", better: "lower", headline: true },
  schedule_conflicts: { label: "Schedule conflicts (class clashes)", unit: "count", better: "lower", headline: true },
  cancellations: { label: "Cancellations (of booked)", unit: "count", better: null, headline: true },
  no_shows: { label: "No-shows (of booked)", unit: "count", better: null, headline: true },
  fairness_jain: { label: "Fairness (Jain index)", unit: "index", better: "higher", headline: true },
  urgent_success_rate: { label: "Urgent requests held", unit: "fraction", better: "higher", headline: true },
};
const level = (n, k) => {
  const row = (m) => ({
    avg_wait_min: cell(299 * k * m[0], 25), p90_wait_min: cell(610 * k * m[0], 40), served_meetings: cell(n * 0.57 * m[1], 8), success_rate: cell(0.57 * m[1], 0.03),
    faculty_idle_min: cell(900 * m[2], 60), wasted_min: cell(420 * m[2], 30), schedule_conflicts: cell(m[3], 1.2), cancellations: cell(14, 3), no_shows: cell(9, 2),
    fairness_jain: cell(0.7 + (m[1] - 1) * 0.2, 0.02), urgent_success_rate: cell(0.5 * m[1], 0.05),
  });
  const table = { fcfs: row([1, 1, 1, 18]), rule_based: row([0.9, 1.12, 0.82, 0]), intelligent: row([0.92, 1.14, 0.8, 0]) };
  const mk = (a, b) => ({
    avg_wait_min: imp(a.avg_wait_min.mean, b.avg_wait_min.mean, (1 - a.avg_wait_min.mean / b.avg_wait_min.mean) * 100, a.avg_wait_min.mean > b.avg_wait_min.mean ? "worse" : "better"),
    p90_wait_min: imp(a.p90_wait_min.mean, b.p90_wait_min.mean, (1 - a.p90_wait_min.mean / b.p90_wait_min.mean) * 100),
    served_meetings: imp(a.served_meetings.mean, b.served_meetings.mean, (a.served_meetings.mean / b.served_meetings.mean - 1) * 100),
    success_rate: imp(a.success_rate.mean, b.success_rate.mean, (a.success_rate.mean / b.success_rate.mean - 1) * 100),
    faculty_idle_min: imp(a.faculty_idle_min.mean, b.faculty_idle_min.mean, (1 - a.faculty_idle_min.mean / b.faculty_idle_min.mean) * 100),
    wasted_min: imp(a.wasted_min.mean, b.wasted_min.mean, (1 - a.wasted_min.mean / b.wasted_min.mean) * 100),
    schedule_conflicts: imp(a.schedule_conflicts.mean, b.schedule_conflicts.mean, 100),
    cancellations: imp(14, 14, 0, "informational"), no_shows: imp(9, 9, 0, "informational"),
    fairness_jain: imp(a.fairness_jain.mean, b.fairness_jain.mean, 3), urgent_success_rate: imp(a.urgent_success_rate.mean, b.urgent_success_rate.mean, 12),
  });
  return {
    num_requests: n, dataset: { requests: n, offered_load: 0.88 }, table,
    improvement: { intelligent_vs_fcfs: mk(table.intelligent, table.fcfs), intelligent_vs_rule_based: mk(table.intelligent, table.rule_based), rule_based_vs_fcfs: mk(table.rule_based, table.fcfs) },
    conclusions: ["Waiting time: intelligent scheduling waits less than FCFS.", "Meetings held: more meetings are held per week."],
    weakest_metric: { metric: "avg_wait_min", pct_improvement: -1.8, verdict: "worse" },
  };
};
const research = {
  question: "Can data-driven scheduling reduce student waiting time and improve faculty-student meeting efficiency compared with the current/manual scheduling approach?",
  config: { world: { days: 5, day_minutes: 480, num_faculty: 12, num_students: 150, loads: { low: 240, medium: 360, high: 480 } }, eval_seeds: Array.from({ length: 30 }, (_, i) => i + 1) },
  methods: { fcfs: { label: "FCFS / manual" }, rule_based: { label: "Rule-based" }, intelligent: { label: "Intelligent (proposed)" } },
  metrics: METRICS,
  levels: { low: level(240, 0.6), medium: level(360, 1), high: level(480, 1.5) },
  sensitivity: { load: "medium", variants: {} },
};

const NODATA = Symbol("nodata");
export function handleDataMock({ method, path, url, body, user, json, err }) {
  const role = user.role;
  const q = (k) => url.searchParams.get(k);
  const bad = (r) => (r === role ? null : err(403, "forbidden", "You do not have permission to do that."));
  const mine = MEETINGS.filter((m) => (role === "STUDENT" ? m.student.id === 3 : role === "FACULTY" ? m.faculty.id === 5 : true));
  const statusFilter = q("status") ? q("status").toUpperCase().split(",") : null;
  const meetingRows = (rows) => (statusFilter ? rows.filter((m) => statusFilter.includes(m.status)) : rows);

  if (path === "/api/student/dashboard") {
    return bad("STUDENT") || json(200, {
      student: studentObj, assigned_faculty: [FAC[0], FAC[1]], supporting_faculty: [FAC[2]],
      pending_supporting_requests: [rel(1, "PENDING", "FACULTY", "incoming", 0, 1)],
      recent_meetings: mine.slice(0, 5).map((m) => forViewer(m, user)),
      counts: { assigned_faculty: 2, supporting_faculty: 1, pending_supporting_requests: 1, meetings_total: mine.length, meetings_pending: 1, meetings_accepted: 1 },
    });
  }
  if (path === "/api/student/profile") return bad("STUDENT") || json(200, { student: studentObj, assigned_faculty: [FAC[0], FAC[1]], permission_requests: [{ id: 1, request_type: "STUDENT_PROFILE_CHANGE", requested_changes: { phone: "9876500000" }, reason: "Changed SIM", status: "PENDING", created_at: ts(30), reviewed_at: null }, { id: 2, request_type: "STUDENT_PROFILE_CHANGE", requested_changes: { personal_email: "new@example.com" }, reason: "Old address closed", status: "APPROVED", created_at: ts(300), reviewed_at: ts(280) }] });

  if (path === "/api/faculty/dashboard") {
    return bad("FACULTY") || json(200, {
      profile: { ...FAC[0], email: "meera@college.edu", professional_email: "meera@college.edu", theme: "light" }, subjects: ["DSA", "Operating Systems", "Machine Learning"],
      classes: [{ ...C7, assignment_id: 1, assigned_at: ts(300), student_count: 62 }, { ...C9, assignment_id: 2, assigned_at: ts(300), student_count: 58 }],
      pending_class_requests: [{ id: 1, section_id: 4, status: "PENDING", note: "I teach this section", created_at: ts(20), reviewed_at: null, class: C8 }],
      supporting_students: [STU[2]], pending_supporting_requests: [{ id: 2, created_at: ts(12), student: STU[3] }],
      recent_meetings: mine.slice(0, 5).map((m) => forViewer(m, user)), pending_permission_requests: [stuPerm(1, "PENDING")],
      counts: { classes: 2, pending_class_requests: 1, supporting_students: 1, pending_supporting_requests: 1, pending_permission_requests: 1, meetings_pending: 2 },
    });
  }
  if (path === "/api/faculty/profile") return bad("FACULTY") || json(200, { profile: { ...FAC[0], email: "meera@college.edu", professional_email: "meera@college.edu", theme: "light" }, subjects: ["DSA", "Operating Systems", "Machine Learning"], classes: [{ ...C7, assignment_id: 1, assigned_at: ts(300), student_count: 62 }], change_requests: [{ id: 2, request_type: "FACULTY_PROFILE_CHANGE", status: "PENDING", requested_changes: { department: "Cyber Security" }, reason: "Moved departments", created_at: ts(30), reviewed_at: null }], departments: ["AIML", "Cyber Security", "VLSI"] });
  if (path === "/api/faculty/classes") return bad("FACULTY") || json(200, { assignments: [{ ...C7, assignment_id: 1, assigned_at: ts(300), student_count: 62 }, { ...C9, assignment_id: 2, assigned_at: ts(300), student_count: 58 }], requests: [{ id: 1, section_id: 4, status: "PENDING", note: "I teach this section", created_at: ts(20), reviewed_at: null, class: C8 }, { id: 2, section_id: 5, status: "REJECTED", note: null, created_at: ts(200), reviewed_at: ts(190), class: C10 }] });
  let m = path.match(/^\/api\/faculty\/classes\/(\d+)$/);
  if (m) return bad("FACULTY") || json(200, { class: { ...C7, student_count: 4, assignment_id: 1 }, students: STU.map((s) => ({ id: s.id, usn: s.usn, full_name: s.full_name, phone: "9999999999", college_email: `${s.usn.toLowerCase()}@college.edu`, profile_picture_url: null })), co_faculty: [{ ...FAC[0], is_me: true }, { ...FAC[1], is_me: false }] });
  if (path === "/api/faculty/permission-requests") return bad("FACULTY") || json(200, { items: [stuPerm(1, "PENDING")], total: 1 });
  if (path === "/api/supporting/students/search") { const s = (q("q") || "").toLowerCase(); const items = s ? STU.filter((x) => (x.full_name + x.usn).toLowerCase().includes(s)).map((x, i) => ({ ...x, relationship: i === 2 ? { id: 3, status: "ACCEPTED", requested_by: "FACULTY" } : null, can_request: i !== 2 })) : []; return json(200, { items, total: items.length, query: q("q") || "" }); }
  if (path === "/api/supporting/faculty/search") { const s = (q("q") || "").toLowerCase(); const items = s ? FAC.filter((x) => (x.full_name + x.faculty_code).toLowerCase().includes(s)).map((x, i) => ({ ...x, relationship: i === 1 ? { id: 1, status: "PENDING", requested_by: "STUDENT" } : null, has_access: i === 0, access_via: i === 0 ? "class" : null, can_request: i === 2 })) : []; return json(200, { items, total: items.length, query: q("q") || "" }); }
  if (path === "/api/supporting") return json(200, { items: [rel(1, "PENDING", "FACULTY", "incoming", 0, 1), rel(2, "ACCEPTED", "STUDENT", "outgoing", 0, 2)], total: 2 });
  if (/^\/api\/supporting\/(faculty|students)\/\d+\/request$/.test(path) || /^\/api\/supporting\/\d+\/(accept|reject)$/.test(path)) return json(200, { ok: true, message: "Done.", id: 1, status: "ACCEPTED", relationship: rel(1, "ACCEPTED", "FACULTY", "incoming", 0, 1) });

  if (path === "/api/meetings" && method === "GET") { const rows = meetingRows(mine).map((x) => forViewer(x, user)); return json(200, { items: rows, total: rows.length }); }
  if (path === "/api/meetings" && method === "POST") return json(201, { ok: true, message: "Meeting request sent.", id: 99, meeting: forViewer(MEETINGS[0], user) });
  m = path.match(/^\/api\/meetings\/(\d+)\/(respond|cancel|complete)$/);
  if (m) return json(200, { ok: true, message: "Done.", status: "ACCEPTED", meeting: forViewer(MEETINGS[0], user) });

  if (path.startsWith("/api/admin/") && role === "ADMIN") {
    if (path === "/api/admin/dashboard") return json(200, { stats: { student_count: 132, removed_student_count: 3, unmapped_student_count: 1, faculty_count: 14, admin_count: 3, meeting_count: 87, pending_permission_count: 2, pending_assignment_count: 1, class_count: 72 } });
    if (path === "/api/admin/academics") return json(200, academics);
    if (path === "/api/admin/assignments") return json(200, { items: FAC.map((f, i) => ({ faculty_id: f.id, faculty_code: f.faculty_code, full_name: f.full_name, department: f.department, profile_picture_url: null, assignments: adminFaculty[i].assignments, pending_requests: i === 1 ? [assignRequests[0]] : [] })), total: 3, pending_count: 1 });
    if (path === "/api/admin/assignment-requests") { const rows = statusFilter ? assignRequests.filter((r) => statusFilter.includes(r.status)) : assignRequests; return json(200, { items: rows, total: rows.length, pending_count: 1 }); }
    if (path === "/api/admin/classes") return json(200, { items: adminClasses, total: adminClasses.length });
    if ((m = path.match(/^\/api\/admin\/classes\/(\d+)$/))) { const c = adminClasses.find((x) => x.section_id === Number(m[1])) || adminClasses[1]; return json(200, { class: c, faculty: c.faculty, students: STU.map(adminStudent) }); }
    if (path === "/api/admin/students") { const rows = STU.map(adminStudent); return json(200, { items: rows, total: rows.length }); }
    if (path === "/api/admin/faculty") return json(200, { items: adminFaculty, total: adminFaculty.length });
    if (path === "/api/admin/meetings") { const rows = meetingRows(MEETINGS); return json(200, { items: rows, total: rows.length }); }
    if (path === "/api/admin/permission-requests") return json(200, { items: permissionRequests, total: 3, pending: 2 });
    if (path === "/api/admin/admins") return json(200, { items: ADMINS, total: ADMINS.length });
    if (path === "/api/admin/passkeys") return json(200, { items: [{ id: 1, label: "Work laptop", transports: ["internal"], created_at: ts(500), last_used_at: ts(2) }], total: 1 });
    if (method !== "GET") return json(200, { ok: true, message: "Done.", temporary_password: "Temp-4821-xk", admin: ADMINS[1] });
  }
  if (path === "/api/research/results" && role === "ADMIN") return json(200, research);
  return NODATA;
}
export { NODATA };
