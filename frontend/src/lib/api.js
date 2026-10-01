/**
 * Campus Connect API client.
 *
 * Contract: docs/api/CONVENTIONS.md
 *  - same-origin fetch, session cookie (`cc_session`), JSON in / JSON out
 *  - every non-GET sends `X-CSRFToken`; the token comes from GET /api/auth/session
 *  - a 400 `csrf_failed` refreshes the token once and retries
 *  - errors are normalised to ApiError { status, code, message, fields }
 *  - a 401 calls the handler registered by AuthProvider (clears auth state, redirects to /login?next=...)
 *
 * Usage:
 *   import { api } from "@/lib/api";
 *   const { items } = await api.get("/api/notifications", { params: { limit: 20 } });
 *   await api.post("/api/meetings", { faculty_id: 4, purpose: "..." });
 *   await api.upload("/api/chats/3/messages", formData);          // multipart (POST)
 *   await api.upload("/api/account/photo", formData, { method: "PUT" });
 * Feature code should wrap calls in src/lib/endpoints.js (or its own file) so paths live in one place.
 */

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export class ApiError extends Error {
  /**
   * @param {{status?: number, code?: string, message?: string, fields?: Record<string,string>, data?: any}} init
   */
  constructor({ status = 0, code = "error", message = "Something went wrong.", fields = null, data = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields || {};
    this.data = data;
  }

  get isUnauthenticated() { return this.status === 401; }
  get isForbidden() { return this.status === 403; }
  get isNotFound() { return this.status === 404; }
  get isValidation() { return this.status === 400 || this.status === 422; }
  get isNetwork() { return this.status === 0; }
  get isRateLimited() { return this.status === 429; }

  /** Message for a single form field, or "". */
  fieldError(name) { return this.fields?.[name] || ""; }
}

/** Friendly message for any thrown value (use in toasts). */
export function errorMessage(err, fallback = "Something went wrong. Please try again.") {
  if (err instanceof ApiError) return err.message || fallback;
  return err?.message || fallback;
}

// ---------------------------------------------------------------------------------------------
// CSRF + session bootstrap
// ---------------------------------------------------------------------------------------------
let csrfToken = null;
let sessionInFlight = null;
let unauthorizedHandler = null;

export function getCsrfToken() { return csrfToken; }
export function setCsrfToken(token) { if (token) csrfToken = token; }

/** AuthProvider registers this so a 401 anywhere signs the user out cleanly. */
export function setUnauthorizedHandler(fn) { unauthorizedHandler = fn; }

/**
 * GET /api/auth/session -> { authenticated, user, csrf_token, unread_notifications, unread_messages }.
 * Also refreshes the CSRF token. Concurrent callers share one request.
 */
export function fetchSession() {
  if (!sessionInFlight) {
    sessionInFlight = send("GET", "/api/auth/session", { cache: "no-store" })
      .then((data) => {
        setCsrfToken(data?.csrf_token);
        return data;
      })
      .finally(() => { sessionInFlight = null; });
  }
  return sessionInFlight;
}

// ---------------------------------------------------------------------------------------------
// Core request
// ---------------------------------------------------------------------------------------------
function buildUrl(path, params) {
  if (!params) return path;
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => qs.append(key, String(v)));
    else qs.append(key, String(value));
  }
  const s = qs.toString();
  if (!s) return path;
  return path + (path.includes("?") ? "&" : "?") + s;
}

function normaliseError(status, payload, fallbackMessage) {
  const err = payload && typeof payload === "object" ? payload.error : null;
  if (err && typeof err === "object") {
    return new ApiError({
      status,
      code: err.code || "error",
      message: err.message || fallbackMessage,
      fields: err.fields || null,
      data: payload,
    });
  }
  if (typeof err === "string") return new ApiError({ status, code: "error", message: err, data: payload });
  return new ApiError({ status, code: status >= 500 ? "server_error" : "error", message: fallbackMessage, data: payload });
}

function fallbackFor(status) {
  if (status === 401) return "Please sign in to continue.";
  if (status === 403) return "You do not have access to this.";
  if (status === 404) return "We could not find what you asked for.";
  if (status === 413) return "That file is too large.";
  if (status === 429) return "Too many attempts. Please wait a moment and try again.";
  if (status >= 500) return "The server ran into a problem. Please try again in a moment.";
  return "Something went wrong. Please try again.";
}

async function send(method, path, { params, body, formData, signal, headers, cache } = {}) {
  const init = {
    method,
    credentials: "same-origin",
    signal,
    cache,
    headers: { Accept: "application/json", ...headers },
  };
  if (!SAFE_METHODS.has(method) && csrfToken) init.headers["X-CSRFToken"] = csrfToken;
  if (formData) {
    init.body = formData; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(buildUrl(path, params), init);
  } catch (e) {
    if (e?.name === "AbortError") throw e;
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: "We could not reach the server. Check your connection and try again.",
    });
  }

  const type = res.headers.get("content-type") || "";
  let payload = null;
  if (res.status !== 204) {
    if (type.includes("application/json")) {
      try { payload = await res.json(); } catch { payload = null; }
    } else {
      // HTML from a proxy/gateway error page - never surface it
      try { await res.text(); } catch { /* ignore */ }
    }
  }

  if (!res.ok) throw normaliseError(res.status, payload, fallbackFor(res.status));
  if (!type.includes("application/json") && res.status !== 204) {
    throw new ApiError({ status: 502, code: "bad_response", message: "The server sent an unexpected response." });
  }
  return payload ?? {};
}

/**
 * @param {string} method
 * @param {string} path
 * @param {{params?: object, body?: any, formData?: FormData, signal?: AbortSignal, skipAuthRedirect?: boolean}} opts
 */
async function request(method, path, opts = {}) {
  const unsafe = !SAFE_METHODS.has(method);
  if (unsafe && !csrfToken) {
    try { await fetchSession(); } catch { /* the real request below reports the failure */ }
  }
  try {
    return await send(method, path, opts);
  } catch (err) {
    if (err instanceof ApiError) {
      if (unsafe && err.status === 400 && err.code === "csrf_failed" && !opts._retried) {
        await fetchSession();
        return request(method, path, { ...opts, _retried: true });
      }
      if (err.status === 401 && !opts.skipAuthRedirect && unauthorizedHandler) unauthorizedHandler(err);
    }
    throw err;
  }
}

export const api = {
  get: (path, opts) => request("GET", path, opts),
  post: (path, body, opts) => request("POST", path, { ...opts, body }),
  put: (path, body, opts) => request("PUT", path, { ...opts, body }),
  patch: (path, body, opts) => request("PATCH", path, { ...opts, body }),
  delete: (path, opts) => request("DELETE", path, opts),
  /** Multipart upload. `formData` is a FormData; method defaults to POST. */
  upload: (path, formData, opts = {}) => request(opts.method || "POST", path, { ...opts, formData }),
};

/** Build a FormData from a plain object (skips null/undefined, keeps File/Blob values). */
export function toFormData(values) {
  const fd = new FormData();
  for (const [key, value] of Object.entries(values || {})) {
    if (value === undefined || value === null) continue;
    fd.append(key, value);
  }
  return fd;
}

/** Server-stored files are referenced as /uploads/<relative path> (auth-checked by Flask). */
export function uploadUrl(path) {
  if (!path) return null;
  if (/^(https?:)?\/\//.test(path) || path.startsWith("/uploads/")) return path;
  return `/uploads/${String(path).replace(/^\/+/, "")}`;
}
