import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Full-viewport hero with a muted background video that plays by itself on load (once, then holds its last frame).
 * The page scrolls normally; scrolling only adds a light parallax on the video (transform-only, rAF-throttled).
 * Reduced motion: no autoplay and no parallax, the video shows a late frame. Video blocked / failed: plain dark hero.
 *
 * Props: videoSrc, title (the h1), tagline, scrollHint, children (e.g. CTA buttons, shown under the title).
 */
export default function AutoplayVideoHero({ videoSrc, title, tagline, scrollHint = "SCROLL", children, className }) {
  const sectionRef = useRef(null);
  const videoRef = useRef(null);
  const hintRef = useRef(null);
  const [state, setState] = useState("loading"); // loading | ready | failed
  const [cycle, setCycle] = useState(0); // bumps each time the hero re-enters the viewport: remounts the text so it animates in again
  const [reduce] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;
    const onReady = () => {
      setState("ready");
      if (reduce) video.currentTime = (video.duration || 0) * 0.92;
    };
    const onError = () => setState("failed");
    video.addEventListener("loadeddata", onReady);
    video.addEventListener("error", onError);
    if (video.readyState >= 2) onReady();
    // Autoplay can be refused (data saver, iOS low-power): the first frame still shows, nothing else breaks.
    if (!reduce) video.play?.()?.catch(() => {});

    // Seamless loop, no frozen frame: the video fades out over its last second, restarts the moment it ends, and fades
    // back in only once frame 0 is decoded (so there is never a flash of the old frame). Replays from 0 whenever the
    // hero scrolls back into view and pauses while off-screen (saves battery / decoding).
    let visible = true;
    let firstCheck = true;
    let fadingOut = false;
    const restart = () => {
      fadingOut = false;
      const go = () => {
        video.style.opacity = "";
        video.play?.()?.catch(() => {});
      };
      if (video.currentTime === 0) { go(); return; }
      video.addEventListener("seeked", go, { once: true });
      video.currentTime = 0;
    };
    const onTime = () => {
      if (fadingOut || !visible || !video.duration) return;
      if (video.duration - video.currentTime < 1) { fadingOut = true; video.style.opacity = "0"; }
    };
    const onEnded = () => { if (visible) restart(); };
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("ended", onEnded);
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      const initial = firstCheck;
      firstCheck = false;
      if (!visible) { video.pause(); return; }
      if (initial) return; // first paint: autoplay already started it
      setCycle((c) => c + 1);
      restart();
    }, { threshold: 0.35 });
    if (!reduce && sectionRef.current) io.observe(sectionRef.current);

    let raf = 0;
    const onScroll = () => {
      if (raf || reduce) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const y = Math.min(window.scrollY, window.innerHeight);
        video.style.transform = `translate3d(0, ${y * 0.2}px, 0) scale(1.08)`;
        if (hintRef.current) hintRef.current.style.opacity = y > 40 ? "0" : "";
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      io.disconnect();
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("ended", onEnded);
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      video.removeEventListener("loadeddata", onReady);
      video.removeEventListener("error", onError);
    };
  }, [reduce]);

  return (
    <section id="top" ref={sectionRef} aria-labelledby="hero-title" className={cn("relative isolate flex min-h-svh w-full items-center justify-center overflow-hidden bg-nav px-[6%] py-28 text-center text-white", className)}>
      <video
        ref={videoRef}
        src={videoSrc}
        muted
        playsInline
        autoPlay={!reduce}
        preload="auto"
        aria-hidden="true"
        tabIndex={-1}
        className={cn("pointer-events-none absolute inset-0 -z-20 size-full scale-[1.08] object-cover will-change-transform transition-opacity duration-[900ms] ease-in-out", state === "ready" ? "opacity-100" : "opacity-0")}
      />
      {/* Legibility: an even dark wash, a heavier vignette behind the text block, and a darker top/bottom for the header and hint. */}
      <div aria-hidden="true" className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,rgba(10,10,11,0.7),rgba(10,10,11,0.5)_35%,rgba(10,10,11,0.55)_65%,rgba(10,10,11,0.88))]" />
      <div aria-hidden="true" className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_65%_50%_at_50%_50%,rgba(10,10,11,0.6),transparent_80%)]" />

      <div key={cycle} className="flex flex-col items-center gap-6">
        <h1 id="hero-title" className="animate-rise m-0 max-w-[22ch] font-display text-[clamp(2.1rem,1.3rem+2.6vw,3.5rem)] leading-[1.05] font-medium tracking-[-0.04em] text-balance text-white! [animation-delay:0.3s] [text-shadow:0_2px_3px_rgba(0,0,0,0.7),0_6px_28px_rgba(0,0,0,0.75)]">
          {title}
        </h1>
        {children ? <div className="animate-rise [animation-delay:0.6s]">{children}</div> : null}
        {tagline ? <p className="animate-rise m-0 max-w-[48ch] text-sm font-medium text-white/90 [animation-delay:0.85s] [text-shadow:0_1px_2px_rgba(0,0,0,0.85),0_4px_18px_rgba(0,0,0,0.8)]">{tagline}</p> : null}
      </div>

      <div ref={hintRef} aria-hidden="true" className="pointer-events-none absolute bottom-[clamp(20px,5vh,40px)] left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 text-xs font-semibold tracking-[0.3em] text-white/70 transition-opacity duration-300">
        <span>{scrollHint}</span>
        <svg width="14" height="18" viewBox="0 0 14 18" className="animate-bounce motion-reduce:animate-none" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M7 1v16M2 12l5 5 5-5" /></svg>
      </div>
    </section>
  );
}
