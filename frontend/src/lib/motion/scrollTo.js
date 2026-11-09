import { ScrollTrigger, prefersReducedMotion } from "./gsap";

/** Smooth-scroll to a section id; for the pinned showcase, `slide` (0-2) lands on that step of the scrub. */
export function goTo(id, slide) {
  const behavior = prefersReducedMotion() ? "auto" : "smooth";
  const st = slide != null ? ScrollTrigger.getById("showcase") : null;
  if (st) {
    window.scrollTo({ top: st.start + (st.end - st.start) * ((slide + 0.5) / 3), behavior });
    return;
  }
  const el = document.getElementById(slide != null ? `showcase-slide-${slide}` : id);
  el?.scrollIntoView({ behavior, block: "start" });
}
