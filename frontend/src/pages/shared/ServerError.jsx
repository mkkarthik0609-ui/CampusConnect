import { Link, useRouteError } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ErrorPageLayout } from "@/components/app/ErrorPageLayout";
import { ApiError } from "@/lib/api";

/**
 * 500 / "can't reach the server". Also the router's errorElement (uncaught render errors, failed lazy chunks).
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
          <Button onClick={onRetry || (() => window.location.reload())}>Try again</Button>
          <Button asChild variant="outline"><Link to="/">Back to home</Link></Button>
        </>
      }
    >
      <p>{message || "The page could not be shown. Nothing you entered has been lost on the server. Try again, and if it keeps happening let an administrator know."}</p>
    </ErrorPageLayout>
  );
}

/** React Router errorElement. */
export function RouteError() {
  const error = useRouteError();
  const chunkFailed = /dynamically imported module|Importing a module script failed|Loading chunk/i.test(String(error?.message || ""));
  if (import.meta.env.DEV) console.error(error);
  return (
    <ServerErrorPage
      standalone
      title={chunkFailed ? "A new version of Campus Connect is available" : undefined}
      message={chunkFailed ? "Reload the page to pick up the latest version." : error instanceof ApiError ? error.message : undefined}
      onRetry={() => window.location.reload()}
    />
  );
}

export default ServerErrorPage;
