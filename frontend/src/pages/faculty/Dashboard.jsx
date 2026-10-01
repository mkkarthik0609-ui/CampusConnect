import { Link } from "react-router-dom";
import { ArrowRight, CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/StatusPill";
import { ClassPath } from "@/components/app/ClassPath";
import { EmptyState } from "@/components/app/EmptyState";
import { useAuth } from "@/auth/AuthProvider";
import { pluralize, timeAgo } from "@/lib/format";
import {
  ChangedFields, ClassLinkRow, ListSkeleton, MessageButton, NoClassesEmpty, Panel, PersonCell, QueryError, Row, RowList,
} from "@/features/faculty/ui";
import { SupportingRequestRow } from "@/features/faculty/SupportingRequestRow";
import { useFacultyDashboard, useMessageStudent } from "@/features/faculty/hooks";

export default function FacultyDashboard() {
  const { user } = useAuth();
  const query = useFacultyDashboard();
  const message = useMessageStudent();
  const data = query.data;

  const profile = data?.profile;
  const counts = data?.counts || {};
  const attention = [
    { n: counts.pending_supporting_requests, one: "student request", many: "student requests", to: "#supporting-requests" },
    { n: counts.pending_permission_requests, one: "profile approval", many: "profile approvals", to: "/faculty/approvals" },
    { n: counts.meetings_pending, one: "meeting request", many: "meeting requests", to: "/faculty/meetings" },
  ].filter((a) => a.n > 0);

  return (
    <>
      <PageHeader
        title={profile?.full_name || user?.full_name || "Dashboard"}
        documentTitle="Dashboard"
        description={
          profile ? (
            <>
              Faculty ID <span className="font-mono text-[0.9em] text-foreground">{profile.faculty_code}</span>
              {profile.department ? <> &middot; {profile.department} department</> : null}
            </>
          ) : undefined
        }
        actions={<Button asChild variant="outline"><Link to="/faculty/classes">Request a class</Link></Button>}
      />

      {query.isError ? <QueryError error={query.error} onRetry={() => query.refetch()} title="Could not load your dashboard" /> : null}
      {query.isPending ? <div className="grid gap-8"><ListSkeleton rows={3} /><ListSkeleton rows={2} /></div> : null}

      {data ? (
        <div className="grid items-start gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_21rem]">
          <div className="grid min-w-0 gap-8">
            {attention.length ? (
              <nav aria-label="Needs your attention" className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-warn-line bg-saffron-soft px-4 py-3 text-saffron-ink">
                <span className="font-display font-bold">Waiting on you</span>
                {attention.map((a) => (
                  <a key={a.to} href={a.to} className="inline-flex items-center gap-1 text-[0.9375rem] font-semibold text-inherit underline underline-offset-4 decoration-1">
                    {pluralize(a.n, a.one, a.many)}
                  </a>
                ))}
              </nav>
            ) : null}

            <Panel title="Your classes" count={data.classes.length || null} actions={data.classes.length ? <Button asChild variant="ghost" size="sm"><Link to="/faculty/classes">Manage <ArrowRight aria-hidden="true" /></Link></Button> : null}>
              {data.classes.length ? (
                <RowList label="Assigned classes">{data.classes.map((c) => <ClassLinkRow key={c.section_id} cls={c} />)}</RowList>
              ) : (
                <div className="rounded-lg border bg-card shadow-sm"><NoClassesEmpty /></div>
              )}
            </Panel>

            {data.pending_supporting_requests.length ? (
              <Panel title="Mentor requests" count={data.pending_supporting_requests.length} className="scroll-mt-24" id="supporting-requests">
                <RowList label="Pending supporting-student requests">
                  {data.pending_supporting_requests.map((r) => <SupportingRequestRow key={r.id} request={r} />)}
                </RowList>
              </Panel>
            ) : null}

            <Panel title="Supporting students" count={data.supporting_students.length || null}>
              {data.supporting_students.length ? (
                <RowList label="Supporting students">
                  {data.supporting_students.map((s) => (
                    <Row key={s.id}>
                      <div className="grid min-w-0 flex-1 basis-56 gap-1.5">
                        <PersonCell name={s.full_name} src={s.profile_picture_url} code={s.usn} />
                        {s.class ? <div className="pl-12"><ClassPath cls={s.class} /></div> : null}
                      </div>
                      <div className="ml-auto">
                        <MessageButton name={s.full_name} pending={message.isPending && message.variables === s.id} onClick={() => message.mutate(s.id)} />
                      </div>
                    </Row>
                  ))}
                </RowList>
              ) : (
                <div className="rounded-lg border bg-card shadow-sm">
                  <EmptyState compact className="px-4" title="No supporting students yet">
                    Students outside your classes can ask you to mentor them, or you can invite a student from your classes.
                    <div className="mt-3"><Button asChild variant="outline" size="sm"><Link to="/faculty/find-students">Find students</Link></Button></div>
                  </EmptyState>
                </div>
              )}
            </Panel>
          </div>

          <aside aria-label="Requests and meetings" className="grid min-w-0 gap-8">
            <Panel title="Class requests" count={data.pending_class_requests.length || null}>
              {data.pending_class_requests.length ? (
                <RowList label="Pending class requests">
                  {data.pending_class_requests.map((r) => (
                    <Row key={r.id} className="justify-between">
                      <ClassPath cls={r.class} />
                      <StatusPill status={r.status} />
                    </Row>
                  ))}
                </RowList>
              ) : (
                <p className="m-0 rounded-lg border border-dashed border-line-strong px-4 py-3 text-sm text-muted-foreground">
                  No class requests with Admin right now.
                </p>
              )}
            </Panel>

            <Panel
              title="Profile approvals"
              count={data.pending_permission_requests.length || null}
              actions={data.pending_permission_requests.length ? <Button asChild variant="ghost" size="sm"><Link to="/faculty/approvals">Review <ArrowRight aria-hidden="true" /></Link></Button> : null}
            >
              {data.pending_permission_requests.length ? (
                <RowList label="Pending student profile changes">
                  {data.pending_permission_requests.slice(0, 3).map((r) => (
                    <li key={r.id} className="grid gap-1.5 px-4 py-3.5">
                      <p className="m-0 font-semibold">{r.student?.full_name || r.requester_name}</p>
                      <ChangedFields changes={r.requested_changes} />
                    </li>
                  ))}
                </RowList>
              ) : (
                <p className="m-0 rounded-lg border border-dashed border-line-strong px-4 py-3 text-sm text-muted-foreground">
                  Nothing to approve.
                </p>
              )}
            </Panel>

            <Panel title="Recent meetings" actions={<Button asChild variant="ghost" size="sm"><Link to="/faculty/meetings">All <ArrowRight aria-hidden="true" /></Link></Button>}>
              {data.recent_meetings.length ? (
                <RowList label="Recent meetings">
                  {data.recent_meetings.map((m) => (
                    <li key={m.id} className="grid gap-1 px-4 py-3.5">
                      <div className="flex items-start justify-between gap-3">
                        <p className="m-0 min-w-0 font-semibold">{m.student?.full_name || m.counterpart_name}</p>
                        <StatusPill status={m.status} />
                      </div>
                      <p className="m-0 line-clamp-2 text-sm text-ink-2">{m.reason}</p>
                      <p className="m-0 inline-flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
                        <CalendarDays aria-hidden="true" className="size-3.5" />
                        {m.meeting_time_text || `Requested ${timeAgo(m.requested_at)}`}
                      </p>
                    </li>
                  ))}
                </RowList>
              ) : (
                <p className="m-0 rounded-lg border border-dashed border-line-strong px-4 py-3 text-sm text-muted-foreground">
                  No meetings yet. Requests from students show up here.
                </p>
              )}
            </Panel>
          </aside>
        </div>
      ) : null}
    </>
  );
}
