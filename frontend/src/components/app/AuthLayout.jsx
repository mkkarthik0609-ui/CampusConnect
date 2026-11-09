import { useEffect, useRef } from "react";
import { Outlet } from "react-router-dom";
import gsap from "gsap";
import { CircleCheck } from "lucide-react";
import { Brand, BrandMark } from "@/components/app/BrandMark";
import { ThemeToggle } from "@/components/app/ThemeToggle";
import { cn } from "@/lib/utils";

const YEAR = new Date().getFullYear();
const TICKER = ["For students", "Mentor chat", "For faculty", "Meeting requests", "For administrators", "Class approvals"];
const POINTS = [
  "Message your mentors directly, with attachments.",
  "Request meetings and keep a record of every outcome.",
  "Admin-defined classes, so approvals always reach the right people.",
];

// Fixed "random" dust: seeded so the markup is identical on every render.
const DUST = (() => {
  let s = 7;
  const next = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  return Array.from({ length: 30 }, () => ({ left: next() * 100, top: next() * 100, size: 2 + Math.round(next() * 3) }));
})();

/**
 * The inverse-theme panel: big tagline, the logo mark drawing itself then turning slowly, floating dust.
 * prefers-reduced-motion: nothing is animated, the mark simply sits there fully drawn.
 */
function AuthStage() {
  const root = useRef(null);

  useEffect(() => {
    const el = root.current;
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      const paths = el.querySelectorAll("[data-auth-mark] path");
      paths.forEach((p) => {
        const len = p.getTotalLength();
        gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
      });
      gsap.to(paths, { strokeDashoffset: 0, duration: 2.4, ease: "power2.inOut", stagger: 0.4 });
      gsap.to("[data-auth-mark]", { rotation: 360, duration: 140, ease: "none", repeat: -1, transformOrigin: "50% 50%" });
      gsap.utils.toArray("[data-dust]", el).forEach((d) => {
        gsap.set(d, { opacity: gsap.utils.random(0.15, 0.5) });
        gsap.to(d, {
          x: gsap.utils.random(-24, 24), y: gsap.utils.random(-44, 44), opacity: gsap.utils.random(0.2, 0.8),
          duration: gsap.utils.random(4, 9), delay: gsap.utils.random(0, 3), ease: "sine.inOut", repeat: -1, yoyo: true,
        });
      });
    }, el);
    return () => mm.revert();
  }, []);

  return (
    <div ref={root} className="relative flex h-full max-h-dvh flex-col justify-between gap-8 overflow-hidden p-[clamp(2rem,4vw,3.5rem)] lg:sticky lg:top-0">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        {DUST.map((d, i) => (
          <i key={i} data-dust="" className="absolute rounded-full bg-current opacity-30" style={{ left: `${d.left}%`, top: `${d.top}%`, width: d.size, height: d.size }} />
        ))}
      </div>

      <div aria-hidden="true" className="pointer-events-none relative grid min-h-0 flex-1 place-items-center">
        <div data-auth-mark="" className="origin-center text-background/90">
          <BrandMark size={220} strokeWidth={2.2} className="h-auto w-[clamp(9rem,17vw,15rem)]" />
        </div>
      </div>

      <div className="relative">
        <p className="m-0 mb-8 max-w-[22ch] font-display text-[clamp(1.75rem,1.2rem+1.6vw,2.5rem)] leading-[1.1] font-light tracking-[-0.04em] text-balance">
          Every student mapped to the faculty
        </p>
        <ul className="m-0 grid max-w-[32rem] list-none gap-2.5 p-0">
          {POINTS.map((text) => (
            <li key={text} className="flex items-start gap-3 text-[0.9375rem] text-background/70">
              <CircleCheck aria-hidden="true" className="mt-0.5 size-[1.05rem] shrink-0 text-saffron" />
              <span>{text}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Minimal footer for guest pages: a quiet ticker, a one-line legal note and the theme switch. */
function AuthFooter() {
  const row = (hidden) => (
    <ul aria-hidden={hidden || undefined} className="auth-marquee-row">
      {[0, 1, 2].flatMap((n) => TICKER.map((t) => <li key={`${n}-${t}`}>{t}<span aria-hidden="true" className="auth-marquee-dot" /></li>))}
    </ul>
  );
  return (
    <footer className="border-t">
      <div className="auth-marquee border-b py-3" role="group" aria-label="Campus Connect is for students, faculty and administrators">
        <div className="auth-marquee-track">{row(false)}{row(true)}</div>
      </div>
      <div className="flex items-center justify-between gap-4 px-5 py-1.5 sm:px-8">
        <p className="m-0 text-[0.8125rem] text-muted-foreground">&copy; {YEAR} CampusConnect. Students, faculty and administrators of the college.</p>
        <ThemeToggle />
      </div>
    </footer>
  );
}

/**
 * Guest layout for /login, /admin-login and /signup/*: the form on calm paper, an inverse-theme panel beside it
 * (desktop only), and the ticker footer under both. Pages render <AuthCard> inside the <Outlet/>.
 */
export function AuthLayout() {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <a className="skip-link" href="#main">Skip to main content</a>

      <div className="flex-1 lg:grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col">
          <header className="px-5 pt-6 sm:px-8 lg:px-[clamp(2rem,6vw,6rem)]">
            <Brand to="/" size={30} />
          </header>
          <main id="main" tabIndex={-1} className="flex flex-1 items-start justify-center px-5 pt-10 pb-14 sm:px-8 lg:justify-start lg:px-[clamp(2rem,6vw,6rem)] lg:pt-[clamp(2rem,9vh,6rem)]">
            <Outlet />
          </main>
        </div>

        <aside aria-label="About Campus Connect" className="hidden bg-foreground text-background lg:block">
          <AuthStage />
        </aside>
      </div>

      <AuthFooter />
    </div>
  );
}

/**
 * The form block used by every guest page (no box: the form sits straight on the paper).
 *   <AuthCard title="Sign in" lead="..." footer={<>New here? <Link/></>}>...form...</AuthCard>
 */
export function AuthCard({ title, lead, children, footer, wide = false, steps, className }) {
  return (
    <div className={cn("page-enter @container w-full", wide ? "max-w-[40rem]" : "max-w-[27rem]", className)}>
      {steps}
      <h1 className="font-display text-[clamp(2rem,1.6rem+1.1vw,2.5rem)] leading-[1.08] font-light tracking-[-0.04em]">{title}</h1>
      {lead ? <p className="mt-3 mb-9 text-muted-foreground">{lead}</p> : <div className="mb-9" />}
      <div className="auth-form">{children}</div>
      {footer ? <div className="auth-links mt-10 grid gap-2 border-t pt-6 text-[0.9375rem] text-muted-foreground">{footer}</div> : null}
    </div>
  );
}

/** Signup progress: a real sequence, so numbers are earned here. `current` is 1-based. */
export function Steps({ current, labels }) {
  return (
    <ol aria-label="Registration progress" className="m-0 mb-8 grid list-none grid-cols-3 gap-2 p-0">
      {labels.map((label, i) => {
        const n = i + 1;
        const done = n < current;
        const now = n === current;
        return (
          <li
            key={label}
            aria-current={now ? "step" : undefined}
            className={cn(
              "flex flex-col gap-1.5 border-t pt-2.5 text-[0.8125rem] font-medium",
              done || now ? "border-foreground" : "border-line-strong",
              now ? "text-foreground" : done ? "text-ink-2" : "text-muted-foreground",
            )}
          >
            <span className="tabular-nums">{done ? <CircleCheck aria-hidden="true" className="size-4" /> : String(n).padStart(2, "0")}</span>
            <span>{label}<span className="sr-only">{done ? " (done)" : now ? " (current step)" : ""}</span></span>
          </li>
        );
      })}
    </ol>
  );
}
