import { useLayoutEffect, useRef } from "react";
import { gsap, scrollFx } from "@/lib/motion/gsap";
import { ChatMock, ClassMock, MeetingMock } from "@/components/landing/mocks";

// Copy is the original "How it works" story, verbatim.
const SLIDES = [
  {
    label: "Admin draws the map",
    body: "Branch, department, year and section are defined once by the administrator. A student picks a real section at sign-up, so “3rd Year A” always means the same group of people.",
    Mock: ClassMock,
  },
  {
    label: "Mentor-Connect follows the map",
    body: "Students and faculty can message each other only when the class structure connects them. Attach a PDF, an image or a DOCX, and fix a typo until the other person has seen the message.",
    Mock: ChatMock,
  },
  {
    label: "A request has a clear path",
    body: "The student asks. The faculty member accepts or rejects in writing and types the time. Afterwards either side marks it completed, or cancels with a reason that both keep.",
    Mock: MeetingMock,
  },
];

/**
 * Pinned showcase (inverse surface). Scroll progress cross-fades three labelled product scenes.
 * Motion: the labels + a copy of each scene's text sit in the left column (aria-hidden), the mocks cross-fade on the
 * right, the real <h3>/<p> in each slide are screen-reader only. Reduced motion: no pin, slides stack with visible text.
 */
export function Showcase() {
  const root = useRef(null);

  useLayoutEffect(
    () =>
      scrollFx(root.current, () => {
        const slides = gsap.utils.toArray("[data-slide]");
        const labels = gsap.utils.toArray("[data-label]");
        const bodies = gsap.utils.toArray("[data-body]");
        gsap.set([...slides, ...bodies].filter((_, i) => i % 3 !== 0), { opacity: 0 });
        gsap.set(slides.slice(1), { yPercent: 7 });
        gsap.set(labels.slice(1), { opacity: 0.35 });
        const tl = gsap.timeline({
          defaults: { ease: "power2.inOut" },
          scrollTrigger: { id: "showcase", trigger: root.current, start: "top top", end: "+=300%", pin: true, scrub: 0.6, anticipatePin: 1 },
        });
        tl.to("[data-bar]", { scaleX: 1, ease: "none", duration: 3 }, 0);
        [1, 2].forEach((i) => {
          tl.to([slides[i - 1], bodies[i - 1]], { opacity: 0, yPercent: (j) => (j === 0 ? -7 : 0), duration: 0.4 }, i - 0.25)
            .to([slides[i], bodies[i]], { opacity: 1, yPercent: 0, duration: 0.4 }, i - 0.1)
            .to(labels[i - 1], { opacity: 0.35, duration: 0.3 }, i - 0.25)
            .to(labels[i], { opacity: 1, duration: 0.3 }, i - 0.1);
        });
      }),
    [],
  );

  return (
    <section id="structure" ref={root} aria-labelledby="structure-title" className="relative bg-ink text-background motion-safe:h-svh motion-safe:min-h-[34rem]">
      <div className="lp-wrap grid gap-10 py-[clamp(4rem,7vw,7rem)] motion-safe:h-full motion-safe:content-center motion-safe:gap-4 motion-safe:py-14 lg:grid-cols-[5fr_7fr] lg:gap-14 motion-safe:lg:gap-14">
        <div className="min-w-0">
          <h2 id="structure-title" className="m-0 font-display text-[clamp(1.5rem,1.1rem+1.4vw,2.5rem)] leading-[1.1] font-medium tracking-[-0.035em] text-background">
            One class structure decides who can reach whom
          </h2>
          <p className="mt-3 mb-0 max-w-[48ch] text-[0.9375rem] leading-relaxed text-background/75 sm:text-base max-sm:motion-safe:hidden">
            Everything in Campus Connect hangs off the same four levels. Scroll to watch a student&apos;s class turn into a conversation and a meeting.
          </p>
          <div aria-hidden="true" className="mt-5 hidden motion-safe:block lg:mt-7">
            <ol className="m-0 grid list-none gap-1.5 p-0 max-lg:grid-cols-3 max-lg:gap-2">
              {SLIDES.map((s) => (
                <li key={s.label} data-label className="font-display text-[0.6875rem] leading-tight font-medium tracking-[0.08em] uppercase sm:text-xs lg:text-[0.875rem] lg:tracking-[0.12em]">
                  {s.label}
                </li>
              ))}
            </ol>
            <div className="mt-3 h-px bg-background/20 lg:mt-4"><div data-bar className="h-full origin-left scale-x-0 bg-background" /></div>
            <div className="mt-4 grid [&>*]:col-start-1 [&>*]:row-start-1">
              {SLIDES.map((s) => (
                <p key={s.label} data-body className="m-0 max-w-[48ch] text-[0.875rem] leading-relaxed text-background/75 sm:text-base">{s.body}</p>
              ))}
            </div>
          </div>
        </div>

        <div className="relative motion-safe:h-[21rem] motion-safe:sm:h-[24rem]">
          {SLIDES.map((s, i) => (
            <article key={s.label} id={`showcase-slide-${i}`} data-slide className="grid content-center justify-items-start gap-5 motion-safe:absolute motion-safe:inset-0 motion-reduce:mb-14 motion-reduce:last:mb-0">
              <div className="motion-safe:sr-only">
                <h3 className="m-0 mb-2 font-display text-sm font-medium tracking-[0.12em] text-background uppercase">{s.label}</h3>
                <p className="m-0 max-w-[48ch] text-base leading-relaxed text-background/75">{s.body}</p>
              </div>
              <s.Mock />
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
