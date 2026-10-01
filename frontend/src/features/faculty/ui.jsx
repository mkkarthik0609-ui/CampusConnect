import { Link } from "react-router-dom";
import { ChevronRight, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SubmitButton } from "@/components/app/SubmitButton";
import { SectionHeading } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { UserAvatar } from "@/components/app/UserAvatar";
import { ClassPath } from "@/components/app/ClassPath";
import { Notice } from "@/components/app/Notice";
import { Skeleton } from "@/components/ui/skeleton";
import { pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A titled block: heading row on the page background, a bordered list surface beneath it. */
export function Panel({ title, count, actions, children, className, id }) {
  return (
    <section id={id} className={cn("min-w-0", className)}>
      <SectionHeading
        title={
          <span className="inline-flex items-baseline gap-2">
            {title}
            {count ? <span className="font-sans text-sm font-semibold text-muted-foreground tabular-nums">{count}</span> : null}
          </span>
        }
        actions={actions}
      />
      {children}
    </section>
  );
}

/** Divided rows inside one bordered surface (preferred over a grid of identical cards). */
export function RowList({ children, className, label }) {
  return (
    <ul aria-label={label} className={cn("m-0 list-none divide-y divide-line overflow-hidden rounded-lg border bg-card p-0 shadow-sm", className)}>
      {children}
    </ul>
  );
}

export function Row({ children, className }) {
  return <li className={cn("flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5", className)}>{children}</li>;
}

export function ListSkeleton({ rows = 3 }) {
  return (
    <div role="status" aria-busy="true" className="divide-y divide-line overflow-hidden rounded-lg border bg-card shadow-sm">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-4">
          <Skeleton className="size-9 rounded-full" />
          <div className="grid flex-1 gap-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-3 w-1/2" /></div>
        </div>
      ))}
    </div>
  );
}

export function QueryError({ error, onRetry, title = "Could not load this" }) {
  return (
    <Notice tone="danger" title={title}>
      <p>{error?.message || "Please try again in a moment."}</p>
      {onRetry ? <Button type="button" variant="outline" size="sm" className="mt-2" onClick={onRetry}>Try again</Button> : null}
    </Notice>
  );
}

/** Avatar + name + secondary line (USN / Faculty ID in mono). */
export function PersonCell({ name, src, code, extra, size = "sm", className }) {
  return (
    <div className={cn("flex min-w-0 items-center gap-3", className)}>
      <UserAvatar name={name} src={src} size={size} />
      <div className="min-w-0">
        <p className="m-0 truncate font-semibold text-foreground">{name}</p>
        <p className="m-0 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
          {code ? <span className="font-mono text-[0.8125rem]">{code}</span> : null}
          {extra}
        </p>
      </div>
    </div>
  );
}

/** One assigned class as a full-width link row: path pills, student count, chevron. */
export function ClassLinkRow({ cls }) {
  return (
    <li>
      <Link
        to={`/faculty/classes/${cls.section_id}`}
        className="group flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3.5 text-inherit no-underline transition-colors hover:bg-primary-soft/60 focus-visible:bg-primary-soft/60"
      >
        <ClassPath cls={cls} />
        <span className="ml-auto inline-flex items-center gap-2 text-sm text-muted-foreground">
          <span className="font-semibold tabular-nums text-ink-2">{pluralize(cls.student_count ?? 0, "student")}</span>
          <ChevronRight aria-hidden="true" className="size-4 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" />
        </span>
      </Link>
    </li>
  );
}

export function MessageButton({ onClick, pending, name, size = "sm", variant = "outline" }) {
  return (
    <SubmitButton type="button" variant={variant} size={size} loading={pending} onClick={onClick} aria-label={name ? `Message ${name}` : undefined}>
      {pending ? null : <MessageSquare aria-hidden="true" />}
      Message
    </SubmitButton>
  );
}

export function NoClassesEmpty({ compact = false }) {
  return (
    <EmptyState
      compact={compact}
      title="No classes assigned yet"
      action={<Button asChild><Link to="/faculty/classes">Request a class</Link></Button>}
    >
      <p>Ask the Admin for a class and it will appear here once approved. Students and search open up at the same moment.</p>
    </EmptyState>
  );
}

/** Human labels for the fields a student may ask to change. */
const FIELD_LABELS = {
  phone: "Phone",
  personal_email: "Personal email",
  department: "Department",
  professional_email: "Professional email",
};

export function ChangedFields({ changes, className }) {
  const entries = Object.entries(changes || {});
  if (!entries.length) return null;
  return (
    <dl className={cn("m-0 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]", className)}>
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="font-semibold text-muted-foreground">{FIELD_LABELS[key] || key.replace(/_/g, " ")}</dt>
          <dd className="m-0 break-words font-medium text-foreground">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
