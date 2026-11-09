/** Theme plumbing with no React or auth imports (so AuthProvider and ThemeProvider can both use it). */
const STORAGE_KEY = "cc-theme";

export function systemTheme() {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function storedTheme() {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null;
  }
}

export function persistTheme(theme) {
  try {
    if (theme) window.localStorage.setItem(STORAGE_KEY, theme);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch { /* storage unavailable - fine */ }
}

/** Put the theme on <html> (class + color-scheme + theme-color meta). */
export function applyTheme(theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  // index.html ships one theme-color per OS scheme (media attr); the in-app choice overrides both.
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => {
    m.removeAttribute("media");
    m.setAttribute("content", theme === "dark" ? "#0a0a0b" : "#f7f7f5");
  });
}

/** Call on logout so the next person on a shared device starts from the system theme. */
export function forgetStoredTheme() {
  persistTheme(null);
  applyTheme(systemTheme());
}
