import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * Loading placeholders that mirror the real layouts (same borders, row heights and grids) so nothing jumps when
 * data arrives. Every export is one announced region (role="status"); the shimmer lives in index.css under
 * `.cc-skeleton` and stops for prefers-reduced-motion.
 *
 *   {query.isPending ? <CardListSkeleton rows={3} /> : <Real/>}
 */
export function SkeletonRegion({ label = "Loading", className, children }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className={cn("cc-skeleton", className)}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

const surface = "overflow-hidden rounded-lg border bg-card shadow-sm";

/** Title + description, as PageHeader renders them. */
export function PageHeaderSkeleton({ description = true, className }) {
  return (
    <div className={cn("mb-6 grid gap-3", className)} aria-hidden="true">
      <Skeleton className="h-9 w-56 max-w-full" />
      {description ? <Skeleton className="h-4 w-80 max-w-full" /> : null}
    </div>
  );
}

function Tiles({ count = 4, className }) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 min-[44rem]:grid-cols-4", className)}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-lg border bg-card px-[1.1rem] py-4">
          <Skeleton className="h-8 w-14" />
          <Skeleton className="mt-2 h-4 w-28 max-w-full" />
        </div>
      ))}
    </div>
  );
}

/** A row of figure tiles (dashboards). */
export function StatTilesSkeleton({ count = 4, className, label = "Loading figures" }) {
  return <SkeletonRegion label={label} className={className}><Tiles count={count} /></SkeletonRegion>;
}

function ListRows({ rows = 3, avatar = true, className }) {
  return (
    <div className={cn("divide-y divide-line", surface, className)}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-4">
          {avatar ? <Skeleton className="size-9 shrink-0 rounded-full" /> : null}
          <div className="grid min-w-0 flex-1 gap-2">
            <Skeleton className="h-4 w-1/3 min-w-24" />
            <Skeleton className="h-3 w-1/2 min-w-32" />
          </div>
          <Skeleton className="h-8 w-20 shrink-0 max-sm:hidden" />
        </div>
      ))}
    </div>
  );
}

/** Divided rows inside one bordered surface (avatar + two lines), like RowList / PersonRow lists. */
export function CardListSkeleton({ rows = 3, avatar = true, className, label = "Loading" }) {
  return <SkeletonRegion label={label}><ListRows rows={rows} avatar={avatar} className={className} /></SkeletonRegion>;
}

/** Table header + rows. */
export function TableSkeleton({ rows = 5, cols = 4, className, label = "Loading table" }) {
  const grid = { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` };
  return (
    <SkeletonRegion label={label} className={cn(surface, className)}>
      <div className="grid gap-4 border-b bg-surface-2 px-4 py-3" style={grid}>
        {Array.from({ length: cols }, (_, i) => <Skeleton key={i} className="h-3 w-16" />)}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="grid items-center gap-4 border-b px-4 py-4 last:border-b-0" style={grid}>
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} className={cn("h-4", c === 0 ? "w-3/4" : "w-1/2")} />
          ))}
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Labelled inputs and a submit button, stacked. */
export function FormSkeleton({ fields = 3, className, label = "Loading form" }) {
  return (
    <SkeletonRegion label={label} className={cn("grid gap-5", className)}>
      {Array.from({ length: fields }, (_, i) => (
        <div key={i} className="grid gap-2">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-11 w-full" />
        </div>
      ))}
      <Skeleton className="h-11 w-36" />
    </SkeletonRegion>
  );
}

/** Photo + name header and a details list: profile pages. */
export function ProfileSkeleton({ details = 5, className, label = "Loading profile" }) {
  return (
    <SkeletonRegion label={label} className={cn("grid items-start gap-6 min-[64rem]:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]", className)}>
      <div className={surface}>
        <div className="flex items-center gap-5 border-b p-5">
          <Skeleton className="size-[104px] shrink-0 rounded-full" />
          <div className="grid gap-2.5">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-8 w-32" />
          </div>
        </div>
        <div className="divide-y divide-line">
          {Array.from({ length: details }, (_, i) => (
            <div key={i} className="grid gap-1.5 px-5 py-3.5 sm:grid-cols-[10rem_1fr]">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </div>
      </div>
      <div className={cn(surface, "grid gap-5 p-5")}>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-11 w-36" />
      </div>
    </SkeletonRegion>
  );
}

/** Nested rows of the academic structure / class pickers: indented levels. */
export function ClassTreeSkeleton({ branches = 3, className, label = "Loading classes" }) {
  return (
    <SkeletonRegion label={label} className={cn("grid gap-3", className)}>
      {Array.from({ length: branches }, (_, i) => (
        <div key={i} className={cn(surface, "grid gap-3 p-4")}>
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-8 w-24" />
          </div>
          {i === 0 ? (
            <div className="grid gap-2.5 border-l border-line pl-4">
              <Skeleton className="h-4 w-44" />
              <Skeleton className="ml-4 h-4 w-36" />
              <Skeleton className="ml-8 h-4 w-28" />
            </div>
          ) : null}
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Meeting requests: avatar + name + status, then reason / time lines (see MeetingCard). */
export function MeetingCardsSkeleton({ count = 3, className, label = "Loading meetings" }) {
  return (
    <SkeletonRegion label={label} className={className}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="grid gap-3 border-t border-line px-[clamp(0.9rem,2.5vw,1.4rem)] py-4 first:border-t-0">
          <div className="flex items-start gap-3">
            <Skeleton className="size-10 shrink-0 rounded-full" />
            <div className="grid min-w-0 flex-1 gap-2">
              <Skeleton className="h-4 w-44 max-w-full" />
              <Skeleton className="h-3 w-28" />
            </div>
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
          <div className="grid gap-2 sm:pl-14">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-40" />
          </div>
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Notification rows: dot + two lines. */
export function NotificationsSkeleton({ rows = 4, className, label = "Loading notifications" }) {
  return (
    <SkeletonRegion label={label} className={className}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-start gap-3 border-t border-line px-2 py-3.5 first:border-t-0">
          <Skeleton className="mt-2 size-2.5 shrink-0 rounded-full" />
          <div className="grid flex-1 gap-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Whole page: header + (optional) tiles + list. For routes that have nothing to show until data lands. */
export function PageSkeleton({ stats = false, rows = 4, className, label = "Loading page" }) {
  return (
    <SkeletonRegion label={label} className={className}>
      <PageHeaderSkeleton />
      {stats ? <Tiles className="mb-6" /> : null}
      <ListRows rows={rows} />
    </SkeletonRegion>
  );
}

/** Admin dashboard "Campus today" ledger: a bordered grid of figure cells. */
export function LedgerSkeleton({ cells = 6, className, label = "Loading figures" }) {
  return (
    <SkeletonRegion label={label} className={cn("grid gap-px overflow-hidden rounded-lg border bg-line shadow-sm sm:grid-cols-2 lg:grid-cols-3", className)}>
      {Array.from({ length: cells }, (_, i) => (
        <div key={i} className="flex items-center justify-between gap-3 bg-card px-5 py-4">
          <div className="grid gap-2.5">
            <Skeleton className="h-8 w-14" />
            <Skeleton className="h-4 w-28" />
          </div>
          <Skeleton className="size-5 rounded-full" />
        </div>
      ))}
    </SkeletonRegion>
  );
}
