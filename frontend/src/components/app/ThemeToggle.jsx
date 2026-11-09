import { useId } from "react";
import { motion } from "motion/react";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const RAYS = [0, 45, 90, 135, 180, 225, 270, 315];

/** Sun that morphs into a crescent moon: the disc grows while a masking circle bites a crescent out of it, rays fold away. */
function SunMoon({ dark }) {
  const maskId = useId();
  const spring = { type: "spring", stiffness: 260, damping: 24 };
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true" focusable="false">
      <mask id={maskId}>
        <rect x="0" y="0" width="24" height="24" fill="white" stroke="none" />
        <motion.circle r="7" fill="black" stroke="none" initial={false} animate={{ cx: dark ? 17 : 30, cy: dark ? 6.5 : 0 }} transition={spring} />
      </mask>
      <motion.circle cx="12" cy="12" fill="currentColor" stroke="none" mask={`url(#${maskId})`} initial={false} animate={{ r: dark ? 8.5 : 4.4 }} transition={spring} />
      <motion.g initial={false} animate={{ rotate: dark ? 70 : 0, scale: dark ? 0.4 : 1, opacity: dark ? 0 : 1 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }} style={{ originX: 0.5, originY: 0.5 }}>
        {RAYS.map((a) => (
          <line key={a} x1="12" y1="2.6" x2="12" y2="4.4" transform={`rotate(${a} 12 12)`} />
        ))}
      </motion.g>
    </svg>
  );
}

/**
 * Light/dark toggle. Signed in: saves to the account (POST /api/account/theme). Signed out: local only.
 * The new theme is revealed as a circle growing from this button (see lib/theme.jsx).
 * `tone="nav"` is for the dark sidebar/top bar; `tone="page"` for light surfaces (landing, auth).
 */
export function ThemeToggle({ tone = "page", className }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={(e) => toggle(e)}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode (D)" : "Dark mode (D)"}
      className={cn(
        "inline-flex size-11 items-center justify-center rounded-[8px] border border-transparent outline-none transition-[background-color,border-color,color] duration-200 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        tone === "nav"
          ? "text-nav-ink hover:border-nav-line hover:bg-nav-hover hover:text-white focus-visible:ring-white/70 focus-visible:ring-offset-nav"
          : "text-ink-2 hover:border-line-strong hover:bg-primary-soft hover:text-foreground",
        className,
      )}
    >
      <SunMoon dark={dark} />
    </button>
  );
}
