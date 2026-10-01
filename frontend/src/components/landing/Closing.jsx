import { Link } from "react-router-dom";
import { Brand } from "@/components/app/BrandMark";
import { Button } from "@/components/ui/button";
import { CreateAccountMenu } from "@/components/landing/LandingHeader";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";

export function Closing() {
  const { isAuthenticated, role } = useAuth();
  return (
    <>
      <section aria-labelledby="closing-title" className="bg-nav text-nav-ink">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-end justify-between gap-x-12 gap-y-8 px-[clamp(1rem,4vw,2.5rem)] py-[clamp(3rem,7vw,5.5rem)]">
          <div className="max-w-[34rem]">
            <h2 id="closing-title" className="m-0 font-display text-[clamp(2rem,1.3rem+3vw,3.6rem)] leading-[1.02] font-extrabold tracking-[-0.03em] text-white">
              Start with your class.
            </h2>
            <p className="mt-4 mb-0 text-[1.0625rem] text-nav-ink">
              Students pick their section at sign-up. Faculty register with their Faculty ID and wait for Admin to assign classes.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {isAuthenticated ? (
              <Button asChild size="lg" variant="saffron"><Link to={homeFor(role)}>Open your dashboard</Link></Button>
            ) : (
              <>
                <Button asChild size="lg" variant="saffron"><Link to="/login">Sign in</Link></Button>
                <CreateAccountMenu size="lg" variant="outline" align="end" className="border-white/30 bg-transparent text-white hover:border-white hover:bg-white/10 hover:text-white" />
              </>
            )}
          </div>
        </div>
      </section>
      <footer className="bg-nav text-nav-muted">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-4 border-t border-nav-line px-[clamp(1rem,4vw,2.5rem)] py-6 text-sm">
          <Brand to="/" size={28} wordClassName="text-white text-[1.05rem]" />
          <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-1">
            <Link to="/login" className="inline-flex min-h-8 items-center text-nav-ink hover:text-white">Sign in</Link>
            <Link to="/signup/student" className="inline-flex min-h-8 items-center text-nav-ink hover:text-white">Student sign-up</Link>
            <Link to="/signup/faculty" className="inline-flex min-h-8 items-center text-nav-ink hover:text-white">Faculty sign-up</Link>
          </nav>
          <p className="m-0">Students, faculty and administrators of the college.</p>
        </div>
      </footer>
    </>
  );
}
