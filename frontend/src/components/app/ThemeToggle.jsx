import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

/**
 * Light/dark toggle. Signed in: saves to the account (POST /api/account/theme). Signed out: local only.
 * `tone="nav"` is for the dark sidebar/top bar; `tone="page"` for light surfaces (landing, auth).
 */
export function ThemeToggle({ tone = "page", className }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className={cn(
        "inline-flex size-11 items-center justify-center rounded-lg transition-colors",
        tone === "nav" ? "text-nav-ink hover:bg-nav-hover hover:text-white" : "text-ink-2 hover:bg-primary-soft hover:text-primary-ink",
        className,
      )}
    >
      {dark ? <Sun aria-hidden="true" className="size-5" /> : <Moon aria-hidden="true" className="size-5" />}
    </button>
  );
}
