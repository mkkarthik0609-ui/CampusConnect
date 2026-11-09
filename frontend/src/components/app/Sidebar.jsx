import { useId } from "react";
import { NavLink } from "react-router-dom";
import { LayoutGroup, MotionConfig, motion } from "motion/react";
import { useAuth } from "@/auth/AuthProvider";
import { Brand } from "@/components/app/BrandMark";
import { UserMenu } from "@/components/app/UserMenu";
import { ThemeToggle } from "@/components/app/ThemeToggle";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

/**
 * Sidebar body: brand, grouped links for the current role, account footer.
 * Rendered in a fixed column on desktop and inside a Sheet on mobile (AppShell).
 * The active pill is one shared element (motion layoutId) that glides from item to item.
 */
export function SidebarContent({ onNavigate, headerSlot }) {
  const { role, unread } = useAuth();
  const groups = NAV[role] || [];
  const pillId = useId(); // desktop column and mobile sheet can both be mounted; keep their pills apart

  return (
    <MotionConfig reducedMotion="user">
      <LayoutGroup id={pillId}>
        <div className="flex h-full min-h-0 flex-col bg-nav text-nav-ink">
          <div className="flex items-center justify-between px-5 pt-5 pb-4">
            <Brand to="/app" size={28} onClick={onNavigate} className="text-white hover:text-white" />
            {headerSlot}
          </div>

          <nav aria-label="Main" className="scroll-nav min-h-0 flex-1 overflow-y-auto px-3 pb-4">
            {groups.map((group, gi) => (
              <div key={group.label || gi} className={cn(gi > 0 && "mt-4 border-t border-nav-line pt-4")}>
                {group.label ? (
                  <p id={`nav-${pillId}-${gi}`} className="micro mb-2 px-3 text-nav-muted">{group.label}</p>
                ) : null}
                <ul aria-labelledby={group.label ? `nav-${pillId}-${gi}` : undefined} className="m-0 grid grid-cols-1 list-none gap-0.5 p-0">
                  {group.items.map((item) => {
                    const count = item.badge ? unread[item.badge] : 0;
                    return (
                      <li key={item.to}>
                        <NavLink
                          to={item.to}
                          onClick={onNavigate}
                          className={({ isActive }) =>
                            cn(
                              "group relative flex min-h-10 items-center gap-3 rounded-[8px] px-3 py-2 text-[0.9375rem] text-nav-muted no-underline outline-none transition-colors duration-200 hover:text-white focus-visible:ring-2 focus-visible:ring-white/70",
                              isActive && "font-medium text-white",
                            )
                          }
                        >
                          {({ isActive }) => (
                            <>
                              {isActive ? (
                                <motion.span
                                  layoutId="nav-pill"
                                  className="nav-pill"
                                  transition={{ type: "spring", stiffness: 420, damping: 36 }}
                                />
                              ) : (
                                <span aria-hidden="true" className="absolute inset-0 rounded-[8px] bg-nav-hover opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
                              )}
                              <item.icon aria-hidden="true" strokeWidth={1.7} className="relative size-[18px] shrink-0" />
                              <span className="relative min-w-0 flex-1">{item.label}</span>
                              {count ? (
                                <span className="relative ml-1 inline-flex h-[1.35rem] min-w-[1.35rem] items-center justify-center rounded-full bg-saffron px-1.5 text-xs font-semibold text-on-saffron tabular-nums">
                                  {count > 99 ? "99+" : count}
                                  <span className="sr-only"> unread</span>
                                </span>
                              ) : null}
                            </>
                          )}
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
      </LayoutGroup>
    </MotionConfig>
  );
}
