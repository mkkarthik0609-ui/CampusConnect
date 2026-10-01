import { Suspense, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger, SheetClose } from "@/components/ui/sheet";
import { useAuth } from "@/auth/AuthProvider";
import { Brand } from "@/components/app/BrandMark";
import { NotificationBell } from "@/components/app/NotificationBell";
import { SidebarContent } from "@/components/app/Sidebar";
import { RouteFallback } from "@/components/app/PageLoader";

/**
 * The signed-in layout: fixed sidebar on desktop (>= 60rem), top bar + slide-out menu below.
 * Pages render into <Outlet/> inside <main id="main">. Keep pages free of their own page padding/max-width:
 * the shell provides them (max 1120px, fluid gutters).
 */
export function AppShell({ children }) {
  const { unread } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => { setOpen(false); }, [location.pathname]);
  useEffect(() => { window.scrollTo(0, 0); }, [location.pathname]);

  const unreadTotal = unread.notifications + unread.messages;
  // Re-run the entrance animation when the section changes, not on every param change.
  const sectionKey = location.pathname.split("/").slice(0, 3).join("/");

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[var(--nav-w)_minmax(0,1fr)]">
      <a className="skip-link" href="#main">Skip to main content</a>

      {/* Mobile / tablet top bar */}
      <header className="sticky top-0 z-30 flex h-[60px] items-center justify-between border-b border-nav-line bg-nav pr-2.5 pl-4 text-white lg:hidden">
        <Brand to="/app" size={30} />
        <div className="flex items-center gap-0.5">
          <NotificationBell />
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                aria-label={unreadTotal ? `Menu, ${unreadTotal} unread` : "Menu"}
                className="relative inline-flex size-11 items-center justify-center rounded-xl text-white hover:bg-nav-hover"
              >
                <Menu aria-hidden="true" className="size-6" />
                {unreadTotal ? <span aria-hidden="true" className="absolute top-[9px] right-[9px] size-2.5 rounded-full bg-saffron shadow-[0_0_0_2px_var(--nav-bg)]" /> : null}
              </button>
            </SheetTrigger>
            <SheetContent side="left" showCloseButton={false} className="w-[min(20rem,88vw)] gap-0 border-nav-line bg-nav p-0 text-nav-ink sm:max-w-none">
              <SheetTitle className="sr-only">Main menu</SheetTitle>
              <SheetDescription className="sr-only">Navigate between sections of Campus Connect</SheetDescription>
              <SidebarContent
                onNavigate={() => setOpen(false)}
                headerSlot={
                  <SheetClose asChild>
                    <button type="button" aria-label="Close menu" className="inline-flex size-11 items-center justify-center rounded-xl text-white hover:bg-nav-hover">
                      <X aria-hidden="true" className="size-[22px]" />
                    </button>
                  </SheetClose>
                }
              />
            </SheetContent>
          </Sheet>
        </div>
      </header>

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh border-r border-nav-line lg:block">
        <SidebarContent />
      </aside>

      <main id="main" tabIndex={-1} className="min-w-0 px-[clamp(1rem,3.5vw,2.75rem)] pt-5 pb-[4.5rem] lg:pt-8">
        <div key={sectionKey} className="page-enter mx-auto max-w-[1120px]">
          <Suspense fallback={<RouteFallback />}>
            {children ?? <Outlet />}
          </Suspense>
        </div>
      </main>
    </div>
  );
}
