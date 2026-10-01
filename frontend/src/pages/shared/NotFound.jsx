import { Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { ErrorPageLayout } from "@/components/app/ErrorPageLayout";
import { homeFor } from "@/lib/nav";
import { AppShell } from "@/components/app/AppShell";
import { PageLoader } from "@/components/app/PageLoader";

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
          <Button asChild><Link to={isAuthenticated ? homeFor(role) : "/"}>{isAuthenticated ? "Go to dashboard" : "Back to home"}</Link></Button>
          {!isAuthenticated ? <Button asChild variant="outline"><Link to="/login">Sign in</Link></Button> : null}
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
  if (status === "authenticated") return <AppShell><NotFound /></AppShell>;
  return <NotFound standalone />;
}
