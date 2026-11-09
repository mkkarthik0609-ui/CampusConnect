import { Link } from "react-router-dom";
import { BrandMark } from "@/components/app/BrandMark";
import { useOnline } from "@/components/app/OfflineBanner";
import { useTheme } from "@/lib/theme";
import { version } from "../../../package.json";

/** One shortcut hint: [key] label */
function Hint({ k, children }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <kbd className="kbd">{k}</kbd>
      {children}
    </span>
  );
}

/**
 * Status-bar footer of the signed-in shell: a single dotted-leader row of uppercase micro labels
 * (wordmark ..... links ..... shortcut hints ..... version). Static: it never calls the API.
 * Shortcuts themselves are bound in AppShell (useShellShortcuts).
 */
export function AppFooter() {
  const online = useOnline();
  const { theme } = useTheme();
  return (
    <footer className="micro mt-auto border-t border-line px-[clamp(1rem,3.5vw,2.75rem)] py-3 text-muted-foreground">
      <div className="mx-auto flex max-w-[1120px] items-center gap-3 max-sm:flex-wrap max-sm:gap-y-2">
        <span className="inline-flex items-center gap-2 text-foreground">
          <BrandMark size={13} />
          CampusConnect
        </span>
        <span className="leader" aria-hidden="true" />
        <nav aria-label="Footer" className="inline-flex items-center gap-4">
          <Link to="/notifications" className="link-wipe text-inherit hover:text-foreground">Notifications</Link>
          <Link to="/account/password" className="link-wipe text-inherit hover:text-foreground">Password</Link>
        </nav>
        <span className="leader max-md:hidden" aria-hidden="true" />
        <span className="inline-flex items-center gap-4 max-md:hidden" aria-label="Keyboard shortcuts">
          <Hint k="D">{theme === "dark" ? "Light" : "Dark"}</Hint>
          <Hint k="N">Alerts</Hint>
          <Hint k="Esc">Close</Hint>
        </span>
        <span className="leader" aria-hidden="true" />
        <span className="num inline-flex items-center gap-2 whitespace-nowrap">
          <span aria-hidden="true" className={online ? "size-1.5 rounded-full bg-ok-ink" : "size-1.5 rounded-full bg-destructive"} />
          <span className="sr-only">{online ? "Online" : "Offline"}</span>
          v{version} / {new Date().getFullYear()}
        </span>
      </div>
    </footer>
  );
}
