/**
 * Theme: light / dark via the `.dark` class on <html>.
 *  - signed in:  the user's saved `theme` (session user) wins; toggling POSTs /api/account/theme
 *  - signed out: last local choice, else prefers-color-scheme
 * index.html runs a tiny inline script before first paint so there is no flash.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/auth/AuthProvider";
import { accountApi } from "@/lib/endpoints";
import { errorMessage } from "@/lib/api";
import { applyTheme, persistTheme, storedTheme, systemTheme } from "@/lib/themeStorage";

const ThemeContext = createContext(null);

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

  const setTheme = useCallback(async (next) => {
    const previous = theme;
    setThemeState(next); // instant
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

  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme, setTheme]);

  const value = useMemo(() => ({ theme, setTheme, toggle }), [theme, setTheme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
