import { useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, GraduationCap, Presentation, ShieldCheck } from "lucide-react";
import { useReveal } from "@/lib/motion/useReveal";
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
    tone: "border-primary bg-primary text-primary-foreground",
    sub: "text-primary-foreground/80",
    rule: "border-primary-foreground/20",
    chip: "bg-primary-foreground/12",
    btn: "bg-primary-foreground text-primary hover:bg-primary-foreground/85",
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
    tone: "border-line-strong bg-card text-card-foreground",
    sub: "text-muted-foreground",
    rule: "border-line",
    chip: "bg-sunken",
    btn: "bg-primary text-primary-foreground hover:bg-primary-hover",
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
    tone: "border-nav-line bg-nav text-nav-ink",
    sub: "text-nav-muted",
    rule: "border-white/15",
    chip: "bg-white/10",
    btn: "bg-nav-ink text-nav hover:bg-white",
    note: "Admin accounts are created by an existing admin; there is no public sign-up.",
  },
];

/** Three roles as hover-lift cards: a grid on desktop, a swipeable scroll-snap row on phones. */
export function Roles() {
  const root = useRef(null);
  useReveal(root);
  return (
    <section id="roles" ref={root} aria-labelledby="roles-title" className="bg-surface-2 py-[clamp(4rem,7vw,7rem)]">
      <div className="lp-wrap">
        <div data-reveal className="mb-9 max-w-[40rem] lg:mb-12">
          <h2 id="roles-title" className="m-0 font-display text-[clamp(1.75rem,1.2rem+1.6vw,2.5rem)] leading-[1.04] font-medium tracking-[-0.04em]">Three roles, three different jobs</h2>
          <p className="mt-5 mb-0 text-[1.0625rem] text-ink-2">Pick the one that matches how you use the college.</p>
        </div>
      </div>

      <ul className="lp-snap lp-wrap mx-auto my-0 flex list-none gap-4 overflow-x-auto pt-3 pb-6 max-lg:scroll-px-4 lg:grid lg:grid-cols-3 lg:gap-5 lg:overflow-visible lg:pb-0">
        {ROLES.map((r) => (
          <li key={r.id} data-reveal className="flex w-[84%] shrink-0 snap-center sm:w-[26rem] lg:w-auto">
            <article className={cn("flex w-full flex-col rounded-2xl border p-6 transition-[transform,box-shadow] duration-300 ease-[var(--ease-out-expo)] hover:-translate-y-2 hover:shadow-md focus-within:-translate-y-2 focus-within:shadow-md lg:p-8", r.tone)}>
              <span className={cn("inline-flex size-11 items-center justify-center rounded-xl", r.chip)}><r.icon aria-hidden="true" className="size-5" /></span>
              <h3 className="m-0 mt-6 font-display text-[1.5rem] leading-none font-medium tracking-[-0.03em] text-inherit">{r.name}</h3>
              <p className="m-0 mt-2 text-[1.0625rem] font-medium">{r.promise}</p>
              <ul className="m-0 mt-5 grid list-none gap-3 p-0">
                {r.points.map((pt) => (
                  <li key={pt} className={cn("border-t pt-3 text-[0.9688rem] leading-snug", r.sub, r.rule)}>{pt}</li>
                ))}
              </ul>
              <div className="mt-auto pt-7">
                <Link to={r.cta.to} className={cn("group inline-flex min-h-11 items-center gap-2 rounded-lg px-4 py-2 text-[0.94rem] font-[650] no-underline transition-colors", r.btn)}>
                  {r.cta.label} <ArrowRight aria-hidden="true" className="size-4 transition-transform duration-200 group-hover:translate-x-1" />
                </Link>
                {r.note ? <p className={cn("mt-3 mb-0 text-[0.8125rem]", r.sub)}>{r.note}</p> : null}
              </div>
            </article>
          </li>
        ))}
      </ul>
    </section>
  );
}
