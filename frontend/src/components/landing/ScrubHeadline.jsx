import { useLayoutEffect, useRef } from "react";
import { gsap, scrollFx } from "@/lib/motion/gsap";
import { Words } from "@/lib/motion/Words";

// The original landing's hero paragraph, verbatim.
const TEXT = "Campus Connect keeps mentoring inside the college. Chat with the faculty for your class, request meetings they schedule, and let Admin's class structure decide who can reach whom.";

/** Pinned paragraph: while you scroll, the words go from dim to full contrast. Static, fully lit under reduced motion. */
export function ScrubHeadline() {
  const root = useRef(null);

  useLayoutEffect(
    () =>
      scrollFx(root.current, () => {
        const words = gsap.utils.toArray(".w");
        gsap.set(words, { opacity: 0.18 });
        gsap.to(words, {
          opacity: 1,
          ease: "none",
          stagger: 0.5,
          duration: 1,
          scrollTrigger: { trigger: root.current, start: "top top", end: "+=100%", pin: true, scrub: 0.5 },
        });
      }),
    [],
  );

  return (
    <section id="statement" ref={root} aria-label="About Campus Connect" className="relative flex min-h-svh items-center bg-background">
      <div className="lp-wrap py-20">
        <p className="m-0 max-w-[40ch] font-display text-[clamp(1.25rem,0.95rem+1vw,2rem)] leading-[1.3] font-medium tracking-[-0.02em] text-balance text-foreground">
          <Words text={TEXT} />
        </p>
      </div>
    </section>
  );
}
