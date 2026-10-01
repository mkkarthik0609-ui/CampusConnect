import { NavLink } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { Brand } from "@/components/app/BrandMark";
import { UserMenu } from "@/components/app/UserMenu";
import { ThemeToggle } from "@/components/app/ThemeToggle";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

/**
 * Sidebar body: brand, grouped links for the current role, account footer.
 * Rendered in a fixed column on desktop and inside a Sheet on mobile (AppShell).
 */
export function SidebarContent({ onNavigate, headerSlot }) {
  const { role, unread } = useAuth();
  const groups = NAV[role] || [];

  return (
    <div className="flex h-full min-h-0 flex-col bg-nav text-nav-ink">
      <div className="flex items-center justify-between px-[1.1rem] pt-5 pb-3 text-white">
        <Brand to="/app" size={32} onClick={onNavigate} />
        {headerSlot}
      </div>

      <nav aria-label="Main" className="scroll-nav min-h-0 flex-1 overflow-y-auto px-3 pt-2 pb-4">
        {groups.map((group, gi) => (
          <div key={group.label || gi}>
            {group.label ? (
              <p id={`nav-${gi}`} className="mt-5 mb-1.5 px-3 text-[0.8125rem] font-semibold text-nav-muted">{group.label}</p>
            ) : null}
            <ul aria-labelledby={group.label ? `nav-${gi}` : undefined} className="m-0 grid list-none gap-0.5 p-0">
              {group.items.map((item) => {
                const count = item.badge ? unread[item.badge] : 0;
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      onClick={onNavigate}
                      className={({ isActive }) =>
                        cn(
                          "group flex min-h-[42px] items-center gap-3 rounded-[10px] px-3 py-2 text-[0.96rem] font-medium text-nav-ink no-underline transition-colors hover:bg-nav-hover hover:text-white",
                          isActive && "bg-nav-active font-[650] text-white",
                        )
                      }
                    >
                      <item.icon aria-hidden="true" className="size-5 shrink-0 group-aria-[current=page]:text-saffron" />
                      <span className="min-w-0 flex-1">{item.label}</span>
                      {count ? (
                        <span className="ml-1 inline-flex h-[1.4rem] min-w-[1.4rem] items-center justify-center rounded-full bg-saffron px-1.5 text-xs font-bold text-on-saffron tabular-nums">
                          {count > 99 ? "99+" : count}
                          <span className="sr-only"> unread</span>
                        </span>
                      ) : null}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-1 border-t border-nav-line px-3 py-3">
        <div className="min-w-0 flex-1"><UserMenu onNavigate={onNavigate} /></div>
        <ThemeToggle tone="nav" />
      </div>
    </div>
  );
}
