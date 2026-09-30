// Build step for the Vercel frontend project (no dependencies).
//   static/  ->  public/static/   (served from Vercel's CDN; the filesystem wins over rewrites)
//   public/robots.txt             (the app is login-only; keep crawlers out)
// Every other path is proxied to the Render backend by the rewrite in vercel.json.
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const staticSrc = join(root, "static");
const outDir = join(root, "public");
const PLACEHOLDER = "YOUR-RENDER-SERVICE.onrender.com";

// Guard: never ship a proxy that points nowhere. Enforced on Vercel builds; a warning locally.
try {
  const cfg = JSON.parse(readFileSync(join(root, "vercel.json"), "utf8"));
  const dest = (cfg.rewrites || []).map((r) => String(r.destination || "")).join(" ");
  if (dest.includes(PLACEHOLDER)) {
    const msg =
      "vercel.json still points at the placeholder backend host. Run:\n" +
      "  node scripts/set-backend-url.mjs https://<your-service>.onrender.com\n" +
      "then commit vercel.json (see DEPLOYMENT.md).";
    if (process.env.VERCEL) {
      console.error("ERROR: " + msg);
      process.exit(1);
    }
    console.warn("WARNING: " + msg);
  }
} catch (err) {
  console.error("Could not read vercel.json: " + err.message);
  process.exit(1);
}

if (!existsSync(staticSrc)) {
  console.error("static/ directory not found at " + staticSrc);
  process.exit(1);
}

rmSync(outDir, { recursive: true, force: true });
mkdirSync(join(outDir, "static"), { recursive: true });
cpSync(staticSrc, join(outDir, "static"), { recursive: true });
writeFileSync(join(outDir, "robots.txt"), "User-agent: *\nDisallow: /\n");

console.log("Frontend build complete: public/static + public/robots.txt");
