// @ts-check
/* global Buffer, process */
import { test, expect } from "@playwright/test";

const ADMIN = { email: "mkkarthik0609@gmail.com", password: "E2e#Admin0wner1" };
const FACULTY = { email: "e2e.faculty@college.edu", password: "E2e#Passw0rd1" };
const STUDENT1 = { email: "e2e.student1@college.edu", password: "E2e#Passw0rd1" };
const STUDENT2 = { email: "e2e.student2@college.edu", password: "E2e#Passw0rd1" };
const ADMIN_ID = "campus-connect-123";
const NEW_ADMIN = { email: `second.admin.${Date.now()}@college.edu` };

// 1x1 PNG
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

/** Log in through the real login form of `path` (works for /login and /admin-login). */
async function uiLogin(page, path, user) {
  await page.goto(path);
  await page.getByLabel(/^(Email|Email, Faculty ID or USN)/).first().fill(user.email);
  await page.getByLabel("Password", { exact: false }).first().fill(user.password);
  await page.getByRole("button", { name: /sign in|log in|login|open admin portal/i }).first().click();
}

/** Admin sign-in through the real form: e-mail + shared admin ID (no password). */
async function uiAdminLogin(page, email, adminId = ADMIN_ID) {
  await page.goto("/admin-login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Admin ID").fill(adminId);
  await page.getByRole("button", { name: /open admin portal/i }).click();
}

/** API client that is signed in (cookies kept in the context's request jar). */
async function apiLogin(request, user, url = "/api/auth/login") {
  const session = await (await request.get("/api/auth/session")).json();
  const res = await request.post(url, {
    headers: { "X-CSRFToken": session.csrf_token },
    data: url.endsWith("admin-login")
      ? { identifier: user.email, admin_id: ADMIN_ID }
      : { identifier: user.email, password: user.password },
  });
  expect(res.status(), `login ${user.email}`).toBe(200);
  const body = await res.json();
  return body.csrf_token;
}

test("landing page and SPA deep links survive a browser refresh", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Campus ?Connect/i);
  for (const path of ["/login", "/admin-login", "/signup/student", "/signup/faculty"]) {
    await page.goto(path);
    await page.reload();
    await expect(page.locator("body")).not.toContainText(/not found|cannot get/i);
    await expect(page.locator("#root")).not.toBeEmpty();
  }
});

test("admin sign-in is email + admin ID (no password, no passkeys)", async ({ page }) => {
  await page.goto("/admin-login");
  await expect(page.locator("body")).not.toContainText(/passkey|webauthn|biometric|security key/i);
  await expect(page.getByLabel("Password")).toHaveCount(0);
  await uiAdminLogin(page, ADMIN.email);
  await expect(page).toHaveURL(/\/admin\/dashboard/);
  await page.goto("/admin/admins");
  await expect(page.locator("body")).not.toContainText(/passkey/i);
  await expect(page.getByText(/invite/i).first()).toBeVisible();
});

test("wrong admin ID is rejected with a generic message", async ({ page }) => {
  await uiAdminLogin(page, ADMIN.email, "definitely-wrong");
  await expect(page).toHaveURL(/admin-login/);
  await expect(page.locator("body")).toContainText(/invalid|incorrect|wrong/i);
});

test("add admin: primary adds an e-mail -> that admin signs in with the admin ID -> cannot add admins", async ({ browser, request }) => {
  const csrf = await apiLogin(request, ADMIN, "/api/auth/admin-login");
  const added = await request.post("/api/admin/admin-invitations", {
    headers: { "X-CSRFToken": csrf },
    data: { email: NEW_ADMIN.email, full_name: "Second Admin" },
  });
  expect(added.status()).toBe(201);
  const body = await added.json();
  // Nothing is e-mailed and there is no link: the primary admin tells them the e-mail + admin ID.
  expect(body.email_delivery).toBe("NONE");
  expect(body.invite_link).toBeNull();

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await uiAdminLogin(page, NEW_ADMIN.email);
  await expect(page).toHaveURL(/\/admin\/dashboard/);
  // a second admin may not appoint admins
  await page.goto("/admin/admins");
  await expect(page.getByRole("button", { name: /send invitation|invite/i })).toHaveCount(0);

  // an e-mail the primary admin never added is refused even with the right ID
  await ctx.close();
  const ctx2 = await browser.newContext();
  const stranger = await ctx2.newPage();
  await uiAdminLogin(stranger, `nobody.${Date.now()}@college.edu`);
  await expect(stranger).toHaveURL(/admin-login/);
  await expect(stranger.locator("body")).toContainText(/invalid/i);
  await ctx2.close();
});

test("student and faculty sign in and reach their dashboards", async ({ browser }) => {
  for (const [user, re] of [[STUDENT1, /\/student\/dashboard/], [FACULTY, /\/faculty\/dashboard/]]) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await uiLogin(page, "/login", user);
    await expect(page).toHaveURL(re);
    await page.reload();
    await expect(page).toHaveURL(re); // session survives a refresh
    await ctx.close();
  }
});

test("route guards: anonymous and wrong-role access is redirected", async ({ page, browser }) => {
  await page.goto("/admin/dashboard");
  await expect(page).toHaveURL(/login/);
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await uiLogin(p, "/login", STUDENT1);
  await expect(p).toHaveURL(/\/student\/dashboard/);
  await p.goto("/admin/dashboard");
  await expect(p.getByRole("heading", { name: /isn't open to you/i })).toBeVisible(); // friendly 403 page, no admin data
  await expect(p.locator("body")).not.toContainText(/E2E Faculty|invite administrator/i);
  await ctx.close();
});

test("private attachments: only the two chat participants (and admins) can open them", async ({ playwright }) => {
  const base = process.env.E2E_BASE_URL || "http://127.0.0.1:8765";
  const mk = async () => playwright.request.newContext({ baseURL: base });
  const student = await mk();
  const faculty = await mk();
  const other = await mk();
  const anon = await mk();
  const sCsrf = await apiLogin(student, STUDENT1);
  await apiLogin(faculty, FACULTY);
  await apiLogin(other, STUDENT2);

  const find = await (await student.get("/api/supporting/faculty/search?q=E2E")).json();
  const fac = (find.items || find.faculty || [])[0];
  expect(fac, "faculty visible to the student").toBeTruthy();
  const chat = await student.post("/api/chat/open", {
    headers: { "X-CSRFToken": sCsrf },
    data: { faculty_id: fac.id },
  });
  expect([200, 201]).toContain(chat.status());
  const chatBody = await chat.json();
  const chatId = chatBody.chat_id ?? chatBody.id;

  const sent = await student.post(`/api/chat/${chatId}/messages`, {
    headers: { "X-CSRFToken": sCsrf },
    multipart: { attachment: { name: "pic.png", mimeType: "image/png", buffer: PNG }, message_text: "see attached" },
  });
  expect(sent.status(), await sent.text()).toBe(201);
  const url = (await sent.json()).item.attachment.url;

  expect((await student.get(url)).status()).toBe(200);
  expect((await faculty.get(url)).status()).toBe(200);
  expect((await other.get(url)).status()).toBe(403);
  expect((await anon.get(url)).status()).toBe(401);

  // fake image content is refused and stores nothing
  const bad = await student.post(`/api/chat/${chatId}/messages`, {
    headers: { "X-CSRFToken": sCsrf },
    multipart: { attachment: { name: "fake.png", mimeType: "image/png", buffer: Buffer.from("not really a png") } },
  });
  expect(bad.status()).toBe(400);
  for (const c of [student, faculty, other, anon]) await c.dispose();
});

test("error states do not leak internals", async ({ request }) => {
  for (const [method, url] of [["get", "/api/does/not/exist"], ["get", "/api/admin/dashboard"], ["post", "/api/auth/login"]]) {
    const res = await request[method](url, method === "post" ? { data: "not json", headers: { "Content-Type": "application/json" } } : {});
    const text = await res.text();
    expect(text).not.toMatch(/Traceback|psycopg|postgres|File "|\.py"/);
    expect(res.status()).toBeGreaterThanOrEqual(400);
  }
});

for (const path of ["/", "/login", "/admin-login", "/signup/student"]) {
  test(`mobile 390px: ${path} has no horizontal overflow`, async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await ctx.newPage();
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await ctx.close();
  });
}
