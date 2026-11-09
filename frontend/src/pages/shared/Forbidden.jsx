import { ArrowRight } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { ErrorPageLayout, PageLink } from "@/components/app/ErrorPageLayout";
import { ROLE_LABEL, homeFor } from "@/lib/nav";

/** 403. Rendered by <RequireRole> inside the shell, or directly when an API call answers 403. */
export function Forbidden({ message }) {
  const { role } = useAuth();
  return (
    <ErrorPageLayout
      code={403}
      title="This area isn't open to you"
      actions={<Button asChild size="pill"><PageLink to={homeFor(role)}>Back to your dashboard <ArrowRight aria-hidden="true" /></PageLink></Button>}
    >
      <p>{message || `Your ${ROLE_LABEL[role]?.toLowerCase() || "account"} role doesn't include this page. If you think that's a mistake, ask an administrator.`}</p>
    </ErrorPageLayout>
  );
}

export default Forbidden;
