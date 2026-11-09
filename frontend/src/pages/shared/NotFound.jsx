import { Suspense, lazy } from "react";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { ErrorPageLayout, PageLink } from "@/components/app/ErrorPageLayout";
import { homeFor } from "@/lib/nav";
import { PageLoader } from "@/components/app/PageLoader";

const AppShell = lazy(() => import("@/components/app/AppShell").then((m) => ({ default: m.AppShell })));

/** 404. Used inside the shell (signed in) and standalone (public catch-all). */
export function NotFound({ standalone = false }) {
  const { isAuthenticated, role } = useAuth();
  return (
    <ErrorPageLayout
      code={404}
      title="We can't find that page"
      standalone={standalone}
      actions={
        <>
          <Button asChild size="pill"><PageLink to={isAuthenticated ? homeFor(role) : "/"}>{isAuthenticated ? "Go to dashboard" : "Back to home"} <ArrowRight aria-hidden="true" /></PageLink></Button>
          {!isAuthenticated ? <Button asChild size="pill" variant="outline"><PageLink to="/login">Sign in</PageLink></Button> : null}
        </>
      }
    >
      <p>The link may be out of date, or the page may have moved. Check the address, or use the menu to find what you need.</p>
    </ErrorPageLayout>
  );
}

/** Route element for the catch-all: standalone when signed out, inside the shell when signed in. */
export default function NotFoundRoute() {
  const { status } = useAuth();
  if (status === "loading") return <PageLoader />;
  if (status === "authenticated") {
    return (
      <Suspense fallback={<PageLoader />}>
        <AppShell><NotFound /></AppShell>
      </Suspense>
    );
  }
  return <NotFound standalone />;
}
