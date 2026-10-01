import { Link } from "react-router-dom";
import { ChevronDown, GraduationCap, Presentation } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Brand } from "@/components/app/BrandMark";
import { ThemeToggle } from "@/components/app/ThemeToggle";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";

/** "Create account" menu: students and faculty register differently, so the choice is explicit. */
export function CreateAccountMenu({ variant = "outline", size = "default", className, align = "end" }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={variant} size={size} className={className}>
          Create account <ChevronDown aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="min-w-60">
        <DropdownMenuItem asChild>
          <Link to="/signup/student" className="no-underline"><GraduationCap aria-hidden="true" /> I'm a student</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/signup/faculty" className="no-underline"><Presentation aria-hidden="true" /> I'm faculty</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function LandingHeader() {
  const { isAuthenticated, role, status } = useAuth();
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-background/90 backdrop-blur-[6px] supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-16 max-w-[1240px] items-center justify-between gap-3 px-[clamp(1rem,4vw,2.5rem)]">
        <Brand to="/" size={32} wordClassName="text-ink" accentClassName="text-primary" />
        <nav aria-label="Page sections" className="hidden items-center gap-1 md:flex">
          <a href="#structure" className="rounded-md px-3 py-2 text-[0.9375rem] font-semibold text-ink-2 no-underline hover:bg-primary-soft hover:text-primary-ink">How it works</a>
          <a href="#roles" className="rounded-md px-3 py-2 text-[0.9375rem] font-semibold text-ink-2 no-underline hover:bg-primary-soft hover:text-primary-ink">Who it is for</a>
          <a href="#rules" className="rounded-md px-3 py-2 text-[0.9375rem] font-semibold text-ink-2 no-underline hover:bg-primary-soft hover:text-primary-ink">House rules</a>
        </nav>
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          {status === "loading" ? null : isAuthenticated ? (
            <Button asChild><Link to={homeFor(role)}>Open dashboard</Link></Button>
          ) : (
            <>
              <Button asChild variant="ghost" className="max-[26rem]:px-3"><Link to="/login">Sign in</Link></Button>
              <CreateAccountMenu className="max-sm:hidden" />
            </>
          )}
        </div>
      </div>
    </header>
  );
}
