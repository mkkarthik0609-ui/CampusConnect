import { Loader2 } from "lucide-react";
import { BrandMark } from "@/components/app/BrandMark";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function Spinner({ className, label }) {
  return (
    <span role={label ? "status" : undefined} className="inline-flex items-center">
      <Loader2 aria-hidden="true" className={cn("size-4 animate-spin", className)} />
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}

/** Full-screen loader for the first session check. */
export function PageLoader({ label = "Loading" }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-background" role="status" aria-live="polite">
      <div className="flex flex-col items-center gap-4">
        <BrandMark size={44} className="animate-pulse motion-reduce:animate-none" />
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

/** Suspense fallback inside the shell while a lazy page chunk loads. Reserves height to avoid layout shift. */
export function RouteFallback() {
  return (
    <div className="grid gap-4" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">Loading page</span>
      <Skeleton className="h-9 w-56" />
      <Skeleton className="h-4 w-80 max-w-full" />
      <Skeleton className="mt-4 h-40 w-full" />
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
