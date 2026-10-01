import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight, BookOpen, CalendarDays, CircleCheck, FlaskConical, Inbox, LayoutGrid, Layers, Link2, MessagesSquare, ShieldCheck, Users,
} from "lucide-react";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { Notice } from "@/components/app/Notice";
import { Skeleton } from "@/components/ui/skeleton";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { QueryError } from "@/features/admin/common";
import { cn } from "@/lib/utils";

const LEDGER = [
  { key: "student_count", label: "Students registered", to: "/admin/students", icon: Users },
  { key: "faculty_count", label: "Faculty", to: "/admin/faculty", icon: BookOpen },
  { key: "class_count", label: "Active classes", to: "/admin/classes", icon: LayoutGrid },
  { key: "meeting_count", label: "Meeting requests", to: "/admin/meetings", icon: CalendarDays },
  { key: "admin_count", label: "Admin accounts", to: "/admin/admins", icon: ShieldCheck },
  { key: "removed_student_count", label: "Registrations removed", to: "/admin/students", icon: Users },
];

const QUICK = [
  { to: "/admin/academics", label: "Academic structure", hint: "Branches, departments, years and sections", icon: Layers },
  { to: "/admin/assignments", label: "Faculty assignments", hint: "Who teaches and mentors which class", icon: Link2 },
  { to: "/admin/chats", label: "Chats", hint: "Read-only view of every conversation", icon: MessagesSquare },
  { to: "/admin/research", label: "Scheduling research", hint: "FCFS vs rule-based vs intelligent results", icon: FlaskConical },
];

function Attention({ to, count, title, children, icon: Icon }) {
  const live = count > 0;
  return (
    <li>
      <Link
        to={to}
        className={cn(
          "group flex items-center gap-4 rounded-lg border px-4 py-3.5 text-inherit no-underline transition-colors",
          live ? "border-warn-line bg-saffron-soft hover:border-saffron" : "border-line bg-card hover:border-primary",
        )}
      >
        <span className={cn("font-display text-[2rem] leading-none font-bold tracking-tight tabular-nums", live ? "text-saffron-ink" : "text-muted-foreground")}>{count}</span>
        <span className="min-w-0 flex-1">
          <span className={cn("flex items-center gap-1.5 font-semibold", live ? "text-saffron-ink" : "text-foreground")}>
            <Icon aria-hidden="true" className="size-4 shrink-0" />
            {title}
          </span>
          <span className={cn("block text-sm", live ? "text-saffron-ink" : "text-muted-foreground")}>{children}</span>
        </span>
        <ArrowUpRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 motion-reduce:transition-none" />
      </Link>
    </li>
  );
}

export default function AdminDashboard() {
  const q = useQuery({ queryKey: adminKeys.dashboard, queryFn: adminApi.dashboard });
  const s = q.data?.stats;

  return (
    <>
      <PageHeader title="Dashboard" description="Campus activity at a glance, and what is waiting for you." />

      {q.isError ? <QueryError error={q.error} onRetry={q.refetch} /> : null}

      <section aria-label="Needs your attention" className="mb-8">
        <SectionHeading title="Needs your attention" />
        {q.isPending ? (
          <div className="grid gap-3" role="status" aria-busy="true"><span className="sr-only">Loading</span>{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[4.5rem]" />)}</div>
        ) : s ? (
          <>
            <ul className="m-0 grid list-none gap-3 p-0">
              <Attention to="/admin/assignment-requests" count={s.pending_assignment_count} icon={Inbox} title="Class requests from faculty">
                {s.pending_assignment_count ? "Faculty are waiting to be assigned to a class." : "No pending requests."}
              </Attention>
              <Attention to="/admin/approvals" count={s.pending_permission_count} icon={CircleCheck} title="Profile change approvals">
                {s.pending_permission_count ? "Profile-change requests are waiting for a decision." : "Nothing to approve."}
              </Attention>
              <Attention to="/admin/students" count={s.unmapped_student_count} icon={Users} title="Students without a class">
                {s.unmapped_student_count ? "Their old class text matched no class. Remove the registration so they can register again." : "Every student is mapped to a class."}
              </Attention>
            </ul>
            {s.unmapped_student_count > 0 ? (
              <Notice tone="warning" className="mt-3" title="Unmapped students cannot reach their faculty">
                Open Students and filter by "Unmapped" to review them.
              </Notice>
            ) : null}
          </>
        ) : null}
      </section>

      <section aria-label="Campus figures" className="mb-8">
        <SectionHeading title="Campus today" />
        {q.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : s ? (
          <dl className="m-0 grid gap-px overflow-hidden rounded-lg border bg-line shadow-sm sm:grid-cols-2 lg:grid-cols-3">
            {LEDGER.map(({ key, label, to, icon: Icon }) => (
              <div key={key} className="bg-card">
                <Link to={to} className="flex items-center justify-between gap-3 px-5 py-4 text-inherit no-underline transition-colors hover:bg-primary-soft">
                  <div className="flex flex-col-reverse">
                    <dt className="mt-1 text-sm text-muted-foreground">{label}</dt>
                    <dd className="m-0 font-display text-[1.9rem] leading-none font-bold tracking-tight tabular-nums">{s[key]}</dd>
                  </div>
                  <Icon aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
                </Link>
              </div>
            ))}
          </dl>
        ) : null}
      </section>

      <section aria-label="Quick links">
        <SectionHeading title="Jump to" />
        <ul className="m-0 grid list-none gap-x-8 p-0 sm:grid-cols-2">
          {QUICK.map(({ to, label, hint, icon: Icon }) => (
            <li key={to} className="border-b border-line">
              <Link to={to} className="flex items-center gap-3 py-3 text-inherit no-underline hover:text-primary">
                <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary-ink"><Icon aria-hidden="true" className="size-[1.1rem]" /></span>
                <span className="min-w-0">
                  <span className="block font-semibold">{label}</span>
                  <span className="block text-sm text-muted-foreground">{hint}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
