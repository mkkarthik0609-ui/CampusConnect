import { useId } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { UserAvatar } from "@/components/app/UserAvatar";
import { StatusPill } from "@/components/app/StatusPill";
import { Notice } from "@/components/app/Notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Avatar + name, with an optional second line (USN, faculty code, department...). */
export function PersonCell({ name, src, sub, mono = false, size = "sm", className }) {
  return (
    <div className={cn("flex min-w-0 items-center gap-2.5 max-sm:justify-end", className)}>
      <UserAvatar name={name} src={src} size={size} />
      <div className="min-w-0 text-left">
        <div className="truncate font-semibold text-foreground">{name}</div>
        {sub ? <div className={cn("truncate text-[0.8125rem] text-muted-foreground", mono && "font-mono")}>{sub}</div> : null}
      </div>
    </div>
  );
}

/** Labelled search field (type="search"). */
export function SearchBox({ value, onChange, label = "Search", placeholder = "Search", className }) {
  const id = useId();
  return (
    <div className={cn("relative min-w-0", className)}>
      <label htmlFor={id} className="sr-only">{label}</label>
      <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input id={id} type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="pl-9" autoComplete="off" />
    </div>
  );
}

/**
 * Single-choice filter as a row of toggle buttons (state is announced with aria-pressed, not colour alone).
 *   <FilterTabs label="Status" value={v} onChange={setV} options={[{ value: "", label: "All", count: 3 }]} />
 */
export function FilterTabs({ label, value, onChange, options, className }) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex max-w-full flex-wrap gap-1 rounded-xl bg-muted p-1", className)}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value || "all"}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold transition-colors pointer-coarse:min-h-11",
              on ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
            {o.count != null ? <span className={cn("num rounded-full px-1.5 text-xs", on ? "bg-primary-soft text-primary-ink" : "bg-sunken text-ink-2")}>{o.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

export function ActivePill({ active, onLabel = "Active", offLabel = "Inactive" }) {
  return <StatusPill status={active ? "ACTIVE" : "INACTIVE"} label={active ? onLabel : offLabel} />;
}

/** Skeleton rows for non-table lists. */
export function ListSkeletonRows({ rows = 4, className }) {
  return (
    <div className={cn("grid gap-3", className)} role="status" aria-busy="true">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-16 w-full" />)}
    </div>
  );
}

export function QueryError({ error, onRetry, title = "Could not load this page" }) {
  return (
    <Notice tone="danger" title={title}>
      <p>{error?.message || "Please try again in a moment."}</p>
      {onRetry ? <Button type="button" variant="outline" size="sm" className="mt-2" onClick={onRetry}>Try again</Button> : null}
    </Notice>
  );
}

/** "Mon 16:30"-style helper is on the API; this one turns a status filter value into the API param. */
export const statusParam = (v) => (v ? v : undefined);

export function includesText(haystack, needle) {
  if (!needle) return true;
  return String(haystack || "").toLowerCase().includes(needle.trim().toLowerCase());
}

/** Select with an "all" option; `value` "" means all. */
export function FilterSelect({ label, value, onChange, options, allLabel = "All", className }) {
  const id = useId();
  return (
    <div className={cn("min-w-0", className)}>
      <label htmlFor={id} className="sr-only">{label}</label>
      <Select value={value || "__all"} onValueChange={(v) => onChange(v === "__all" ? "" : v)}>
        <SelectTrigger id={id} aria-label={label} className="h-11">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper">
          <SelectItem value="__all">{allLabel}</SelectItem>
          {options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}
