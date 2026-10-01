import { Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { ErrorPageLayout } from "@/components/app/ErrorPageLayout";
import { ROLE_LABEL, homeFor } from "@/lib/nav";

/** 403. Rendered by <RequireRole> inside the shell, or directly when an API call answers 403. */
export function Forbidden({ message }) {
  const { role } = useAuth();
  return (
    <ErrorPageLayout
      code={403}
      title="This area isn't open to you"
      actions={<Button asChild><Link to={homeFor(role)}>Back to your dashboard</Link></Button>}
    >
      <p>{message || `Your ${ROLE_LABEL[role]?.toLowerCase() || "account"} role doesn't include this page. If you think that's a mistake, ask an administrator.`}</p>
    </ErrorPageLayout>
  );
}

export default Forbidden;
