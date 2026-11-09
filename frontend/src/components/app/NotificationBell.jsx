import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { cn } from "@/lib/utils";

/** Bell link with an unread dot (used in the mobile top bar). The count lives in the accessible name. */
export function NotificationBell({ className }) {
  const { unread } = useAuth();
  const n = unread.notifications;
  return (
    <Link
      to="/notifications"
      aria-label={n ? `Notifications, ${n} unread` : "Notifications"}
      className={cn("relative inline-flex size-11 items-center justify-center rounded-[8px] text-inherit outline-none transition-colors hover:bg-nav-hover hover:text-white focus-visible:ring-2 focus-visible:ring-white/70", className)}
    >
      <Bell aria-hidden="true" className="size-[22px]" strokeWidth={1.6} />
      {n ? (
        <span aria-hidden="true" className="absolute top-[9px] right-[9px] size-2.5 rounded-full bg-saffron shadow-[0_0_0_2px_var(--nav-bg)]" />
      ) : null}
    </Link>
  );
}
