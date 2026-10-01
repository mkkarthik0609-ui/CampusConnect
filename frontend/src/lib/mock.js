/**
 * DEV-ONLY in-memory API used when the Flask/FastAPI backend is unavailable:  `npm run dev:mock`
 * (sets VITE_MOCK=1). main.jsx imports this behind `import.meta.env.DEV`, so it is tree-shaken from
 * production builds. It covers only the foundation endpoints (auth, account, academic tree, notifications).
 * Sign in with any of: student / faculty / admin (password: Passw0rd!).
 */

const USERS = {
  student: { id: 1, role: "STUDENT", full_name: "Ananya Rao", email: "ananya@college.edu", theme: "light", profile_picture_url: null, student_id: 3, faculty_id: null },
  faculty: { id: 2, role: "FACULTY", full_name: "Dr. Meera Iyer", email: "meera@college.edu", theme: "light", profile_picture_url: null, student_id: null, faculty_id: 5 },
  admin: { id: 3, role: "ADMIN", full_name: "Campus Admin", email: "admin@college.edu", theme: "light", profile_picture_url: null, student_id: null, faculty_id: null },
};

const TREE = {
  branches: [
    {
      id: 1, name: "CSE",
      departments: [
        { id: 1, name: "AIML", years: [{ id: 1, name: "2nd Year", sections: [{ id: 1, name: "A" }, { id: 2, name: "B" }] }, { id: 2, name: "3rd Year", sections: [{ id: 3, name: "A" }, { id: 4, name: "B" }] }] },
        { id: 2, name: "Cyber Security", years: [{ id: 3, name: "1st Year", sections: [{ id: 5, name: "A" }] }] },
      ],
    },
    { id: 2, name: "ECE", departments: [{ id: 3, name: "VLSI", years: [{ id: 4, name: "4th Year", sections: [{ id: 6, name: "A" }] }] }] },
  ],
};

let notifications = [
  { id: 3, type: "MEETING_ACCEPTED", title: "Meeting accepted", message: "Dr. Meera Iyer accepted your request for Thursday, 11:30.", related_entity_type: "meeting", related_entity_id: 9, is_read: false, created_at: new Date(Date.now() - 12 * 60_000).toISOString().slice(0, 19).replace("T", " ") },
  { id: 2, type: "NEW_MESSAGE", title: "New message", message: "You have a new message in Mentor-Connect.", related_entity_type: "chat", related_entity_id: 4, is_read: false, created_at: new Date(Date.now() - 3 * 3600_000).toISOString().slice(0, 19).replace("T", " ") },
  { id: 1, type: "PERMISSION_RESPONDED", title: "Profile change approved", message: "Your phone number change was approved.", related_entity_type: "permission", related_entity_id: 2, is_read: true, created_at: "2026-09-20 08:15:00" },
];

let current = (() => { try { return JSON.parse(sessionStorage.getItem("cc-mock-user")); } catch { return null; } })();
const save = () => { try { sessionStorage.setItem("cc-mock-user", JSON.stringify(current)); } catch { /* ignore */ } };
let csrf = "mock-csrf-1";

const json = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const err = (status, code, message, fields) => json(status, { error: { code, message, ...(fields ? { fields } : {}) } });
const session = () => ({
  authenticated: !!current,
  user: current,
  csrf_token: csrf,
  unread_notifications: current ? notifications.filter((n) => !n.is_read).length : 0,
  unread_messages: current ? 2 : 0,
});

export function installMock() {
  const realFetch = window.fetch.bind(window);
  console.info("[mock] API mock active. Sign in as student / faculty / admin with Passw0rd!");

  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, window.location.origin);
    if (!url.pathname.startsWith("/api/")) return realFetch(input, init);
    const method = (init.method || "GET").toUpperCase();
    const path = url.pathname;
    await new Promise((r) => setTimeout(r, 180));
    let body = {};
    try { body = init.body && typeof init.body === "string" ? JSON.parse(init.body) : {}; } catch { /* ignore */ }

    if (method !== "GET" && init.headers?.["X-CSRFToken"] !== csrf) return err(400, "csrf_failed", "CSRF token missing or invalid.");

    if (path === "/api/auth/session") return json(200, session());
    if (path === "/api/meta") return json(200, { app: "Campus Connect" });
    if (path === "/api/academic/tree") return json(200, TREE);
    if (path === "/api/auth/faculty-departments") return json(200, { items: ["AIML", "Cyber Security", "VLSI"] });

    if (path === "/api/auth/login") {
      const key = String(body.identifier || "").toLowerCase();
      const user = USERS[key] || Object.values(USERS).find((u) => u.email === key);
      if (!user || body.password !== "Passw0rd!") return err(401, "invalid_credentials", "Invalid email or password.");
      current = { ...user };
      save();
      csrf = "mock-csrf-" + Math.random().toString(36).slice(2, 8);
      return json(200, { ok: true, message: "Welcome back!", user: current, csrf_token: csrf });
    }
    if (path === "/api/auth/logout") {
      current = null;
      save();
      csrf = "mock-csrf-" + Math.random().toString(36).slice(2, 8);
      return json(200, { ok: true, message: "You have been signed out.", csrf_token: csrf });
    }

    if (path === "/api/auth/captcha") {
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="84"><rect width="240" height="84" fill="#eef"/><text x="30" y="58" font-size="46" font-family="monospace" fill="#223">MOCK42</text></svg>`;
      return json(200, { captcha_id: "mock-captcha", image: "data:image/svg+xml;base64," + btoa(svg), expires_in_seconds: 300 });
    }
    const captchaFails = () => String(body.captcha_answer || "").toUpperCase() !== "MOCK42"
      && err(400, "validation_error", "Incorrect captcha. A new one has been loaded. (mock answer: MOCK42)", { captcha: "Incorrect captcha. A new one has been loaded. (mock answer: MOCK42)" });
    if (path === "/api/auth/signup/student") {
      const bad = captchaFails(); if (bad) return bad;
      if (!/^[A-Za-z0-9]{6,15}$/.test(body.usn || "")) return err(400, "validation_error", "USN must be 6-15 alphanumeric characters.", { usn: "USN must be 6-15 alphanumeric characters." });
      if (!/[A-Z]/.test(body.password) || !/[a-z]/.test(body.password) || !/\d/.test(body.password) || body.password.length < 8) return err(400, "validation_error", "Password rules.", { password: "Password must be at least 8 characters and include an uppercase letter, a lowercase letter and a digit." });
      return json(201, { ok: true, message: "Registration successful. Please sign in." });
    }
    if (path === "/api/auth/signup/faculty") {
      const bad = captchaFails(); if (bad) return bad;
      return json(201, { ok: true, message: "Registration successful. Please sign in." });
    }

    if (!current) return err(401, "unauthenticated", "Please sign in to continue.");

    if (path === "/api/account/theme") { current.theme = body.theme; save(); return json(200, { ok: true, theme: body.theme }); }
    if (path === "/api/account/password") {
      if (body.current_password !== "Passw0rd!") return err(400, "validation_error", "Your current password is incorrect.", { current_password: "Your current password is incorrect." });
      return json(200, { ok: true, message: "Your password has been changed." });
    }
    if (path === "/api/notifications") return json(200, { items: notifications, unread_count: notifications.filter((n) => !n.is_read).length });
    if (path === "/api/notifications/read-all") { notifications = notifications.map((n) => ({ ...n, is_read: true })); return json(200, { ok: true, unread_count: 0 }); }
    const m = path.match(/^\/api\/notifications\/(\d+)\/read$/);
    if (m) { notifications = notifications.map((n) => (n.id === Number(m[1]) ? { ...n, is_read: true } : n)); return json(200, { ok: true, unread_count: notifications.filter((n) => !n.is_read).length }); }

    return err(404, "not_found", `Mock has no endpoint for ${method} ${path}.`);
  };
}
