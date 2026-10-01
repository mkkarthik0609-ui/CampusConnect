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
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#080b1a" : "#111741");
}

/** Call on logout so the next person on a shared device starts from the system theme. */
export function forgetStoredTheme() {
  persistTheme(null);
  applyTheme(systemTheme());
}
