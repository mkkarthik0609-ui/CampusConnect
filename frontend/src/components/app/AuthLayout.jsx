import { Outlet } from "react-router-dom";
import { MessagesSquare, CalendarDays, CircleCheck, ChevronRight } from "lucide-react";
import { Brand } from "@/components/app/BrandMark";
import { ThemeToggle } from "@/components/app/ThemeToggle";
import { cn } from "@/lib/utils";

const PATH = ["Branch", "Department", "Year", "Section"];

/**
 * Guest layout for /login and /signup/*: ink-navy story panel on the left (desktop), form on the right.
 * Below 62rem the panel collapses to a slim header. Pages render <AuthCard> inside.
 */
export function AuthLayout() {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[5fr_6fr]">
      <a className="skip-link" href="#main">Skip to main content</a>

      <aside aria-label="About Campus Connect" className="relative hidden h-dvh flex-col justify-between gap-6 overflow-hidden bg-nav p-[clamp(1.5rem,3.5vw,3rem)] text-nav-ink lg:sticky lg:top-0 lg:flex">
        <Brand to="/" size={40} wordClassName="text-[1.4rem] text-white" />

        <div className="max-w-[26rem]">
          <p className="mb-6 font-display text-[clamp(1.7rem,1.1rem+2vw,2.5rem)] leading-[1.1] font-bold tracking-[-0.02em] text-balance text-white">
            Every student, mapped to the faculty who know their class.
          </p>
          <ol aria-label="How classes are organised" className="m-0 mb-6 grid list-none gap-1.5 p-0">
            {PATH.map((label, i) => (
              <li key={label} style={{ paddingLeft: `${i * 1.4}rem` }} className="flex">
                <span
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-[0.9375rem] font-semibold",
                    i === PATH.length - 1 ? "border-saffron bg-saffron text-on-saffron" : "border-white/15 bg-white/10 text-white",
                  )}
                >
                  {i > 0 ? <ChevronRight aria-hidden="true" className={cn("size-4", i === PATH.length - 1 ? "text-on-saffron" : "text-saffron")} /> : null}
                  {label}
                </span>
              </li>
            ))}
          </ol>
          <ul className="m-0 grid list-none gap-3 p-0">
            {[
              [MessagesSquare, "Message your mentors directly, with attachments."],
              [CalendarDays, "Request meetings and keep a record of every outcome."],
              [CircleCheck, "Admin-defined classes, so approvals always reach the right people."],
            ].map(([Icon, text]) => (
              <li key={text} className="flex items-start gap-3 text-[0.96rem]">
                <Icon aria-hidden="true" className="mt-0.5 size-[18px] shrink-0 text-saffron" />
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="m-0 text-sm text-nav-muted">Students, faculty and administrators of the college.</p>
      </aside>

      <div className="min-w-0">
        <header className="flex items-center justify-between bg-nav px-5 py-3 lg:hidden">
          <Brand to="/" size={32} wordClassName="text-white" />
          <ThemeToggle tone="nav" />
        </header>
        <div className="relative">
          <ThemeToggle className="absolute top-4 right-4 z-10 max-lg:hidden" />
          <main id="main" tabIndex={-1} className="flex min-h-[calc(100dvh-4.5rem)] items-start justify-center px-4 pt-8 pb-14 sm:px-8 lg:min-h-dvh lg:items-center lg:py-12">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}

/**
 * The form card used by every guest page.
 *   <AuthCard title="Sign in" lead="..." footer={<>New here? <Link/></>}>...form...</AuthCard>
 */
export function AuthCard({ title, lead, children, footer, wide = false, steps, className }) {
  return (
    <div className={cn("page-enter w-full", wide ? "max-w-[40rem]" : "max-w-[29rem]", className)}>
      {steps}
      <h1 className="mb-1.5 text-[clamp(1.6rem,1.25rem+1.5vw,2.15rem)] leading-[1.1]">{title}</h1>
      {lead ? <p className="mb-6 text-muted-foreground">{lead}</p> : <div className="mb-6" />}
      <div className="rounded-xl border bg-card p-[clamp(1.25rem,3vw,2rem)] shadow-sm">{children}</div>
      {footer ? <div className="mt-6 grid gap-2 text-[0.9375rem] text-muted-foreground [&_a]:font-semibold">{footer}</div> : null}
    </div>
  );
}

/** Signup progress: a real sequence, so numbers are earned here. `current` is 1-based. */
export function Steps({ current, labels }) {
  return (
    <ol aria-label="Registration progress" className="m-0 mb-6 grid list-none grid-cols-3 gap-2 p-0">
      {labels.map((label, i) => {
        const n = i + 1;
        const done = n < current;
        const now = n === current;
        return (
          <li
            key={label}
            aria-current={now ? "step" : undefined}
            className={cn(
              "flex flex-col gap-1.5 border-t-[3px] pt-2.5 text-[0.8125rem] font-semibold",
              done || now ? "border-primary" : "border-line-strong",
              now ? "text-foreground" : done ? "text-ink-2" : "text-muted-foreground",
            )}
          >
            <span
              className={cn(
                "inline-flex size-[1.6rem] items-center justify-center rounded-full text-[0.8125rem] font-bold tabular-nums",
                done && "bg-primary text-primary-foreground",
                now && "bg-primary-soft text-primary-ink shadow-[inset_0_0_0_2px_var(--primary)]",
                !done && !now && "bg-sunken text-ink-2",
              )}
            >
              {done ? <CircleCheck aria-hidden="true" className="size-4" /> : n}
            </span>
            <span>{label}<span className="sr-only">{done ? " (done)" : now ? " (current step)" : ""}</span></span>
          </li>
        );
      })}
    </ol>
  );
}
