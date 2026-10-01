import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

/**
 * Screen-reader announcement of client-side navigation (the page does not reload, so nothing else speaks).
 * Reads document.title after the new page has set it (PageHeader / usePageTitle).
 */
export function RouteAnnouncer() {
  const { pathname } = useLocation();
  const [message, setMessage] = useState("");

  useEffect(() => {
    const id = window.setTimeout(() => setMessage(document.title || ""), 150);
    return () => window.clearTimeout(id);
  }, [pathname]);

  return (
    <div aria-live="polite" aria-atomic="true" role="status" className="sr-only">
      {message}
    </div>
  );
}
