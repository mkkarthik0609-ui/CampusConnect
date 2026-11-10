/* global process */
import { defineConfig } from "@playwright/test";

// End-to-end suite against a locally running stack (API + built SPA on one origin). See e2e/README.md.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:8765", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
