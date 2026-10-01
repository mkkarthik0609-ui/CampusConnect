// Runs before React mounts (see index.html): put the saved/system theme on <html> so the first paint is right.
// Signed-in users' server-side theme replaces this once the session loads (src/lib/theme.jsx).
import { applyTheme, storedTheme, systemTheme } from "@/lib/themeStorage";

applyTheme(storedTheme() || systemTheme());
