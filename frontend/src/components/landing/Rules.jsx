import { CalendarClock, FlaskConical, PencilLine, UsersRound } from "lucide-react";

const RULES = [
  {
    icon: CalendarClock,
    title: "Meeting times are the faculty's call",
    body: "Students request; faculty reply in writing and type the time themselves. Cancel from either side, but a reason is required, and the record stays in both histories.",
  },
  {
    icon: PencilLine,
    title: "Fix a message until it's seen",
    body: "A sent message can be edited only while the recipient hasn't opened it. After that it is part of the conversation record, which admins can review.",
  },
  {
    icon: UsersRound,
    title: "Mentors beyond your class",
    body: "Need a faculty member who doesn't teach your section? Send a supporting-faculty request. They accept or decline, and the chat opens only on acceptance.",
  },
  {
    icon: FlaskConical,
    title: "Scheduling research stays separate",
    body: "A research module compares first-come-first-served, rule-based and data-driven scheduling on synthetic data. It never touches live accounts or meetings.",
  },
];

/** House rules as a ruled list: content that is a list of rules, not a grid of cards. */
export function Rules() {
  return (
    <section id="rules" aria-labelledby="rules-title" className="border-t bg-surface-2 py-[clamp(3rem,7vw,6rem)]">
      <div className="mx-auto grid max-w-[1240px] gap-10 px-[clamp(1rem,4vw,2.5rem)] lg:grid-cols-[4fr_7fr] lg:gap-16">
        <div>
          <h2 id="rules-title" className="m-0 text-[clamp(1.9rem,1.3rem+2.4vw,3.1rem)] leading-[1.05] tracking-[-0.03em] lg:sticky lg:top-24">
            Small rules that keep mentoring honest
          </h2>
        </div>
        <ul className="m-0 grid list-none p-0">
          {RULES.map((r, i) => (
            <li key={r.title} className={`grid grid-cols-[2.5rem_1fr] gap-x-4 py-6 ${i === 0 ? "border-t-2 border-ink" : "border-t"} `}>
              <r.icon aria-hidden="true" className="mt-1 size-6 text-primary" />
              <div>
                <h3 className="m-0 mb-1.5 font-display text-[1.3rem] leading-tight font-bold tracking-tight">{r.title}</h3>
                <p className="m-0 max-w-[60ch] text-ink-2">{r.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
