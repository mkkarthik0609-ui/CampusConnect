import { useLayoutEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowUp, LogIn, Mail } from "lucide-react";
import { CONTACT_EMAIL } from "@/components/landing/LandingHeader";
import { gsap, scrollFx } from "@/lib/motion/gsap";
import { goTo } from "@/lib/motion/scrollTo";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";

// Nelson Mandela, speech at the launch of Mindset Network, Johannesburg, 16 July 2003.
const QUOTE = "Education is the most powerful weapon which you can use to change the world.";

const ICON = "inline-flex size-11 items-center justify-center rounded-full border border-white/20 text-nav-ink no-underline transition-colors hover:border-white hover:bg-white/10 hover:text-white";

/** "CampusConnect" at exactly the container's width, outlined, filling in on scroll and on hover. */
function Wordmark() {
  const wrap = useRef(null);
  const txt = useRef(null);
  useLayoutEffect(() => {
    let lastWidth = 0;
    const fit = () => {
      const w = wrap.current.clientWidth;
      if (!w || w === lastWidth) return;
      lastWidth = w;
      const t = txt.current;
      t.style.fontSize = "100px";
      t.style.fontSize = `${((100 * w) / t.offsetWidth).toFixed(2)}px`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(wrap.current);
    document.fonts?.ready.then(() => { lastWidth = 0; fit(); });
    return () => ro.disconnect();
  }, []);
  return (
    <div aria-hidden="true" className="px-[clamp(1rem,4vw,2.5rem)] select-none">
      <div ref={wrap} className="overflow-hidden">
        <span ref={txt} data-wordmark className="lp-outline inline-block pb-[0.3em] font-display leading-[0.82] font-medium tracking-[-0.05em] whitespace-nowrap">CampusConnect</span>
      </div>
    </div>
  );
}

/** Reveal footer: black, fixed behind the page and uncovered as the last section scrolls away. */
export function LandingFooter() {
  const root = useRef(null);
  const { isAuthenticated, role, status } = useAuth();
  const authed = status !== "loading" && isAuthenticated;

  useLayoutEffect(
    () =>
      scrollFx(root.current, () => {
        const typed = root.current.querySelector("[data-typed]");
        const rest = root.current.querySelector("[data-rest]");
        const cite = root.current.querySelector("[data-cite]");
        typed.textContent = "";
        rest.textContent = QUOTE;
        gsap.set(cite, { opacity: 0 });
        const state = { n: 0 };
        gsap.to(state, {
          n: QUOTE.length,
          duration: QUOTE.length * 0.045,
          ease: "none",
          scrollTrigger: { trigger: root.current, start: "top 55%", once: true },
          onUpdate: () => {
            const n = Math.round(state.n);
            typed.textContent = QUOTE.slice(0, n);
            rest.textContent = QUOTE.slice(n);
          },
          onComplete: () => gsap.to(cite, { opacity: 1, duration: 0.8 }),
        });
        gsap.fromTo("[data-wordmark]", { "--lp-fs": "0%" }, { "--lp-fs": "100%", ease: "none", scrollTrigger: { trigger: root.current, start: "top 35%", end: "bottom bottom", scrub: true } });
      }),
    [],
  );

  // The fixed inner panel is not scrollable into view by focus alone: bring the page to the bottom first.
  const onFocus = () => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" });

  return (
    <footer ref={root} className="lp-reveal" onFocusCapture={onFocus}>
      <div className="lp-reveal-inner flex flex-col justify-between gap-8 overflow-hidden border-t border-nav-line bg-black pt-16 text-nav-ink sm:pt-20">
        <div className="lp-wrap grid gap-8 lg:grid-cols-[13rem_1fr] lg:gap-16">
          <nav aria-label="Footer" className="grid grid-cols-2 content-start gap-x-6 gap-y-0.5 lg:grid-cols-1">
            <a href="#structure" className="lp-link" onClick={(e) => { e.preventDefault(); goTo("structure"); }}>How it works</a>
            <a href="#roles" className="lp-link" onClick={(e) => { e.preventDefault(); goTo("roles"); }}>Who it is for</a>
            <a href="#rules" className="lp-link" onClick={(e) => { e.preventDefault(); goTo("rules"); }}>House rules</a>
            {authed ? (
              <Link to={homeFor(role)} className="lp-link">Open dashboard</Link>
            ) : (
              <>
                <Link to="/login" className="lp-link">Sign in</Link>
                <Link to="/signup/student" className="lp-link">Student sign-up</Link>
                <Link to="/signup/faculty" className="lp-link">Faculty sign-up</Link>
              </>
            )}
            <Link to="/admin-login" className="lp-link">Admin sign-in</Link>
          </nav>

          <figure className="m-0 max-w-[58rem]">
            <blockquote className="m-0">
              <p className="m-0 font-display text-[clamp(1.35rem,0.9rem+1.6vw,2.4rem)] leading-[1.2] font-light tracking-[-0.035em] text-white">
                <span className="sr-only">{QUOTE}</span>
                <span aria-hidden="true">
                  <span data-typed>{QUOTE}</span>
                  <span className="lp-caret" />
                  <span data-rest className="opacity-0" />
                </span>
              </p>
            </blockquote>
            <figcaption data-cite className="mt-4 text-[0.8125rem] font-medium tracking-[0.16em] text-nav-muted uppercase">Nelson Mandela</figcaption>
          </figure>
        </div>

        <div>
          <div className="lp-wrap mb-5 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
            <p className="m-0 text-[0.8125rem] text-nav-muted">Students, faculty and administrators of the college.</p>
            <div className="flex items-center gap-2">
              <a href={`mailto:${CONTACT_EMAIL}`} className={ICON} aria-label={`Email ${CONTACT_EMAIL}`}><Mail aria-hidden="true" className="size-[1.1rem]" /></a>
              {authed ? null : <Link to="/login" className={ICON} aria-label="Sign in"><LogIn aria-hidden="true" className="size-[1.1rem]" /></Link>}
              <button type="button" className={ICON} aria-label="Back to top" onClick={() => goTo("top")}><ArrowUp aria-hidden="true" className="size-[1.1rem]" /></button>
            </div>
          </div>
          <Wordmark />
        </div>
      </div>
    </footer>
  );
}
