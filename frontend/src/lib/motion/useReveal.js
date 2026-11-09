import { useLayoutEffect } from "react";
import { gsap, scrollFx, ScrollTrigger } from "./gsap";

/**
 * Fade-and-rise every `[data-reveal]` descendant of `ref` the first time it scrolls into view.
 * Static (fully visible) under reduced motion. Do not use inside a pinned section.
 */
export function useReveal(ref) {
  useLayoutEffect(
    () =>
      scrollFx(ref.current, () => {
        const els = gsap.utils.toArray("[data-reveal]");
        gsap.set(els, { opacity: 0, y: 36 });
        ScrollTrigger.batch(els, {
          start: "top 88%",
          once: true,
          onEnter: (batch) => gsap.to(batch, { opacity: 1, y: 0, duration: 0.9, ease: "expo.out", stagger: 0.09, overwrite: true }),
        });
      }),
    [ref],
  );
}
