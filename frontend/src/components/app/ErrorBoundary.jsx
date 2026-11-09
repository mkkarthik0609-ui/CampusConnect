import { Component, Suspense, lazy } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";
import { ServerErrorPage } from "@/pages/shared/ServerError";
import Offline from "@/pages/shared/Offline";
import { ApiError } from "@/lib/api";

// Lazy so this (always-loaded) boundary does not pull the app shell into the entry chunk.
const NotFound = lazy(() => import("@/pages/shared/NotFound").then((m) => ({ default: m.NotFound })));

const CHUNK_FAILED = /dynamically imported module|Importing a module script failed|Loading chunk|error loading dynamically/i;

/** Picks the right full-page error for a thrown value: offline, stale chunk, 404 response, or a generic 500. */
function ErrorScreen({ error, standalone, onRetry }) {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return <Offline standalone={standalone} onRetry={onRetry} />;
  if (isRouteErrorResponse(error) && error.status === 404) return <Suspense fallback={null}><NotFound standalone={standalone} /></Suspense>;
  const chunkFailed = CHUNK_FAILED.test(String(error?.message || ""));
  return (
    <ServerErrorPage
      standalone={standalone}
      title={chunkFailed ? "A new version of CampusConnect is available" : undefined}
      message={chunkFailed ? "Reload the page to pick up the latest version." : error instanceof ApiError ? error.message : undefined}
      onRetry={onRetry}
    />
  );
}

/**
 * react-router `errorElement` for routes. `inShell` keeps the sidebar and renders the error in the page area
 * (used under the AppShell); otherwise it is a standalone full page. "Try again" reloads the page.
 */
export function RouteErrorBoundary({ inShell = false }) {
  const error = useRouteError();
  if (import.meta.env.DEV) console.error(error);
  return <ErrorScreen error={error} standalone={!inShell} onRetry={() => window.location.reload()} />;
}

/**
 * Global boundary (App.jsx) for anything that escapes the router: providers, the shell, the error page itself.
 * "Try again" first re-renders the tree; if that throws again the next click reloads.
 */
export class AppErrorBoundary extends Component {
  state = { error: null, retried: false };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    if (import.meta.env.DEV) console.error(error, info?.componentStack);
  }

  retry = () => {
    if (this.state.retried) window.location.reload();
    else this.setState({ error: null, retried: true });
  };

  render() {
    if (!this.state.error) return this.props.children;
    return <ErrorScreen error={this.state.error} standalone onRetry={this.retry} />;
  }
}
