/**
 * Theme: light / dark via the `.dark` class on <html>.
 *  - signed in:  the user's saved `theme` (session user) wins; toggling POSTs /api/account/theme
 *  - signed out: last local choice, else prefers-color-scheme
 * index.html runs a tiny script before first paint so there is no flash.
 * Toggling reveals the new theme as a circle growing from the clicked control (View Transitions API; instant fallback).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { toast } from "sonner";
import { useAuth } from "@/auth/AuthProvider";
import { accountApi } from "@/lib/endpoints";
import { errorMessage } from "@/lib/api";
import { applyTheme, persistTheme, storedTheme, systemTheme } from "@/lib/themeStorage";

const ThemeContext = createContext(null);

/** Where the reveal starts: a {x,y} point, an element, or a pointer/click event; centre of the viewport otherwise. */
function originPoint(origin) {
  if (origin && typeof origin.clientX === "number" && (origin.clientX || origin.clientY)) return { x: origin.clientX, y: origin.clientY };
  const el = origin instanceof Element ? origin : origin?.currentTarget instanceof Element ? origin.currentTarget : null;
  if (el) {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  if (origin && typeof origin.x === "number") return origin;
  return { x: window.innerWidth / 2, y: window.innerHeight / 2 };
}

/** Run a synchronous DOM/theme flip inside a circular-reveal view transition (skipped for reduced motion / no support). */
function withReveal(flip, origin) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (typeof document.startViewTransition !== "function" || reduce) {
    flip();
    return;
  }
  const { x, y } = originPoint(origin);
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  const transition = document.startViewTransition(flip);
  transition.ready
    .then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 650, easing: "cubic-bezier(0.16, 1, 0.3, 1)", pseudoElement: "::view-transition-new(root)" },
      );
    })
    .catch(() => {}); // skipped transitions reject .ready; the flip already ran
}

export function ThemeProvider({ children }) {
  const { user, status, patchUser } = useAuth();
  const [theme, setThemeState] = useState(() => storedTheme() || systemTheme());

  // Server preference wins as soon as we know who the user is.
  const serverTheme = user?.theme === "dark" || user?.theme === "light" ? user.theme : null;
  useEffect(() => {
    if (serverTheme) {
      setThemeState(serverTheme);
      persistTheme(serverTheme);
    }
  }, [serverTheme]);

  // Signed out: follow the system unless the visitor chose a theme on this device.
  useEffect(() => {
    if (status === "unauthenticated" && !storedTheme()) setThemeState(systemTheme());
  }, [status]);

  useEffect(() => { applyTheme(theme); }, [theme]);

  // While signed out and with no explicit local choice, follow OS changes.
  useEffect(() => {
    if (status === "authenticated") return undefined;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => { if (!storedTheme()) setThemeState(mq.matches ? "dark" : "light"); };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [status]);

  const setTheme = useCallback(async (next, origin) => {
    const previous = theme;
    // flushSync + applyTheme so the new colours are in the DOM when the transition takes its "after" snapshot
    withReveal(() => { flushSync(() => setThemeState(next)); applyTheme(next); }, origin);
    persistTheme(next);
    if (status === "authenticated") {
      patchUser({ theme: next });
      try {
        await accountApi.setTheme(next);
      } catch (err) {
        setThemeState(previous);
        persistTheme(previous);
        patchUser({ theme: previous });
        toast.error(errorMessage(err, "Could not save your theme."));
      }
    }
  }, [theme, status, patchUser]);

  /** toggle(originOrEvent?) - pass the click event or button element so the reveal grows from it. */
  const toggle = useCallback((origin) => setTheme(theme === "dark" ? "light" : "dark", origin), [theme, setTheme]);

  const value = useMemo(() => ({ theme, setTheme, toggle }), [theme, setTheme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
