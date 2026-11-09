import { ArrowRight, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorPageLayout, PageLink } from "@/components/app/ErrorPageLayout";

/** Shown instead of a crash when the browser is offline (the error boundaries pick it when navigator.onLine is false). */
export default function Offline({ standalone = true, onRetry }) {
  return (
    <ErrorPageLayout
      code="OFF"
      title="You're offline"
      documentTitle="Offline"
      standalone={standalone}
      actions={
        <>
          <Button size="pill" onClick={onRetry || (() => window.location.reload())}><RotateCw aria-hidden="true" /> Try again</Button>
          <Button asChild size="pill" variant="outline"><PageLink to="/">Back to home <ArrowRight aria-hidden="true" /></PageLink></Button>
        </>
      }
    >
      <p>CampusConnect can't reach the internet right now. Check your connection - the page will pick up where you left off once you are back online.</p>
    </ErrorPageLayout>
  );
}
