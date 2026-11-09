import { ArrowRight, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorPageLayout, PageLink } from "@/components/app/ErrorPageLayout";

/**
 * 500 / "can't reach the server". Used by the route and global error boundaries (components/app/ErrorBoundary.jsx)
 * and by the auth gate. Works inside and outside the router.
 *   <ServerErrorPage standalone onRetry={fn} title="..." message="..." />
 */
export function ServerErrorPage({ standalone = false, onRetry, title = "Something went wrong on our side", message }) {
  return (
    <ErrorPageLayout
      code={500}
      title={title}
      standalone={standalone}
      actions={
        <>
          <Button size="pill" onClick={onRetry || (() => window.location.reload())}><RotateCw aria-hidden="true" /> Try again</Button>
          <Button asChild size="pill" variant="outline"><PageLink to="/">Back to home <ArrowRight aria-hidden="true" /></PageLink></Button>
        </>
      }
    >
      <p>{message || "The page could not be shown. Nothing you entered has been lost on the server. Try again, and if it keeps happening let an administrator know."}</p>
    </ErrorPageLayout>
  );
}

export default ServerErrorPage;
