import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CalendarPlus, GraduationCap, MessageSquare, Search, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { ClassPath } from "@/components/app/ClassPath";
import { EmptyState } from "@/components/app/EmptyState";
import { ListSkeleton } from "@/components/app/PageLoader";
import { Notice } from "@/components/app/Notice";
import { StatTile } from "@/components/app/StatTile";
import { StatusPill } from "@/components/app/StatusPill";
import { SubmitButton } from "@/components/app/SubmitButton";
import { PersonRow } from "@/features/people/PersonRow";
import { useOpenChat } from "@/features/chat/useOpenChat";
import { errorMessage } from "@/lib/api";
import { studentApi, supportingApi } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

const panel = "overflow-hidden rounded-lg border border-line bg-card shadow-sm";

/** /student/dashboard - who can help you, what is waiting on you, and your latest meeting requests. */
export default function StudentDashboard() {
  const query = useQuery({ queryKey: queryKeys.studentDashboard, queryFn: studentApi.dashboard, refetchInterval: 30_000 });
  const d = query.data;
  const firstName = d?.student?.full_name?.split(/\s+/)[0];

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome, ${firstName}` : "Dashboard"}
        documentTitle="Dashboard"
        description={d?.student?.class ? <ClassPath cls={d.student.class} size="lg" /> : d ? "Your class has not been set yet. Contact Admin." : undefined}
      />

      {query.isPending ? (
        <ListSkeleton rows={5} />
      ) : query.isError ? (
        <Notice tone="danger" title="Could not load your dashboard">
          {query.error.message}
          <Button variant="outline" size="sm" className="mt-2" onClick={() => query.refetch()}>Try again</Button>
        </Notice>
      ) : (
        <DashboardBody d={d} />
      )}
    </>
  );
}

function DashboardBody({ d }) {
  const open = useOpenChat();
  const { assigned_faculty: assigned, supporting_faculty: supporting, pending_supporting_requests: requests, recent_meetings: meetings, counts } = d;

  return (
    <div className="grid gap-6">
      <div className="grid grid-cols-2 gap-3 min-[44rem]:grid-cols-4">
        <StatTile label="Meetings awaiting a reply" value={counts.meetings_pending} to="/student/meetings?status=pending" alert={counts.meetings_pending > 0} />
        <StatTile label="Accepted meetings" value={counts.meetings_accepted} to="/student/meetings?status=accepted" />
        <StatTile label="Class faculty" value={counts.assigned_faculty} />
        <StatTile label="Supporting faculty" value={counts.supporting_faculty} to="/student/find-faculty" />
      </div>

      {requests.length ? <SupportingRequests items={requests} /> : null}

      <div className="grid items-start gap-6 min-[64rem]:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="grid gap-6">
          <section aria-label="Faculty for your class">
            <SectionHeading title="Faculty for your class" as="h2" />
            <div className={panel}>
              {assigned.length ? (
                <ul className="m-0 list-none p-0">
                  {assigned.map((f) => (
                    <li key={f.id} className="border-t border-line px-4 py-3.5 first:border-t-0">
                      <PersonRow
                        name={f.full_name}
                        code={f.faculty_code}
                        sub={f.department}
                        src={f.profile_picture_url}
                        actions={<FacultyActions faculty={f} open={open} />}
                      />
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={GraduationCap} title="No faculty assigned to your class yet">
                  <p>Your registration is complete. Once Admin assigns faculty to your class they appear here, and you can message them or request a meeting. Meanwhile you can ask any faculty member to be your supporting faculty.</p>
                  <Button asChild variant="outline"><Link to="/student/find-faculty"><Search aria-hidden="true" /> Find faculty</Link></Button>
                </EmptyState>
              )}
            </div>
          </section>

          <section aria-label="Recent meetings">
            <SectionHeading
              title="Recent meetings"
              actions={meetings.length ? <Button asChild variant="outline" size="sm"><Link to="/student/meetings">View all</Link></Button> : null}
            />
            <div className={panel}>
              {meetings.length ? (
                <ul className="m-0 list-none p-0">
                  {meetings.map((m) => (
                    <li key={m.id} className="grid gap-1 border-t border-line px-4 py-3.5 first:border-t-0">
                      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                        <p className="m-0 min-w-0 font-[650]">{m.reason}</p>
                        <StatusPill status={m.status} />
                      </div>
                      <p className="m-0 text-sm text-muted-foreground">
                        With {m.counterpart_name} - requested {formatDate(m.requested_at)}
                      </p>
                      {m.meeting_time_text ? (
                        <p className="m-0 mt-0.5 inline-flex w-fit max-w-full items-start gap-1.5 rounded-md bg-saffron-soft px-2.5 py-1 text-sm font-semibold text-saffron-ink">
                          <CalendarClock aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                          <span className="min-w-0 break-words"><span className="sr-only">Time: </span>{m.meeting_time_text}</span>
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={CalendarClock} title="No meeting requests yet">
                  <p>When you ask a faculty member for time, their reply and the time that suits them show up here.</p>
                </EmptyState>
              )}
            </div>
          </section>
        </div>

        <section aria-label="Supporting faculty">
          <SectionHeading title="Supporting faculty" />
          <div className={panel}>
            {supporting.length ? (
              <ul className="m-0 list-none p-0">
                {supporting.map((f) => (
                  <li key={f.id} className="border-t border-line px-4 py-3.5 first:border-t-0">
                    <PersonRow
                      size="sm"
                      name={f.full_name}
                      code={f.faculty_code}
                      sub={f.department}
                      src={f.profile_picture_url}
                      actions={<FacultyActions faculty={f} open={open} compact />}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={Users} compact className="px-4" title="No supporting faculty yet">
                <p>Faculty outside your class can support you too. Send a request and they decide.</p>
              </EmptyState>
            )}
            <div className="border-t border-line bg-sunken/50 px-4 py-3">
              <Button asChild variant="outline" size="sm"><Link to="/student/find-faculty"><Search aria-hidden="true" /> Find faculty</Link></Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function FacultyActions({ faculty, open, compact = false }) {
  const busy = open.isPending && open.variables === faculty.id;
  return (
    <>
      <SubmitButton type="button" size="sm" loading={busy} disabled={open.isPending} onClick={() => open.mutate(faculty.id)} aria-label={`Message ${faculty.full_name}`}>
        <MessageSquare aria-hidden="true" /> Message
      </SubmitButton>
      <Button asChild variant="outline" size="sm">
        <Link to={`/student/meetings/request/${faculty.id}`} aria-label={`Request a meeting with ${faculty.full_name}`}>
          <CalendarPlus aria-hidden="true" /> {compact ? "Meet" : "Request meeting"}
        </Link>
      </Button>
    </>
  );
}

/** Faculty-initiated supporting requests waiting for this student's answer. */
function SupportingRequests({ items }) {
  const qc = useQueryClient();
  const answer = useMutation({
    mutationFn: ({ id, accept }) => (accept ? supportingApi.accept(id) : supportingApi.reject(id)),
    onSuccess: (res) => {
      toast.success(res.message || "Done.");
      qc.invalidateQueries({ queryKey: queryKeys.studentDashboard });
      qc.invalidateQueries({ queryKey: queryKeys.supporting });
      qc.invalidateQueries({ queryKey: queryKeys.chats });
      qc.invalidateQueries({ queryKey: queryKeys.session });
    },
    onError: (err) => {
      toast.error(errorMessage(err));
      qc.invalidateQueries({ queryKey: queryKeys.studentDashboard });
    },
  });
  const working = (id, accept) => answer.isPending && answer.variables?.id === id && answer.variables?.accept === accept;

  return (
    <section aria-labelledby="await-response" className="overflow-hidden rounded-lg border border-warn-line bg-saffron-soft/60 shadow-sm">
      <h2 id="await-response" className="m-0 px-4 pt-3.5 pb-1 text-[1.1rem] text-saffron-ink">
        {items.length === 1 ? "A faculty member wants to support you" : `${items.length} faculty members want to support you`}
      </h2>
      <ul className="m-0 list-none p-0">
        {items.map((r) => (
          <li key={r.id} className="border-t border-warn-line/70 px-4 py-3 first:border-t-0">
            <PersonRow
              size="sm"
              name={r.faculty.full_name}
              code={r.faculty.faculty_code}
              sub={`${r.faculty.department ? `${r.faculty.department} - ` : ""}asked on ${formatDate(r.created_at)}`}
              src={r.faculty.profile_picture_url}
              actions={
                <>
                  <SubmitButton type="button" size="sm" loading={working(r.id, true)} disabled={answer.isPending} onClick={() => answer.mutate({ id: r.id, accept: true })} aria-label={`Accept ${r.faculty.full_name}`}>
                    Accept
                  </SubmitButton>
                  <SubmitButton type="button" size="sm" variant="outline" loading={working(r.id, false)} disabled={answer.isPending} onClick={() => answer.mutate({ id: r.id, accept: false })} aria-label={`Decline ${r.faculty.full_name}`}>
                    Decline
                  </SubmitButton>
                </>
              }
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
