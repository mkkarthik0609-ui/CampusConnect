import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

async function boot() {
  // Dev-only API mock (`npm run dev:mock`). The whole branch is removed from production builds.
  if (import.meta.env.DEV && import.meta.env.VITE_MOCK === "1") {
    const { installMock } = await import("./lib/mock");
    installMock();
  }
  createRoot(document.getElementById("root")).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

boot();
