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
      className={cn("relative inline-flex size-11 items-center justify-center rounded-xl text-inherit hover:bg-nav-hover hover:text-white", className)}
    >
      <Bell aria-hidden="true" className="size-[22px]" />
      {n ? (
        <span aria-hidden="true" className="absolute top-[9px] right-[9px] size-2.5 rounded-full bg-saffron shadow-[0_0_0_2px_var(--nav-bg)]" />
      ) : null}
    </Link>
  );
}
