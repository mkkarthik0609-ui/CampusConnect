import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { m, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import { Check, ChevronRight, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CreateAccountMenu } from "@/components/landing/LandingHeader";
import { StatusPill } from "@/components/app/StatusPill";
import { UserAvatar } from "@/components/app/UserAvatar";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";
import { cn } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1];

/** Headline: each word rises out of its own clipped box (so lines can wrap freely). Text is visible at rest. */
const WORDS = "Every student, mapped to the faculty who know their class.".split(" ");
function Headline({ reduce }) {
  return (
    <h1 className="m-0 flex max-w-[12.5em] flex-wrap gap-x-[0.24em] text-[clamp(2.6rem,1.6rem+5vw,5.25rem)] leading-[1] font-bold tracking-[-0.035em]">
      {WORDS.map((word, i) => (
        <span key={word + i} className="inline-block overflow-hidden pb-[0.1em]">
          <m.span
            className={cn("inline-block", word === "class." && "text-primary")}
            initial={reduce ? false : { y: "105%" }}
            animate={{ y: 0 }}
            transition={{ duration: 0.8, delay: 0.08 + i * 0.06, ease: EASE }}
          >
            {word}
          </m.span>
        </span>
      ))}
    </h1>
  );
}

/** Class path whose pills land one after another. */
function AnimatedPath({ reduce, start = 0.7 }) {
  const parts = ["CSE", "AIML", "3rd Year", "A"];
  return (
    <div className="flex flex-wrap items-center gap-y-1.5" aria-hidden="true">
      {parts.map((p, i) => (
        <span key={p} className="inline-flex items-center">
          {i > 0 ? (
            <m.span initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: start + i * 0.18 - 0.05 }} className="mx-1 inline-flex">
              <ChevronRight className="size-4 text-muted-foreground" />
            </m.span>
          ) : null}
          <m.span
            initial={reduce ? false : { y: -14, opacity: 0, scale: 0.9 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            transition={{ type: "spring", stiffness: 420, damping: 22, delay: start + i * 0.18 }}
            className={cn(
              "rounded-full px-3 py-1 text-[0.9375rem] font-semibold",
              i === parts.length - 1 ? "bg-primary-soft font-bold text-primary-ink ring-2 ring-primary/40" : "bg-sunken text-ink-2",
            )}
          >
            {p}
          </m.span>
        </span>
      ))}
    </div>
  );
}

function Panel({ className, style, children, reduce, delay = 0, ...rest }) {
  return (
    <m.div
      style={style}
      initial={reduce ? false : { opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay, ease: EASE }}
      className={cn("rounded-xl border bg-card shadow-md", className)}
      {...rest}
    >
      {children}
    </m.div>
  );
}

function Bubble({ mine, children, delay, reduce }) {
  return (
    <m.div
      initial={reduce ? false : { opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, delay, ease: EASE }}
      className={cn("bubble", mine ? "bubble-mine" : "bubble-theirs")}
      style={{ transformOrigin: mine ? "100% 100%" : "0% 100%" }}
    >
      {children}
    </m.div>
  );
}

/** The product, in one composed frame: class path, a Mentor-Connect thread, a meeting moving to Accepted. */
function HeroStage({ reduce }) {
  const [accepted, setAccepted] = useState(!!reduce);
  useEffect(() => {
    if (reduce) return undefined;
    const id = window.setTimeout(() => setAccepted(true), 4600);
    return () => window.clearTimeout(id);
  }, [reduce]);

  // Pointer parallax: three depths, springs, transform only. Off for reduced motion and touch.
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const sx = useSpring(px, { stiffness: 90, damping: 18, mass: 0.6 });
  const sy = useSpring(py, { stiffness: 90, damping: 18, mass: 0.6 });
  const a = { x: useTransform(sx, (v) => v * -8), y: useTransform(sy, (v) => v * -6) };
  const b = { x: useTransform(sx, (v) => v * 14), y: useTransform(sy, (v) => v * 10) };
  const c = { x: useTransform(sx, (v) => v * -20), y: useTransform(sy, (v) => v * 16) };

  function onMove(e) {
    if (reduce || e.pointerType !== "mouse") return;
    const r = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width - 0.5);
    py.set((e.clientY - r.top) / r.height - 0.5);
  }
  function onLeave() { px.set(0); py.set(0); }

  return (
    <div onPointerMove={onMove} onPointerLeave={onLeave} className="relative mx-auto w-full max-w-[34rem] lg:mx-0 lg:ml-auto lg:h-[35rem]">
      <p className="sr-only">
        An illustration: a student's class path (CSE, AIML, 3rd Year, A), a Mentor-Connect conversation with a faculty member, and a meeting request that moves from Pending to Accepted with a time set by the faculty member.
      </p>

      <div aria-hidden="true" className="grid gap-4 lg:block">
        {/* A: class */}
        <Panel reduce={reduce} delay={0.45} style={{ x: a.x, y: a.y }} className="p-5 lg:absolute lg:top-0 lg:left-0 lg:w-[88%]">
          <p className="mb-3 text-sm font-semibold text-muted-foreground">Your class, set by Admin</p>
          <AnimatedPath reduce={reduce} />
        </Panel>

        {/* B: thread */}
        <Panel reduce={reduce} delay={1.2} style={{ x: b.x, y: b.y }} className="overflow-hidden max-lg:ml-6 lg:absolute lg:top-[7.6rem] lg:right-0 lg:w-[90%]">
          <div className="flex items-center gap-3 border-b px-4 py-3">
            <UserAvatar name="Meera Iyer" size="sm" />
            <div className="min-w-0 leading-tight">
              <p className="m-0 truncate text-[0.9375rem] font-semibold">Dr. Meera Iyer</p>
              <p className="m-0 text-[0.8125rem] text-muted-foreground">Mentor-Connect</p>
            </div>
          </div>
          <div className="grid gap-2 bg-surface-2 p-4">
            <Bubble mine reduce={reduce} delay={1.7}>Sir, can I show you my mini-project report before Friday?</Bubble>
            <m.div
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2.3 }}
              className="flex items-center gap-1.5 self-end rounded-md border bg-card px-2.5 py-1 text-[0.8125rem] font-semibold text-ink-2"
            >
              <Paperclip className="size-3.5" /> project-report.pdf
            </m.div>
            <Bubble reduce={reduce} delay={2.9}>Yes. Send it here and request a slot. I will set the time.</Bubble>
          </div>
        </Panel>

        {/* C: meeting */}
        <Panel reduce={reduce} delay={3.2} style={{ x: c.x, y: c.y }} className="max-lg:mr-6 p-4 lg:absolute lg:bottom-0 lg:left-0 lg:w-[72%]">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="m-0 text-[0.9375rem] font-semibold">Project report review</p>
              <p className="m-0 text-[0.8125rem] text-muted-foreground">with Dr. Meera Iyer</p>
            </div>
            <span className="relative inline-grid">
              <m.span animate={{ opacity: accepted ? 0 : 1 }} transition={{ duration: 0.3 }} className="col-start-1 row-start-1"><StatusPill status="PENDING" /></m.span>
              <m.span animate={{ opacity: accepted ? 1 : 0 }} transition={{ duration: 0.3 }} className="col-start-1 row-start-1"><StatusPill status="ACCEPTED" /></m.span>
            </span>
          </div>
          <m.p
            animate={{ opacity: accepted ? 1 : 0, y: accepted ? 0 : 6 }}
            transition={{ duration: 0.5, ease: EASE }}
            className="mt-3 mb-0 flex items-center gap-2 border-t pt-3 text-[0.9375rem] font-semibold"
          >
            <Check className="size-4 text-ok-ink" /> Thursday, 11:30
            <span className="font-normal text-muted-foreground">set by the faculty</span>
          </m.p>
        </Panel>
      </div>
    </div>
  );
}

export function Hero() {
  const reduce = useReducedMotion();
  const { isAuthenticated, role } = useAuth();
  return (
    <section aria-labelledby="hero-title" className="mx-auto grid max-w-[1240px] items-center gap-12 px-[clamp(1rem,4vw,2.5rem)] pt-[clamp(2.5rem,6vw,5rem)] pb-[clamp(3rem,7vw,6rem)] lg:grid-cols-[1.15fr_1fr] lg:gap-8">
      <div>
        <div id="hero-title"><Headline reduce={reduce} /></div>
        <m.p
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.55, ease: EASE }}
          className="mt-7 mb-0 max-w-[52ch] text-[1.125rem] leading-relaxed text-ink-2"
        >
          Campus Connect keeps mentoring inside the college. Chat with the faculty for your class, request meetings they schedule, and let Admin's class structure decide who can reach whom.
        </m.p>
        <m.div
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.7, ease: EASE }}
          className="mt-8 flex flex-wrap items-center gap-3"
        >
          {isAuthenticated ? (
            <Button asChild size="lg"><Link to={homeFor(role)}>Open your dashboard</Link></Button>
          ) : (
            <>
              <Button asChild size="lg"><Link to="/login">Sign in</Link></Button>
              <CreateAccountMenu size="lg" align="start" />
            </>
          )}
        </m.div>
        <m.p
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1, duration: 0.6 }}
          className="mt-5 mb-0 text-sm text-muted-foreground"
        >
          For students, faculty and administrators of the college. Admin accounts are created by an existing admin.
        </m.p>
      </div>
      <HeroStage reduce={reduce} />
    </section>
  );
}
