import { Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouteProgress } from "@/components/app/RouteProgress";
import { cn } from "@/lib/utils";

export function Spinner({ className, label }) {
  return (
    <span role={label ? "status" : undefined} className="inline-flex items-center">
      <Loader2 aria-hidden="true" className={cn("size-4 animate-spin", className)} />
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}

/**
 * The logo mark drawing itself: both hooks are stroked in (pathLength=1 + dashoffset, see .loader-mark in index.css),
 * then the mark breathes. Paths mirror BrandMark.jsx; reduced motion shows the finished mark.
 */
export function LogoDraw({ size = 64, strokeWidth = 5, className }) {
  return (
    <svg
      className={cn("loader-mark", className)}
      width={size * 1.2}
      height={size}
      viewBox="0 0 120 100"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path pathLength="1" d="M62 10C38 13 12 26 12 50c0 18 14 26 32 22l22-10" />
      <path pathLength="1" d="M54 40l20-9c18-7 34 3 34 21 0 22-26 38-56 40" />
    </svg>
  );
}

/** Full-screen loader: first session check, and the Suspense fallback for lazy routes. */
export function PageLoader({ label = "Loading" }) {
  useRouteProgress();
  return (
    <div className="grid min-h-dvh place-items-center bg-background text-foreground" role="status" aria-live="polite">
      <div className="flex flex-col items-center gap-6">
        <LogoDraw size={72} />
        <p className="micro m-0 text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

/** Suspense fallback inside the shell while a lazy page chunk loads. Reserves height to avoid layout shift. */
export function RouteFallback() {
  useRouteProgress();
  return (
    <div className="grid gap-4" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">Loading page</span>
      <Skeleton className="h-12 w-72 max-w-full" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <Skeleton className="mt-6 h-44 w-full" />
    </div>
  );
}

/** A generic list/card skeleton for data that is still loading. */
export function ListSkeleton({ rows = 4, className }) {
  return (
    <div className={cn("grid gap-3", className)} role="status" aria-busy="true">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  );
}
