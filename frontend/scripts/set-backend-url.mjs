#!/usr/bin/env node
// Points the Vercel rewrites in frontend/vercel.json at the Render backend. No dependencies.
//
//   node scripts/set-backend-url.mjs https://campus-connect-xxxx.onrender.com   (one-off, then commit)
//   BACKEND_URL=https://campus-connect-xxxx.onrender.com npm run build          (e.g. in Vercel's env settings)
//
// Runs automatically as the `prebuild` npm script:
//   * If BACKEND_URL (or a CLI argument) is set, every rewrite whose destination is an absolute URL
//     gets that origin (path and query are kept). Idempotent; a later run with another URL replaces it.
//   * If it is not set the file is left alone (so local `npm run build` works untouched).
//   * On Vercel (env VERCEL is set) the build FAILS if the placeholder host is still in vercel.json,
//     so a deployment can never go live proxying /api to nowhere.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PLACEHOLDER = "YOUR-RENDER-SERVICE";
const file = resolve(dirname(fileURLToPath(import.meta.url)), "..", "vercel.json");

function fail(message) {
  console.error(`\n[set-backend-url] ERROR: ${message}\n`);
  process.exit(1);
}

const arg = process.argv.slice(2).find((a) => !a.startsWith("-"));
const raw = (arg || process.env.BACKEND_URL || "").trim();

let text = readFileSync(file, "utf8");
const config = JSON.parse(text);

if (raw) {
  let origin;
  try {
    const url = new URL(raw);
    if (!["https:", "http:"].includes(url.protocol)) throw new Error("protocol");
    origin = url.origin; // drops any path / query / trailing slash
  } catch {
    fail(`BACKEND_URL "${raw}" is not a valid URL. Expected e.g. https://campus-connect.onrender.com`);
  }
  if (process.env.VERCEL && origin.startsWith("http://")) {
    fail(`BACKEND_URL must use https:// on Vercel (got ${origin}).`);
  }
  let changed = 0;
  for (const rule of config.rewrites || []) {
    const match = /^https?:\/\/[^/]+/.exec(rule.destination || "");
    if (match && match[0] !== origin) {
      rule.destination = origin + rule.destination.slice(match[0].length);
      changed += 1;
    }
  }
  if (changed) {
    text = JSON.stringify(config, null, 2) + "\n";
    writeFileSync(file, text);
  }
  console.log(`[set-backend-url] rewrites -> ${origin} (${changed} updated)`);
} else {
  console.log("[set-backend-url] BACKEND_URL not set; vercel.json left unchanged.");
}

if (text.includes(PLACEHOLDER)) {
  if (process.env.VERCEL) {
    fail(
      "vercel.json still points at the placeholder host YOUR-RENDER-SERVICE.onrender.com.\n" +
        "  Set the BACKEND_URL environment variable in the Vercel project (e.g. https://campus-connect-xxxx.onrender.com)\n" +
        "  or run `npm run set-backend-url -- <url>` locally and commit frontend/vercel.json."
    );
  }
  console.warn("[set-backend-url] note: vercel.json still contains the placeholder backend host.");
}
