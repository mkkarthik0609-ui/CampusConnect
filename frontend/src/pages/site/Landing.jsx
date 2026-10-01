import { LazyMotion, domAnimation } from "motion/react";
import { LandingHeader } from "@/components/landing/LandingHeader";
import { Hero } from "@/components/landing/Hero";
import { Structure } from "@/components/landing/Structure";
import { Roles } from "@/components/landing/Roles";
import { Rules } from "@/components/landing/Rules";
import { Closing } from "@/components/landing/Closing";
import { usePageTitle } from "@/hooks/usePageTitle";

/**
 * Public landing page (/). Motion is confined to src/components/landing (Framer Motion via `motion/react`,
 * loaded only with this route's chunk). Every animated piece honours prefers-reduced-motion.
 */
export default function Landing() {
  usePageTitle("");
  return (
    <LazyMotion features={domAnimation} strict>
      <div className="min-h-dvh bg-background">
        <a className="skip-link" href="#main">Skip to main content</a>
        <LandingHeader />
        <main id="main" tabIndex={-1}>
          <Hero />
          <Structure />
          <Roles />
          <Rules />
        </main>
        <Closing />
      </div>
    </LazyMotion>
  );
}
