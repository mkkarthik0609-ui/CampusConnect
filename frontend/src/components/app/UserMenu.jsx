import { useNavigate } from "react-router-dom";
import { ChevronsUpDown, KeyRound, LogOut, Moon, Sun, UserRound } from "lucide-react";
import { toast } from "sonner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { UserAvatar } from "@/components/app/UserAvatar";
import { useAuth } from "@/auth/AuthProvider";
import { useTheme } from "@/lib/theme";
import { ROLE_LABEL } from "@/lib/nav";
import { errorMessage } from "@/lib/api";

/** Account menu in the sidebar footer: profile, change password, theme, sign out. */
export function UserMenu({ onNavigate }) {
  const { user, role, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  if (!user) return null;

  const profilePath = role === "STUDENT" ? "/student/profile" : role === "FACULTY" ? "/faculty/profile" : null;
  const go = (to) => { onNavigate?.(); navigate(to); };

  async function signOut() {
    try {
      await logout();
      navigate("/login", { replace: true });
    } catch (err) {
      toast.error(errorMessage(err, "Could not sign you out. Please try again."));
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex min-h-12 w-full min-w-0 items-center gap-3 rounded-xl px-2 py-1.5 text-left text-nav-ink transition-colors hover:bg-nav-hover hover:text-white data-[state=open]:bg-nav-hover"
        >
          <UserAvatar name={user.full_name} src={user.profile_picture_url} size="sm" />
          <span className="grid min-w-0 flex-1 leading-tight">
            <span className="truncate text-[0.93rem] font-semibold text-white">{user.full_name}</span>
            <span className="text-[0.8125rem] text-nav-muted">{ROLE_LABEL[role] || role}</span>
          </span>
          <ChevronsUpDown aria-hidden="true" className="size-4 shrink-0 text-nav-muted" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-[var(--radix-dropdown-menu-trigger-width)] min-w-56">
        <DropdownMenuLabel className="px-2.5 py-2 font-normal">
          <span className="block truncate text-sm font-semibold text-foreground">{user.full_name}</span>
          <span className="block truncate text-[0.8125rem] text-muted-foreground">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {profilePath ? (
          <DropdownMenuItem onSelect={() => go(profilePath)}><UserRound aria-hidden="true" /> Profile</DropdownMenuItem>
        ) : null}
        <DropdownMenuItem onSelect={() => go("/account/password")}><KeyRound aria-hidden="true" /> Change password</DropdownMenuItem>
        <DropdownMenuItem onSelect={toggle}>
          {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}><LogOut aria-hidden="true" /> Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
