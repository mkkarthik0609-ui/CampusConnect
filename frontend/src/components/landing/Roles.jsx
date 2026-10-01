import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, GraduationCap, Presentation, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

const ROLES = [
  {
    id: "student",
    icon: GraduationCap,
    name: "Student",
    promise: "Ask the right person, in writing.",
    points: [
      "Message the mentors for your class, with PDF, image or DOCX attachments.",
      "Request a meeting and read the faculty's written reply with the time.",
      "Ask a faculty member outside your class to support you.",
    ],
    cta: { to: "/signup/student", label: "Create a student account" },
    tone: "bg-primary text-primary-foreground border-primary",
    sub: "text-primary-foreground/85",
    btn: "bg-primary-foreground text-primary hover:bg-primary-foreground/90",
    rail: "bg-primary-foreground/15",
  },
  {
    id: "faculty",
    icon: Presentation,
    name: "Faculty",
    promise: "Decide when, and keep the record.",
    points: [
      "Accept or reject each request and type the meeting time yourself.",
      "Message the students in the classes Admin has assigned to you.",
      "Request extra classes; profile changes go to Admin for approval.",
    ],
    cta: { to: "/signup/faculty", label: "Register as faculty" },
    tone: "bg-card text-card-foreground border-line-strong",
    sub: "text-muted-foreground",
    btn: "bg-primary text-primary-foreground hover:bg-primary-hover",
    rail: "bg-sunken",
  },
  {
    id: "admin",
    icon: ShieldCheck,
    name: "Admin",
    promise: "Own the structure.",
    points: [
      "Build Branch, Department, Year and Section, and assign faculty to them.",
      "See who met whom and when, and read any conversation.",
      "Approve faculty detail changes and add other admins.",
    ],
    cta: { to: "/login", label: "Sign in as admin" },
    tone: "bg-nav text-nav-ink border-nav-line",
    sub: "text-nav-muted",
    btn: "bg-saffron text-on-saffron hover:brightness-95",
    rail: "bg-white/10",
    note: "Admin accounts are created by an existing admin; there is no public sign-up.",
  },
];

/**
 * Three entry points. Hovering or focusing a role widens it (desktop) or opens it (mobile).
 * Every panel's content stays in the DOM; closed panels are inert so keyboard order stays sane.
 */
export function Roles() {
  const [active, setActive] = useState("student");
  return (
    <section id="roles" aria-labelledby="roles-title" className="mx-auto max-w-[1240px] px-[clamp(1rem,4vw,2.5rem)] py-[clamp(3rem,7vw,6rem)]">
      <div className="mb-10 max-w-[40rem]">
        <h2 id="roles-title" className="m-0 text-[clamp(1.9rem,1.3rem+2.4vw,3.1rem)] leading-[1.05] tracking-[-0.03em]">Three roles, three different jobs</h2>
        <p className="mt-4 mb-0 text-[1.0625rem] text-ink-2">Pick the one that matches how you use the college.</p>
      </div>

      <div className="flex flex-col gap-3 lg:h-[27rem] lg:flex-row">
        {ROLES.map((r) => {
          const open = active === r.id;
          return (
            <article
              key={r.id}
              onMouseEnter={(e) => { if (window.matchMedia("(hover: hover)").matches) setActive(r.id); else e.preventDefault(); }}
              onFocus={() => setActive(r.id)}
              className={cn(
                "relative flex min-w-0 flex-col overflow-hidden rounded-2xl border p-6 transition-[flex-grow] duration-500 ease-[var(--ease-out-expo)] motion-reduce:transition-none lg:flex-[1_1_0%] lg:p-7",
                r.tone,
                open && "lg:flex-[2.3_1_0%]",
              )}
            >
              <h3 className="m-0">
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={`role-${r.id}`}
                  onClick={() => setActive(r.id)}
                  className="flex w-full items-center gap-3 rounded-md text-left font-display text-[1.6rem] leading-none font-bold tracking-tight text-inherit"
                >
                  <span className={cn("inline-flex size-10 shrink-0 items-center justify-center rounded-xl", r.rail)}><r.icon aria-hidden="true" className="size-5" /></span>
                  {r.name}
                </button>
              </h3>
              <p className={cn("m-0 mt-3 text-[1.0625rem] font-semibold", !open && "max-lg:hidden")}>{r.promise}</p>

              <div
                id={`role-${r.id}`}
                inert={!open}
                className={cn(
                  "grid transition-[grid-template-rows,opacity] duration-500 ease-[var(--ease-out-expo)] motion-reduce:transition-none max-lg:overflow-hidden",
                  open ? "mt-4 grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 lg:grid-rows-[1fr] lg:opacity-0",
                )}
              >
                <div className="min-h-0 overflow-hidden lg:min-w-[19rem]">
                  <ul className="m-0 grid list-none gap-3 p-0">
                    {r.points.map((pt) => (
                      <li key={pt} className={cn("border-t pt-3 text-[0.9688rem] leading-snug", r.sub, r.id === "faculty" ? "border-line" : "border-current/20")}>{pt}</li>
                    ))}
                  </ul>
                  <Link to={r.cta.to} className={cn("mt-5 inline-flex min-h-11 items-center gap-2 rounded-lg px-4 py-2 text-[0.94rem] font-[650] no-underline transition-colors", r.btn)}>
                    {r.cta.label} <ArrowRight aria-hidden="true" className="size-4" />
                  </Link>
                  {r.note ? <p className={cn("mt-3 mb-0 text-[0.8125rem]", r.sub)}>{r.note}</p> : null}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
