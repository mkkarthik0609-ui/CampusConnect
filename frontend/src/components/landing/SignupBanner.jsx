import { useRef } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { CreateAccountMenu } from "@/components/landing/CreateAccountMenu";
import { useReveal } from "@/lib/motion/useReveal";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";

const PILL = "h-12 rounded-full px-7 text-base";
const LIGHT = "border-nav-ink bg-nav-ink text-nav hover:border-white hover:bg-white";

/** Dark closing band: a clean typographic block with pill buttons (copy from the original closing section). */
export function SignupBanner() {
  const root = useRef(null);
  const { isAuthenticated, role, status } = useAuth();
  useReveal(root);

  return (
    <section ref={root} aria-labelledby="closing-title" className="relative isolate overflow-hidden bg-nav text-nav-ink">
      <div aria-hidden="true" className="lp-dots absolute inset-0 -z-10" />
      <div aria-hidden="true" className="absolute inset-0 -z-10 bg-[radial-gradient(50%_70%_at_50%_100%,rgba(255,255,255,0.07),transparent)]" />
      <div className="lp-wrap flex flex-col items-center py-[clamp(4rem,7vw,6.5rem)] text-center">
        <h2 id="closing-title" data-reveal className="m-0 font-display text-[clamp(1.75rem,1.2rem+1.6vw,2.5rem)] leading-[1.1] font-medium tracking-[-0.035em] text-white">
          Start with your class.
        </h2>
        <p data-reveal className="mt-4 mb-8 max-w-[46ch] text-[1.0625rem] text-nav-ink">
          Students pick their section at sign-up. Faculty register with their Faculty ID and wait for Admin to assign classes.
        </p>
        <div data-reveal className="flex flex-wrap items-center justify-center gap-3">
          {status === "loading" ? null : isAuthenticated ? (
            <Button asChild size="lg" className={`${PILL} ${LIGHT}`}><Link to={homeFor(role)}>Open your dashboard</Link></Button>
          ) : (
            <>
              <CreateAccountMenu size="lg" align="center" className={`${PILL} ${LIGHT}`} />
              <Button asChild size="lg" variant="outline" className={`${PILL} border-white/30 text-nav-ink hover:border-white hover:bg-white/10 hover:text-white`}><Link to="/login">Sign in</Link></Button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
