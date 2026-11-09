import { useEffect } from "react";
import { LandingHeader } from "@/components/landing/LandingHeader";
import { Hero } from "@/components/landing/Hero";
import { ScrubHeadline } from "@/components/landing/ScrubHeadline";
import { Showcase } from "@/components/landing/Showcase";
import { Statement } from "@/components/landing/Statement";
import { Roles } from "@/components/landing/Roles";
import { SignupBanner } from "@/components/landing/SignupBanner";
import { LandingFooter } from "@/components/landing/LandingFooter";
import { ScrollTrigger } from "@/lib/motion/gsap";
import { usePageTitle } from "@/hooks/usePageTitle";

/**
 * Public landing page (/). GSAP ScrollTrigger scenes live in each section (created in a gsap.matchMedia scope and
 * reverted on unmount); the hero's three.js scene is a lazy chunk. Reduced motion renders every section in its final state.
 */
export default function Landing() {
  usePageTitle("");

  // Web fonts change text metrics: re-measure every pin / trigger once they are in.
  useEffect(() => {
    let live = true;
    document.fonts?.ready.then(() => live && ScrollTrigger.refresh());
    return () => { live = false; };
  }, []);

  return (
    <div className="min-h-dvh overflow-x-clip bg-background">
      <a className="skip-link" href="#main">Skip to main content</a>
      <LandingHeader />
      <main id="main" tabIndex={-1}>
        <Hero />
        <ScrubHeadline />
        <Showcase />
        <Statement />
        <Roles />
        <SignupBanner />
      </main>
      <LandingFooter />
    </div>
  );
}
