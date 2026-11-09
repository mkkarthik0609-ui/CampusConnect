import { useLayoutEffect, useRef } from "react";
import { CalendarClock, FlaskConical, PencilLine, UsersRound } from "lucide-react";
import { gsap, scrollFx } from "@/lib/motion/gsap";

/** Small hand-drawn underline under a key phrase; drawn on as the rule scrolls into view. */
function Underline({ children }) {
  return (
    <span className="relative inline-block">
      {children}
      <svg className="pointer-events-none absolute inset-x-0 -bottom-[0.3em] h-[0.4em] w-full overflow-visible text-saffron" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <path data-draw pathLength="1" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M3 9C40 3 72 12 112 6s58 3 85-1" />
      </svg>
    </span>
  );
}

// Original "House rules" copy, verbatim (the underline only marks a phrase inside each title).
const RULES = [
  {
    icon: CalendarClock,
    title: <>Meeting times are <Underline>the faculty&apos;s call</Underline></>,
    body: "Students request; faculty reply in writing and type the time themselves. Cancel from either side, but a reason is required, and the record stays in both histories.",
  },
  {
    icon: PencilLine,
    title: <>Fix a message <Underline>until it&apos;s seen</Underline></>,
    body: "A sent message can be edited only while the recipient hasn't opened it. After that it is part of the conversation record, which admins can review.",
  },
  {
    icon: UsersRound,
    title: <>Mentors <Underline>beyond your class</Underline></>,
    body: "Need a faculty member who doesn't teach your section? Send a supporting-faculty request. They accept or decline, and the chat opens only on acceptance.",
  },
  {
    icon: FlaskConical,
    title: <>Scheduling research <Underline>stays separate</Underline></>,
    body: "A research module compares first-come-first-served, rule-based and data-driven scheduling on synthetic data. It never touches live accounts or meetings.",
  },
];

/** The house rules as an editorial list. Underlines draw on scroll; static and complete under reduced motion. */
export function Statement() {
  const root = useRef(null);

  useLayoutEffect(
    () =>
      scrollFx(root.current, () => {
        gsap.utils.toArray("[data-rule]").forEach((rule) => {
          const draw = rule.querySelector("[data-draw]");
          gsap.set(draw, { strokeDasharray: 1, strokeDashoffset: 1 });
          gsap.to(draw, { strokeDashoffset: 0, ease: "none", scrollTrigger: { trigger: rule, start: "top 78%", end: "top 45%", scrub: 0.5 } });
        });
      }),
    [],
  );

  return (
    <section id="rules" ref={root} aria-labelledby="rules-title" className="bg-background py-[clamp(4rem,7vw,7rem)]">
      <div className="lp-wrap grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-20">
        <h2 id="rules-title" className="m-0 max-w-[16ch] font-display text-[clamp(1.75rem,1.2rem+1.6vw,2.5rem)] leading-[1.1] font-medium tracking-[-0.035em] lg:sticky lg:top-28 lg:self-start">
          Small rules that keep mentoring honest
        </h2>
        <ul className="m-0 grid list-none p-0">
          {RULES.map((r, i) => (
            <li key={i} data-rule className="grid grid-cols-[2.5rem_1fr] gap-x-4 border-t border-line py-7 first:border-t-2 first:border-ink first:pt-6">
              <r.icon aria-hidden="true" className="mt-0.5 size-6 text-muted-foreground" />
              <div>
                <h3 className="m-0 mb-3 font-display text-[clamp(1.2rem,1.05rem+0.5vw,1.4rem)] leading-tight font-medium tracking-[-0.02em]">{r.title}</h3>
                <p className="m-0 max-w-[60ch] text-[1.0625rem] leading-relaxed text-ink-2">{r.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
