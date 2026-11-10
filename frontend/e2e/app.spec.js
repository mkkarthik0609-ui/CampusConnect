// @ts-check
/* global Buffer, process */
import { test, expect } from "@playwright/test";

const ADMIN = { email: "mkkarthik0609@gmail.com", password: "E2e#Admin0wner1" };
const FACULTY = { email: "e2e.faculty@college.edu", password: "E2e#Passw0rd1" };
const STUDENT1 = { email: "e2e.student1@college.edu", password: "E2e#Passw0rd1" };
const STUDENT2 = { email: "e2e.student2@college.edu", password: "E2e#Passw0rd1" };
const NEW_ADMIN = { email: `second.admin.${Date.now()}@college.edu`, password: "Second#Adm1npass" };

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

/** API client that is signed in (cookies kept in the context's request jar). */
async function apiLogin(request, user, url = "/api/auth/login") {
  const session = await (await request.get("/api/auth/session")).json();
  const res = await request.post(url, {
    headers: { "X-CSRFToken": session.csrf_token },
    data: { identifier: user.email, password: user.password },
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

test("admin sign-in is email + password only (no passkeys anywhere)", async ({ page }) => {
  await page.goto("/admin-login");
  await expect(page.locator("body")).not.toContainText(/passkey|webauthn|biometric|security key/i);
  await uiLogin(page, "/admin-login", ADMIN);
  await expect(page).toHaveURL(/\/admin\/dashboard/);
  await page.goto("/admin/admins");
  await expect(page.locator("body")).not.toContainText(/passkey/i);
  await expect(page.getByText(/invite/i).first()).toBeVisible();
});

test("wrong admin password is rejected with a generic message", async ({ page }) => {
  await page.goto("/admin-login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password", { exact: false }).first().fill("definitely-wrong");
  await page.getByRole("button", { name: /open admin portal|sign in/i }).first().click();
  await expect(page).toHaveURL(/admin-login/);
  await expect(page.locator("body")).toContainText(/invalid|incorrect|wrong/i);
});

test("admin invitation: invite -> accept via fragment link -> sign in -> link is single use", async ({ browser, request }) => {
  const csrf = await apiLogin(request, ADMIN, "/api/auth/admin-login");
  const invited = await request.post("/api/admin/admin-invitations", {
    headers: { "X-CSRFToken": csrf },
    data: { email: NEW_ADMIN.email, full_name: "Second Admin" },
  });
  expect(invited.status()).toBe(201);
  const body = await invited.json();
  // No mail provider on the test stack: the API must say nothing was sent and hand over the one-time link.
  expect(body.email_delivery).toBe("NOT_CONFIGURED");
  const link = new URL(body.invite_link);
  expect(link.hash.startsWith("#t=")).toBe(true);
  expect(link.search).toBe("");

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${link.pathname}${link.hash}`);
  await expect(page.getByLabel("Email")).toHaveValue(NEW_ADMIN.email);
  expect(page.url()).not.toContain("#t="); // the token was stripped from the address bar
  await page.getByLabel(/^Password/).first().fill(NEW_ADMIN.password);
  await page.getByLabel(/confirm/i).fill(NEW_ADMIN.password);
  await page.getByRole("button", { name: /activate|create|set|save|continue/i }).first().click();
  await expect(page.locator("body")).toContainText(/ready|sign in/i);

  await uiLogin(page, "/admin-login", NEW_ADMIN);
  await expect(page).toHaveURL(/\/admin\/dashboard/);
  // a second admin may not appoint admins
  await page.goto("/admin/admins");
  await expect(page.getByRole("button", { name: /send invitation|invite/i })).toHaveCount(0);

  // the same link cannot be reused
  const again = await ctx.newPage();
  await again.goto(`${link.pathname}${link.hash}`);
  await expect(again.locator("body")).toContainText(/invalid|expired|unavailable/i);
  await ctx.close();
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
