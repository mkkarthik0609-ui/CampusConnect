import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import AutoplayVideoHero from "@/components/ui/autoplay-video-hero";
import { CreateAccountMenu } from "@/components/landing/CreateAccountMenu";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";

const HEADLINE = "Every student mapped to the faculty";
const NOTE = "For students, faculty and administrators of the college. Admin accounts are created by an existing admin.";
// Self-hosted (public/hero.mp4): the production CSP (vercel.json, default-src 'self') blocks third-party media.
const HERO_VIDEO = "/hero.mp4";

function HeroCtas() {
  const { isAuthenticated, role, status } = useAuth();
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      {status === "loading" ? null : isAuthenticated ? (
        <Button asChild size="lg" className="border-nav-ink bg-nav-ink text-nav hover:border-white hover:bg-white"><Link to={homeFor(role)}>Open your dashboard</Link></Button>
      ) : (
        <>
          <CreateAccountMenu size="lg" align="start" className="border-nav-ink bg-nav-ink text-nav hover:border-white hover:bg-white" />
          <Button asChild size="lg" variant="outline" className="border-white/40 bg-black/45 text-white backdrop-blur-sm hover:border-white hover:bg-black/60 hover:text-white"><Link to="/login">Sign in</Link></Button>
        </>
      )}
    </div>
  );
}

/** Autoplaying, looping video hero: headline, sign-up / sign-in buttons and the audience note over the clip. */
export function Hero() {
  return (
    <AutoplayVideoHero videoSrc={HERO_VIDEO} title={HEADLINE} tagline={NOTE}>
      <HeroCtas />
    </AutoplayVideoHero>
  );
}
