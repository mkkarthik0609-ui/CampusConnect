/** Date/time helpers. The API sends UTC strings like "2026-03-14 09:30:00" (see CONVENTIONS.md). */

/** Parse an API timestamp (UTC, space or T separated) into a Date, or null. */
export function parseApiDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const s = String(value).trim().replace(" ", "T");
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s : `${s}Z`;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

const dateTimeFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

export function formatDateTime(value) {
  const d = parseApiDate(value);
  return d ? dateTimeFmt.format(d) : "";
}
export function formatDate(value) {
  const d = parseApiDate(value);
  return d ? dateFmt.format(d) : "";
}
export function formatTime(value) {
  const d = parseApiDate(value);
  return d ? timeFmt.format(d) : "";
}

const rtf = typeof Intl !== "undefined" && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }) : null;

/** "5 minutes ago", "yesterday", or a date once it is older than a week. */
export function timeAgo(value, now = Date.now()) {
  const d = parseApiDate(value);
  if (!d) return "";
  const diff = (d.getTime() - now) / 1000;
  const abs = Math.abs(diff);
  if (!rtf || abs > 7 * 86400) return formatDate(d);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

/** "Ananya Rao" -> "AR"; ignores Dr./Prof. prefixes. */
export function initials(name) {
  const parts = String(name || "?").replace(/\b(Dr|Prof|Mr|Mrs|Ms)\.?\s/gi, "").split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0] || "?";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

/** Only allow same-site absolute paths as post-login redirects. */
export function safeNext(next, fallback = "/app") {
  if (typeof next !== "string" || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}

export function pluralize(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}
