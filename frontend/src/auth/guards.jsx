/**
 * Route guards. Compose them as layout routes (see src/routes.jsx):
 *
 *   <RequireAuth>            any signed-in user (wraps the AppShell)
 *   <RequireRole roles={[]}> only these roles, everyone else sees the 403 page inside the shell
 *   <GuestOnly>              /login and /signup/*: signed-in users are sent to their home
 *   <AppRedirect>            /app -> the role's home
 */
import { Navigate, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { homeFor } from "@/lib/nav";
import { safeNext } from "@/lib/format";
import { PageLoader } from "@/components/app/PageLoader";
import { ServerErrorPage } from "@/pages/shared/ServerError";
import { Forbidden } from "@/pages/shared/Forbidden";

function Gate({ children }) {
  const { status, retry } = useAuth();
  if (status === "loading") return <PageLoader label="Checking your session" />;
  if (status === "error") return <ServerErrorPage standalone onRetry={retry} title="We can't reach Campus Connect" message="The server did not answer. Check your connection and try again." />;
  return children;
}

export function RequireAuth({ children }) {
  const { status } = useAuth();
  const location = useLocation();
  return (
    <Gate>
      {status === "unauthenticated" ? (
        <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
      ) : (
        children ?? <Outlet />
      )}
    </Gate>
  );
}

export function RequireRole({ roles, children }) {
  const { role } = useAuth();
  if (!roles.includes(role)) return <Forbidden />;
  return children ?? <Outlet />;
}

export function GuestOnly({ children }) {
  const { status, role } = useAuth();
  const [params] = useSearchParams();
  return (
    <Gate>
      {status === "authenticated" ? <Navigate to={safeNext(params.get("next"), homeFor(role))} replace /> : children ?? <Outlet />}
    </Gate>
  );
}

export function AppRedirect() {
  const { status, role } = useAuth();
  return (
    <Gate>
      <Navigate to={status === "authenticated" ? homeFor(role) : "/login"} replace />
    </Gate>
  );
}
