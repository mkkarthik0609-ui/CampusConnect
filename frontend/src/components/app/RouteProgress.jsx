import { useEffect, useSyncExternalStore } from "react";

/**
 * Thin top progress bar (NProgress-like) shown while a lazy route chunk / the session check is loading.
 * Suspense fallbacks call `useRouteProgress()`: mounting starts the bar, unmounting completes it.
 * <RouteProgress/> is mounted once (routes.jsx RootLayout). The look lives in index.css (.route-progress).
 */
let active = 0;
let state = "idle"; // idle | run | done
let startedAt = 0;
let doneTimer;
let bar = null; // the rendered bar element, so done() can read how far the trickle got
const listeners = new Set();

function set(next) {
  state = next;
  listeners.forEach((l) => l());
}

function start() {
  active += 1;
  if (active > 1) return;
  window.clearTimeout(doneTimer);
  startedAt = performance.now();
  set("run");
}

function done() {
  active = Math.max(0, active - 1);
  if (active > 0) return;
  // Under ~120ms the bar was never shown (see .route-progress), so skip the finishing animation too.
  if (performance.now() - startedAt < 120) return set("idle");
  // Hand the CSS the current width so the finishing animation continues from there instead of jumping.
  if (bar) bar.style.setProperty("--p", String(new DOMMatrix(getComputedStyle(bar).transform).a || 0.5));
  set("done");
  doneTimer = window.setTimeout(() => set("idle"), 520);
}

/** Call from a Suspense fallback (or any loading placeholder). */
export function useRouteProgress() {
  useEffect(() => {
    start();
    return done;
  }, []);
}

const subscribe = (l) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export function RouteProgress() {
  const current = useSyncExternalStore(subscribe, () => state, () => "idle");
  if (current === "idle") return null;
  return <div ref={(el) => { bar = el; }} aria-hidden="true" data-state={current} className="route-progress" />;
}
