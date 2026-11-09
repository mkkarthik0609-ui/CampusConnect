import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, ChevronDown, GraduationCap, Layers, Menu, MessagesSquare, Presentation, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Brand } from "@/components/app/BrandMark";
import { ThemeToggle } from "@/components/app/ThemeToggle";
import { CreateAccountMenu } from "@/components/landing/CreateAccountMenu";
import { goTo } from "@/lib/motion/scrollTo";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";
import { cn } from "@/lib/utils";

export const CONTACT_EMAIL = "mkkarthik0609@gmail.com";

/** Header menus. `id` = section id to scroll to; `slide` = step of the pinned showcase; `href` = external link. */
const MENUS = [
  {
    label: "How it works",
    items: [
      { icon: Layers, title: "Admin draws the map", id: "structure", slide: 0 },
      { icon: MessagesSquare, title: "Mentor-Connect follows the map", id: "structure", slide: 1 },
      { icon: CalendarClock, title: "A request has a clear path", id: "structure", slide: 2 },
    ],
  },
  {
    label: "Who it is for",
    items: [
      { icon: GraduationCap, title: "Student", desc: "Ask the right person, in writing.", id: "roles" },
      { icon: Presentation, title: "Faculty", desc: "Decide when, and keep the record.", id: "roles" },
      { icon: ShieldCheck, title: "Admin", desc: "Own the structure.", id: "roles" },
    ],
  },
];

const PLAIN_LINKS = [{ label: "House rules", id: "rules" }];

function jump(e, item) {
  if (item.href) return;
  e.preventDefault();
  goTo(item.id, item.slide);
}

function MegaMenu({ menu, onDark }) {
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button type="button" className={cn("lp-navlink group inline-flex min-h-11 items-center gap-1 rounded-sm px-3 text-[0.9375rem] font-medium", onDark ? "text-nav-ink" : "text-ink-2 hover:text-ink")}>
          {menu.label}
          <ChevronDown aria-hidden="true" className="size-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={10} className="w-[min(92vw,26rem)] rounded-xl p-2">
        {menu.items.map((item) => (
          <DropdownMenuItem key={item.title} asChild className="items-center gap-3 rounded-lg px-3 py-2.5">
            <a href={item.href || `#${item.id}`} onClick={(e) => jump(e, item)} className="no-underline">
              <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-sunken text-ink"><item.icon aria-hidden="true" className="size-[1.1rem]! text-ink!" /></span>
              <span className="grid gap-0.5">
                <span className="font-display text-[0.95rem] leading-tight font-medium text-foreground">{item.title}</span>
                {item.desc ? <span className="text-[0.8125rem] leading-snug text-muted-foreground">{item.desc}</span> : null}
              </span>
            </a>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MobileMenu({ authed, role, onDark }) {
  const [open, setOpen] = useState(false);
  const pending = useRef(null);
  const go = (item) => (e) => {
    if (item.href) return;
    e.preventDefault();
    pending.current = () => goTo(item.id, item.slide);
    setOpen(false);
  };
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className={cn("md:hidden", onDark && "text-nav-ink hover:bg-nav-hover hover:text-white")} aria-label="Open menu"><Menu aria-hidden="true" className="size-5" /></Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-[88%] gap-0 overflow-y-auto p-6 sm:max-w-sm"
        onCloseAutoFocus={(e) => {
          if (pending.current) { e.preventDefault(); pending.current(); pending.current = null; }
        }}
      >
        <SheetTitle className="sr-only">Menu</SheetTitle>
        <nav aria-label="Mobile" className="mt-8 grid gap-7">
          {MENUS.map((m) => (
            <div key={m.label}>
              <p className="m-0 mb-2 text-xs font-semibold tracking-[0.16em] text-muted-foreground uppercase">{m.label}</p>
              <ul className="m-0 grid list-none gap-0.5 p-0">
                {m.items.map((item) => (
                  <li key={item.title}>
                    <a href={item.href || `#${item.id}`} onClick={go(item)} className="flex min-h-11 items-center gap-3 rounded-lg px-2 font-display text-lg font-medium text-foreground no-underline hover:bg-primary-soft">
                      <item.icon aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" /> {item.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {PLAIN_LINKS.map((l) => (
            <a key={l.id} href={`#${l.id}`} onClick={go(l)} className="flex min-h-11 items-center rounded-lg px-2 font-display text-lg font-medium text-foreground no-underline hover:bg-primary-soft">{l.label}</a>
          ))}
        </nav>
        <div className="mt-auto grid gap-2 pt-8">
          {authed ? (
            <SheetClose asChild><Button asChild size="lg"><Link to={homeFor(role)}>Open dashboard</Link></Button></SheetClose>
          ) : (
            <>
              <SheetClose asChild><Button asChild size="lg" variant="outline"><Link to="/login">Sign in</Link></Button></SheetClose>
              <CreateAccountMenu size="lg" align="center" className="w-full" />
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/**
 * Fixed header: transparent over the dark hero, frosted + hairline once scrolled, condenses, hides while
 * scrolling down and returns on scroll up.
 */
export function LandingHeader() {
  const { isAuthenticated, role, status } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let last = window.scrollY;
    let raf = 0;
    const tick = () => {
      raf = 0;
      const y = window.scrollY;
      setScrolled(y > 24);
      if (Math.abs(y - last) > 6) {
        setHidden(y > 480 && y > last);
        last = y;
      }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(tick); };
    tick();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, []);

  const onDark = !scrolled;
  const authed = status !== "loading" && isAuthenticated;
  return (
    <header
      onFocusCapture={() => setHidden(false)}
      className={cn(
        "fixed inset-x-0 top-0 z-40 border-b transition-[transform,background-color,border-color] duration-300",
        hidden && "-translate-y-full",
        scrolled ? "border-line bg-background/85 text-foreground backdrop-blur-md" : "border-transparent text-nav-ink",
      )}
    >
      <div className={cn("lp-wrap flex items-center justify-between gap-3 transition-[height] duration-300", scrolled ? "h-14" : "h-20")}>
        <div className="flex items-center gap-4 lg:gap-8">
          <Brand to="/" size={28} className="text-inherit hover:text-inherit" onClick={(e) => { if (window.scrollY > 0) { e.preventDefault(); goTo("top"); } }} />
          <nav aria-label="Page sections" className="hidden items-center md:flex">
            {MENUS.map((m) => <MegaMenu key={m.label} menu={m} onDark={onDark} />)}
            {PLAIN_LINKS.map((l) => (
              <a key={l.id} href={`#${l.id}`} onClick={(e) => jump(e, l)} className={cn("lp-navlink inline-flex min-h-11 items-center rounded-sm px-3 text-[0.9375rem] font-medium no-underline", onDark ? "text-nav-ink" : "text-ink-2 hover:text-ink")}>{l.label}</a>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-1.5">
          <ThemeToggle tone={onDark ? "nav" : "page"} />
          {authed ? (
            <Button asChild className={cn("max-md:hidden", onDark && "border-nav-ink bg-nav-ink text-nav hover:border-white hover:bg-white")}><Link to={homeFor(role)}>Open dashboard</Link></Button>
          ) : status === "loading" ? null : (
            <>
              <Button asChild variant="outline" className={cn("max-md:hidden", onDark && "border-white/35 text-nav-ink hover:border-white hover:bg-white/10 hover:text-white")}><Link to="/login">Sign in</Link></Button>
              <CreateAccountMenu className={cn("max-md:hidden", onDark && "border-nav-ink bg-nav-ink text-nav hover:border-white hover:bg-white")} />
            </>
          )}
          <MobileMenu authed={authed} role={role} onDark={onDark} />
        </div>
      </div>
    </header>
  );
}
