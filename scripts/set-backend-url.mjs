// Point the Vercel proxy rewrite at your Render service by editing vercel.json in place.
//
//   node scripts/set-backend-url.mjs https://my-service.onrender.com
//   BACKEND_URL=https://my-service.onrender.com node scripts/set-backend-url.mjs
//
// Why a script and not a build-time step? Vercel reads vercel.json BEFORE the build runs, so a
// file generated during the build would be ignored. Run this once locally (or in CI), commit
// vercel.json and push. It is idempotent and works for the placeholder or any earlier host.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const file = join(dirname(fileURLToPath(import.meta.url)), "..", "vercel.json");
const raw = process.argv[2] || process.env.BACKEND_URL || "";

if (!raw) {
  console.error("Usage: node scripts/set-backend-url.mjs https://<service>.onrender.com  (or set BACKEND_URL)");
  process.exit(1);
}

let url;
try {
  url = new URL(raw);
} catch {
  console.error("Not a valid URL: " + raw);
  process.exit(1);
}
if (url.protocol !== "https:") {
  console.error("Backend URL must use https://");
  process.exit(1);
}
const origin = url.origin; // strips any path / trailing slash

const cfg = JSON.parse(readFileSync(file, "utf8"));
let changed = 0;
for (const r of cfg.rewrites || []) {
  if (/^https?:\/\//.test(r.destination || "")) {
    r.destination = origin + "/:path*";
    changed++;
  }
}
if (!changed) {
  console.error("No external rewrite destination found in vercel.json");
  process.exit(1);
}
writeFileSync(file, JSON.stringify(cfg, null, 2) + "\n");
console.log(`vercel.json: proxy destination set to ${origin}/:path* (${changed} rewrite(s) updated)`);
