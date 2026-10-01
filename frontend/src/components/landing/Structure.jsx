import { useRef, useState } from "react";
import { m, motionValue, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "motion/react";
import { Check, ChevronRight, Paperclip } from "lucide-react";
import { StatusPill } from "@/components/app/StatusPill";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";

/**
 * Scroll story: how one class structure drives chat and meetings.
 * Each scene is a pure function of a 0..1 MotionValue `p`:
 *   - desktop: one sticky stage, `p` comes from the page scroll slot of that chapter
 *   - narrower screens: three stacked stages, each driven by its own scroll position
 *   - reduced motion: `p` is fixed at 1 (final state, no scrubbing)
 */
const CHAPTERS = [
  {
    id: "map",
    title: "Admin draws the map",
    body: "Branch, department, year and section are defined once by the administrator. A student picks a real section at sign-up, so “3rd Year A” always means the same group of people.",
  },
  {
    id: "chat",
    title: "Mentor-Connect follows the map",
    body: "Students and faculty can message each other only when the class structure connects them. Attach a PDF, an image or a DOCX, and fix a typo until the other person has seen the message.",
  },
  {
    id: "meet",
    title: "A request has a clear path",
    body: "The student asks. The faculty member accepts or rejects in writing and types the time. Afterwards either side marks it completed, or cancels with a reason that both keep.",
  },
];

const clamp01 = (v) => Math.min(1, Math.max(0, v));
const useSeg = (p, a, b) => useTransform(p, (v) => clamp01((v - a) / (b - a)));

// ---------------------------------------------------------------------------------------------
// Scene 1: the hierarchy
// ---------------------------------------------------------------------------------------------
const LEVELS = [
  { label: "Branch", items: ["CSE", "ECE"], pick: 0 },
  { label: "Department", items: ["AIML", "Cyber Security"], pick: 0 },
  { label: "Year", items: ["2nd Year", "3rd Year"], pick: 1 },
  { label: "Section", items: ["A", "B"], pick: 0 },
];

function LevelRow({ level, index, p }) {
  const start = index * 0.2;
  const appear = useSeg(p, start, start + 0.12);
  const pick = useSeg(p, start + 0.1, start + 0.2);
  const y = useTransform(appear, (v) => (1 - v) * 14);
  return (
    <m.div style={{ opacity: appear, y }} className="grid grid-cols-[5.5rem_1fr] items-center gap-3">
      <span className="text-[0.8125rem] font-semibold text-nav-muted">{level.label}</span>
      <div className="flex flex-wrap gap-2">
        {level.items.map((item, i) => (
          <Chip key={item} chosen={i === level.pick} pick={pick}>{item}</Chip>
        ))}
      </div>
    </m.div>
  );
}

function Chip({ chosen, pick, children }) {
  const bg = useTransform(pick, (v) => (chosen && v > 0.5 ? "var(--accent-saffron)" : "rgba(255,255,255,0.1)"));
  const color = useTransform(pick, (v) => (chosen && v > 0.5 ? "var(--on-accent)" : "var(--nav-ink)"));
  const dim = useTransform(pick, (v) => (chosen ? 1 : 1 - v * 0.55));
  return (
    <m.span style={{ backgroundColor: bg, color, opacity: dim }} className="rounded-full border border-white/15 px-3.5 py-1.5 text-[0.9375rem] font-semibold">
      {children}
    </m.span>
  );
}

function SceneMap({ p }) {
  const result = useSeg(p, 0.82, 0.95);
  return (
    <div className="grid h-full content-center gap-4">
      {LEVELS.map((lv, i) => <LevelRow key={lv.label} level={lv} index={i} p={p} />)}
      <m.div style={{ opacity: result }} className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-white/15 pt-4 text-[0.9375rem] text-nav-ink">
        <span className="font-semibold text-white">CSE</span><ChevronRight aria-hidden="true" className="size-4 text-saffron" />
        <span className="font-semibold text-white">AIML</span><ChevronRight aria-hidden="true" className="size-4 text-saffron" />
        <span className="font-semibold text-white">3rd Year</span><ChevronRight aria-hidden="true" className="size-4 text-saffron" />
        <span className="font-semibold text-white">A</span>
        <span className="ml-auto font-mono text-[0.8125rem] text-nav-muted">stored as one section_id</span>
      </m.div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Scene 2: the thread
// ---------------------------------------------------------------------------------------------
function Msg({ p, at, mine, children }) {
  const v = useSeg(p, at, at + 0.14);
  const y = useTransform(v, (x) => (1 - x) * 16);
  return (
    <m.div style={{ opacity: v, y }} className={cn("max-w-[84%] rounded-2xl px-3.5 py-2 text-[0.9688rem] leading-snug", mine ? "self-end rounded-br-[5px] bg-primary text-primary-foreground" : "self-start rounded-bl-[5px] bg-white/10 text-white")}>
      {children}
    </m.div>
  );
}

function SceneChat({ p }) {
  const linked = useSeg(p, 0.02, 0.12);
  const seen = useSeg(p, 0.62, 0.72);
  const editable = useTransform(seen, (v) => 1 - v);
  return (
    <div className="flex h-full flex-col gap-3">
      <m.div style={{ opacity: linked }} className="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-[0.8125rem] font-semibold text-nav-ink">
        <Check aria-hidden="true" className="size-4 text-saffron" /> Same class chain
        <span className="font-normal text-nav-muted">CSE, AIML, 3rd Year, A</span>
      </m.div>
      <div className="flex flex-1 flex-col justify-center gap-2.5">
        <Msg p={p} at={0.12} mine>Sir, my report is ready. Can I show it before Friday?</Msg>
        <Msg p={p} at={0.28} mine>
          <span className="inline-flex items-center gap-1.5"><Paperclip aria-hidden="true" className="size-4" /> project-report.pdf</span>
        </Msg>
        <Msg p={p} at={0.5}>Received. Request a slot and I will set the time.</Msg>
      </div>
      <div className="flex items-center justify-between gap-3 text-[0.8125rem] text-nav-muted">
        <span className="inline-grid">
          <m.span style={{ opacity: editable }} className="col-start-1 row-start-1 font-semibold text-nav-ink">Edit allowed</m.span>
          <m.span style={{ opacity: seen }} className="col-start-1 row-start-1">Seen, now locked</m.span>
        </span>
        <span>PDF, image or DOCX</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Scene 3: the meeting
// ---------------------------------------------------------------------------------------------
const STEPS = ["Pending", "Accepted", "Completed"];

function SceneMeeting({ p }) {
  const [stage, setStage] = useState(0);
  useMotionValueEvent(p, "change", (v) => setStage(v < 0.3 ? 0 : v < 0.7 ? 1 : 2));
  const bar = useTransform(p, [0.2, 0.34, 0.62, 0.74], [0, 0.5, 0.5, 1]);
  const reply = useSeg(p, 0.36, 0.48);
  const done = useSeg(p, 0.74, 0.86);
  const key = ["PENDING", "ACCEPTED", "COMPLETED"][stage];
  return (
    <div className="grid h-full content-center gap-5">
      <div className="rounded-xl bg-white/[0.07] p-4 text-nav-ink">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="m-0 font-semibold text-white">Project report review</p>
            <p className="m-0 text-[0.8125rem] text-nav-muted">Ananya R. with Dr. Meera Iyer</p>
          </div>
          <StatusPill status={key} />
        </div>
        <m.p style={{ opacity: reply }} className="mt-3 mb-0 border-t border-white/15 pt-3 text-[0.9375rem]">
          <span className="font-semibold text-white">Reply from Dr. Iyer:</span> Thursday, 11:30. Bring the printed copy.
        </m.p>
        <m.p style={{ opacity: done }} className="mt-2 mb-0 flex items-center gap-1.5 text-[0.9375rem]">
          <Check aria-hidden="true" className="size-4 text-saffron" /> Marked completed. It stays in both histories.
        </m.p>
      </div>

      <div>
        <div className="relative mb-2 h-1 rounded-full bg-white/15">
          <m.div style={{ scaleX: bar }} className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-saffron" />
        </div>
        <ol className="m-0 grid list-none grid-cols-3 p-0 text-[0.8125rem] font-semibold">
          {STEPS.map((s, i) => (
            <li key={s} className={cn("transition-colors", i === 1 && "text-center", i === 2 && "text-right", i <= stage ? "text-white" : "text-nav-muted")}>{s}</li>
          ))}
        </ol>
      </div>
      <p className="m-0 text-[0.8125rem] text-nav-muted">Either side can cancel at any point, but a reason is required.</p>
    </div>
  );
}

const SCENES = [SceneMap, SceneChat, SceneMeeting];

function Stage({ children, label }) {
  return (
    <div role="img" aria-label={label} className="relative h-[24rem] overflow-hidden rounded-2xl bg-nav p-6 text-nav-ink shadow-md sm:h-[26rem] sm:p-8">
      {children}
    </div>
  );
}

const STAGE_LABELS = [
  "Illustration: Branch, Department, Year and Section chips; CSE, AIML, 3rd Year and A are selected.",
  "Illustration: a chat between a student and a faculty member in the same class, with an attached PDF.",
  "Illustration: a meeting request moving from Pending to Accepted to Completed.",
];

// ---------------------------------------------------------------------------------------------
// Desktop: sticky pinned stage
// ---------------------------------------------------------------------------------------------
function PinnedStory() {
  const ref = useRef(null);
  const { scrollYProgress: g } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const [active, setActive] = useState(0);
  useMotionValueEvent(g, "change", (v) => setActive(Math.min(2, Math.floor(v * 3 + 0.02))));

  const p = [
    useTransform(g, [0, 0.27], [0.14, 1]),
    useTransform(g, [1 / 3, 1 / 3 + 0.27], [0, 1]),
    useTransform(g, [2 / 3, 2 / 3 + 0.27], [0, 1]),
  ];
  const progress = useTransform(g, [0, 1], [0, 1]);

  return (
    <div ref={ref} className="relative h-[330vh]">
      <div className="sticky top-16 grid h-[calc(100dvh-4rem)] grid-cols-[minmax(0,5fr)_minmax(0,6fr)] items-center gap-14">
        <ol className="relative m-0 grid list-none gap-9 p-0 pl-7">
          <span aria-hidden="true" className="absolute top-1 bottom-1 left-0 w-0.5 rounded-full bg-line" />
          <m.span aria-hidden="true" style={{ scaleY: progress }} className="absolute top-1 bottom-1 left-0 w-0.5 origin-top rounded-full bg-primary" />
          {CHAPTERS.map((c, i) => (
            <li key={c.id} aria-current={active === i ? "step" : undefined} className={cn("transition-opacity duration-300", active === i ? "opacity-100" : "opacity-45")}>
              <h3 className="m-0 mb-2 font-display text-[1.45rem] leading-tight font-bold tracking-tight">{c.title}</h3>
              <p className="m-0 max-w-[44ch] text-ink-2">{c.body}</p>
            </li>
          ))}
        </ol>
        <div className="relative">
          <div className="h-[26rem]" />
          {SCENES.map((Scene, i) => (
            <div key={i} className={cn("absolute inset-0 transition-opacity duration-500 motion-reduce:transition-none", active === i ? "opacity-100" : "pointer-events-none opacity-0")} aria-hidden={active !== i}>
              <Stage label={STAGE_LABELS[i]}><Scene p={p[i]} /></Stage>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Narrow screens: stacked, each stage scrubbed by its own position
// ---------------------------------------------------------------------------------------------
function StackedChapter({ chapter, Scene, index }) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 90%", "end 45%"] });
  return (
    <li ref={ref} className="grid gap-5">
      <div>
        <h3 className="m-0 mb-2 font-display text-[1.35rem] leading-tight font-bold tracking-tight">{chapter.title}</h3>
        <p className="m-0 max-w-[52ch] text-ink-2">{chapter.body}</p>
      </div>
      <Stage label={STAGE_LABELS[index]}><Scene p={scrollYProgress} /></Stage>
    </li>
  );
}

function StaticStory() {
  const [fixed] = useState(() => motionValue(1));
  return (
    <ol className="m-0 grid list-none gap-12 p-0 lg:grid-cols-3">
      {CHAPTERS.map((c, i) => {
        const Scene = SCENES[i];
        return (
          <li key={c.id} className="grid content-start gap-5">
            <div>
              <h3 className="m-0 mb-2 font-display text-[1.35rem] leading-tight font-bold tracking-tight">{c.title}</h3>
              <p className="m-0 text-ink-2">{c.body}</p>
            </div>
            <Stage label={STAGE_LABELS[i]}><Scene p={fixed} /></Stage>
          </li>
        );
      })}
    </ol>
  );
}

export function Structure() {
  const reduce = useReducedMotion();
  const wide = useMediaQuery("(min-width: 60rem)");
  return (
    <section id="structure" aria-labelledby="structure-title" className="border-y bg-surface-2 py-[clamp(3rem,7vw,6rem)]">
      <div className="mx-auto max-w-[1240px] px-[clamp(1rem,4vw,2.5rem)]">
        <div className="mb-12 max-w-[40rem]">
          <h2 id="structure-title" className="m-0 text-[clamp(1.9rem,1.3rem+2.4vw,3.1rem)] leading-[1.05] tracking-[-0.03em]">
            One class structure decides who can reach whom
          </h2>
          <p className="mt-4 mb-0 text-[1.0625rem] text-ink-2">
            Everything in Campus Connect hangs off the same four levels. Scroll to watch a student's class turn into a conversation and a meeting.
          </p>
        </div>
        {reduce ? <StaticStory /> : wide ? <PinnedStory /> : (
          <ol className="m-0 grid list-none gap-14 p-0">
            {CHAPTERS.map((c, i) => <StackedChapter key={c.id} chapter={c} Scene={SCENES[i]} index={i} />)}
          </ol>
        )}
      </div>
    </section>
  );
}
