import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// Registered exactly once for the whole app: import gsap from here, never from "gsap" directly.
gsap.registerPlugin(ScrollTrigger);
ScrollTrigger.config({ ignoreMobileResize: true });

export { gsap, ScrollTrigger };

export const NO_REDUCED_MOTION = "(prefers-reduced-motion: no-preference)";

export const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Scoped scroll effects. `setup({ wide })` runs only when the visitor has NOT asked for reduced motion
 * (otherwise the DOM stays in its static final state) and is re-run / reverted when the preference or
 * the breakpoint changes. Selectors inside `setup` are scoped to `scope`.
 * Use as: useLayoutEffect(() => scrollFx(ref.current, ({ wide }) => { ... }), []);
 */
export function scrollFx(scope, setup) {
  const mm = gsap.matchMedia(scope);
  mm.add({ motion: NO_REDUCED_MOTION, wide: "(min-width: 60rem)" }, (ctx) => (ctx.conditions.motion ? setup(ctx.conditions) : undefined));
  return () => mm.revert();
}
