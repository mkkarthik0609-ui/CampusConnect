import { useId, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { DAY_NAMES, METHODS, clock } from "./model";

const KIND_LABEL = { served: "Held", cancelled: "Cancelled", no_show: "No-show", conflict: "Class clash" };

function tally(blocks) {
  const t = { served: 0, cancelled: 0, no_show: 0, conflict: 0 };
  for (const b of blocks) t[b.kind] = (t[b.kind] || 0) + 1;
  return t;
}

function Block({ b, day, dayMin, color, facultyName }) {
  const left = ((b.start_min - day * dayMin) / dayMin) * 100;
  const width = Math.max(((b.end_min - b.start_min) / dayMin) * 100, 0.7);
  const inner = Math.min(100, (b.meeting_min / Math.max(b.end_min - b.start_min, 1)) * 100);
  const tip = `${facultyName}, ${b.start_clock}: ${KIND_LABEL[b.kind] || b.kind}, ${b.meeting_min} min meeting in a ${b.end_min - b.start_min} min block${b.backfill ? ", filled a freed slot" : ""}${b.priority === 3 ? ", urgent" : b.priority === 2 ? ", priority" : ""}`;
  return (
    <span
      title={tip}
      className={cn(
        "rs-block absolute top-[3px] bottom-[3px] block overflow-hidden rounded-[3px]",
        b.kind === "served" && "bg-[color-mix(in_oklab,var(--c)_32%,transparent)]",
        b.kind === "cancelled" && "border-2 border-dashed border-[var(--c)] bg-transparent",
        b.kind === "no_show" && "rs-hatch text-[var(--c)] opacity-80",
        b.kind === "conflict" && "bg-[color-mix(in_oklab,var(--c)_32%,transparent)] outline-2 outline-offset-1 outline-[var(--rs-conflict)]",
      )}
      style={{ left: `${left}%`, width: `${width}%`, "--c": color }}
    >
      {b.kind === "served" || b.kind === "conflict" ? (
        <span className="absolute top-0 bottom-0 left-0 block bg-[var(--c)]" style={{ width: `${inner}%` }} />
      ) : null}
      {b.priority === 3 ? <span className="absolute top-0 right-0 block size-1.5 rounded-full bg-saffron" /> : null}
    </span>
  );
}

function Lane({ f, day, dayMin, color, blocks }) {
  const lo = day * dayMin;
  const hi = lo + dayMin;
  const within = (iv) => iv[1] > lo && iv[0] < hi;
  const mine = blocks.filter((b) => b.faculty_id === f.faculty_id && b.day === day);
  const t = tally(mine);
  const label = `${f.name}, ${DAY_NAMES[day]}: ${t.served} held, ${t.cancelled} cancelled, ${t.no_show} no-show${t.conflict ? `, ${t.conflict} class clash` : ""}`;
  const pos = (iv) => ({ left: `${((Math.max(iv[0], lo) - lo) / dayMin) * 100}%`, width: `${((Math.min(iv[1], hi) - Math.max(iv[0], lo)) / dayMin) * 100}%` });
  return (
    <div>
      <div className="mb-0.5 flex items-baseline justify-between text-xs text-muted-foreground">
        <span className="font-semibold text-ink-2">{f.name}</span>
        <span className="num">{t.served} held</span>
      </div>
      <div role="img" aria-label={label} className="relative h-[26px] overflow-hidden rounded-[5px] border border-line bg-surface-2">
        {f.availability.filter(within).map((iv, i) => <span key={`a${i}`} className="absolute top-0 bottom-0 block bg-[var(--rs-window)]" style={pos(iv)} />)}
        {f.classes.filter(within).map((iv, i) => <span key={`c${i}`} className="absolute top-0 bottom-0 block bg-[var(--rs-class)]" style={pos(iv)} />)}
        {mine.map((b, i) => <Block key={`${b.request_id}-${i}`} b={b} day={day} dayMin={dayMin} color={color} facultyName={f.name} />)}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <ul className="m-0 mb-3 flex list-none flex-wrap gap-x-4 gap-y-1.5 p-0 text-[0.8125rem] text-ink-2" aria-label="Legend">
      <li className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-5 rounded-[2px] bg-[var(--rs-window)] ring-1 ring-line" />Posted availability</li>
      <li className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-5 rounded-[2px] bg-[var(--rs-class)]" />Class (blocked)</li>
      <li className="inline-flex items-center gap-1.5"><span className="relative inline-block h-3 w-5 overflow-hidden rounded-[2px] bg-ink/25"><span className="absolute inset-y-0 left-0 w-3/5 bg-ink/70" /></span>Meeting held (dark = real length)</li>
      <li className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-5 rounded-[2px] border-2 border-dashed border-ink/70" />Cancelled</li>
      <li className="inline-flex items-center gap-1.5"><span className="rs-hatch inline-block h-3 w-5 rounded-[2px] text-ink/70" />No-show</li>
      <li className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-5 rounded-[2px] bg-ink/25 outline-2 outline-offset-1 outline-[var(--rs-conflict)]" />Clashes with a class</li>
      <li className="inline-flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-saffron" />Urgent</li>
    </ul>
  );
}

/** Per-faculty Gantt lanes for the three methods, one day at a time, with a table alternative. */
export function Timeline({ timeline }) {
  const uid = useId();
  const [day, setDay] = useState(0);
  const axis = timeline.time_axis || { days: 5, day_minutes: 480 };
  const dayMin = axis.day_minutes;
  const startHour = Number.parseInt(String(axis.day_start_clock || "09:00").split(":")[0], 10) || 9;
  const ticks = useMemo(() => Array.from({ length: dayMin / 120 + 1 }, (_, i) => i * 120), [dayMin]);

  const rowsForTable = METHODS.flatMap((m) => (timeline.methods?.[m.id] || [])
    .filter((b) => b.day === day)
    .map((b) => ({ ...b, method: m.short })))
    .sort((a, b) => a.start_min - b.start_min);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Day of the simulated week" className="inline-flex flex-wrap gap-1 rounded-xl bg-muted p-1">
          {Array.from({ length: axis.days }, (_, d) => (
            <button
              key={d}
              type="button"
              aria-pressed={d === day}
              onClick={() => setDay(d)}
              className={cn("min-h-9 rounded-lg px-3.5 text-sm font-semibold transition-colors pointer-coarse:min-h-11", d === day ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
            >
              {DAY_NAMES[d]}
            </button>
          ))}
        </div>
        <p className="m-0 text-sm text-muted-foreground">Seed {timeline.seed}, first {timeline.faculty.length} faculty, {startHour}:00 to {startHour + dayMin / 60}:00</p>
      </div>

      <Legend />

      <div className="grid gap-4 lg:grid-cols-3">
        {METHODS.map((m) => {
          const blocks = timeline.methods?.[m.id] || [];
          const dayBlocks = blocks.filter((b) => b.day === day);
          const t = tally(blocks);
          return (
            <section key={m.id} aria-labelledby={`${uid}-${m.id}`} className="min-w-0 rounded-lg border bg-card p-3.5 shadow-sm">
              <h3 id={`${uid}-${m.id}`} className="m-0 flex items-center gap-2 text-base font-bold">
                <span className="inline-block size-3 rounded-[3px]" style={{ background: m.css }} aria-hidden="true" />
                {m.label}
              </h3>
              <p className="num mt-0.5 mb-3 text-[0.8125rem] text-muted-foreground">
                Week: {t.served} held, {t.cancelled} cancelled, {t.no_show} no-show{t.conflict ? `, ${t.conflict} clashes` : ""}
                <br />
                {DAY_NAMES[day]}: {dayBlocks.filter((b) => b.kind === "served").length} held
              </p>
              <div className="relative mb-1 h-4 text-[0.7rem] text-muted-foreground" aria-hidden="true">
                {ticks.map((tk) => (
                  <span key={tk} className="num absolute -translate-x-1/2 first:translate-x-0 last:-translate-x-full" style={{ left: `${(tk / dayMin) * 100}%` }}>{clock(tk, startHour).slice(0, 5)}</span>
                ))}
              </div>
              <div className="grid gap-2.5">
                {timeline.faculty.map((f) => (
                  <Lane key={f.faculty_id} f={f} day={day} dayMin={dayMin} color={m.css} blocks={blocks} />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      <details className="mt-4 rounded-lg border bg-card">
        <summary className="cursor-pointer rounded-lg px-4 py-3 text-sm font-semibold text-primary hover:bg-primary-soft">Show {DAY_NAMES[day]} as a table</summary>
        <div className="max-h-80 overflow-auto px-4 pb-4" tabIndex={0} role="region" aria-label={`Bookings on ${DAY_NAMES[day]}`}>
          <table className="w-full min-w-[34rem] border-collapse text-sm">
            <caption className="sr-only">Bookings on {DAY_NAMES[day]} for each method</caption>
            <thead>
              <tr className="text-left text-muted-foreground">
                {["Method", "Faculty", "Start", "Blocked", "Meeting", "Outcome"].map((h) => <th key={h} scope="col" className="border-b border-line px-2 py-1.5 font-semibold">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {rowsForTable.length ? rowsForTable.map((b, i) => (
                <tr key={i} className="border-b border-line last:border-b-0">
                  <td className="px-2 py-1.5">{b.method}</td>
                  <td className="px-2 py-1.5">{timeline.faculty.find((f) => f.faculty_id === b.faculty_id)?.name || b.faculty_id}</td>
                  <td className="num px-2 py-1.5">{b.start_clock}</td>
                  <td className="num px-2 py-1.5">{b.end_min - b.start_min} min</td>
                  <td className="num px-2 py-1.5">{b.meeting_min} min</td>
                  <td className="px-2 py-1.5">{KIND_LABEL[b.kind] || b.kind}{b.priority === 3 ? ", urgent" : ""}{b.backfill ? ", refilled slot" : ""}</td>
                </tr>
              )) : <tr><td colSpan={6} className="px-2 py-3 text-muted-foreground">No bookings on this day.</td></tr>}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
