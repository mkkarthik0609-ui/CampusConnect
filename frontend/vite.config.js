import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Flask (see docs/api/CONVENTIONS.md) owns /api, /uploads and /healthz.
// In dev, Vite serves the SPA on :5173 and proxies those paths to Flask on :5000 so the
// session cookie stays same-origin.
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: backend, changeOrigin: false },
      "/uploads": { target: backend, changeOrigin: false },
      "/healthz": { target: backend, changeOrigin: false },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": { target: backend, changeOrigin: false },
      "/uploads": { target: backend, changeOrigin: false },
      "/healthz": { target: backend, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("/motion") || id.includes("framer-motion")) return "motion";
          if (id.includes("@tanstack")) return "query";
          if (id.includes("react-router")) return "router";
          if (id.includes("radix-ui") || id.includes("@radix-ui")) return "radix";
          return undefined;
        },
      },
    },
  },
});
