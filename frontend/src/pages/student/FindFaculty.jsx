import { useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, MessageSquare, Search, UserRoundSearch } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { ListSkeleton } from "@/components/app/PageLoader";
import { Notice } from "@/components/app/Notice";
import { StatusPill } from "@/components/app/StatusPill";
import { SubmitButton } from "@/components/app/SubmitButton";
import { PersonRow } from "@/features/people/PersonRow";
import { useOpenChat } from "@/features/chat/useOpenChat";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { errorMessage } from "@/lib/api";
import { supportingApi } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

const panel = "overflow-hidden rounded-lg border border-line bg-card shadow-sm";

/** /student/find-faculty - ask any faculty member to be your supporting faculty, and follow up on those requests. */
export default function FindFaculty() {
  const [q, setQ] = useState("");
  const term = useDebouncedValue(q.trim(), 300);
  const search = useQuery({
    queryKey: queryKeys.facultySearch(term),
    queryFn: () => supportingApi.searchFaculty(term),
    enabled: term.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 5_000,
  });
  const requests = useQuery({ queryKey: queryKeys.supporting, queryFn: () => supportingApi.list(), refetchInterval: 30_000 });
  const open = useOpenChat();
  const qc = useQueryClient();

  const refresh = () => {
    qc.invalidateQueries({ queryKey: queryKeys.supporting });
    qc.invalidateQueries({ queryKey: queryKeys.studentDashboard });
    qc.invalidateQueries({ queryKey: queryKeys.chats });
    qc.invalidateQueries({ queryKey: queryKeys.session });
  };
  const act = useMutation({
    mutationFn: ({ kind, id }) => (kind === "request" ? supportingApi.requestFaculty(id) : kind === "accept" ? supportingApi.accept(id) : supportingApi.reject(id)),
    onSuccess: (res) => { toast.success(res.message || "Done."); refresh(); },
    onError: (err) => { toast.error(errorMessage(err)); refresh(); },
  });
  const pendingKey = act.isPending ? `${act.variables.kind}:${act.variables.id}` : null;
  const ctx = { act, open, pendingKey };

  const results = search.data?.items || [];
  const typing = q.trim() !== term;
  const mine = requests.data?.items || [];

  return (
    <>
      <PageHeader
        title="Find faculty"
        description="Ask a faculty member outside your class to be your supporting faculty. Once they accept, you can message them and request meetings."
      />

      <form role="search" onSubmit={(e) => e.preventDefault()} className="mb-5 max-w-2xl">
        <label htmlFor="faculty-q" className="mb-1.5 block text-sm font-semibold text-ink-2">Search by name or Faculty ID</label>
        <div className="relative">
          <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-[1.1rem] -translate-y-1/2 text-muted-foreground" />
          <Input id="faculty-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} placeholder="For example: FAC101 or Rao" className="pl-10" autoComplete="off" />
        </div>
      </form>

      {term ? (
        <section aria-label="Search results" aria-busy={search.isFetching} className="mb-8">
          <p className="sr-only" role="status">
            {search.isSuccess && !typing ? `${results.length} ${results.length === 1 ? "result" : "results"} for ${term}` : ""}
          </p>
          <div className={panel}>
            {search.isPending ? (
              <ListSkeleton rows={3} className="p-3" />
            ) : search.isError ? (
              <div className="p-3">
                <Notice tone="danger" title="Search failed">
                  {search.error.message}
                  <Button variant="outline" size="sm" className="mt-2" onClick={() => search.refetch()}>Try again</Button>
                </Notice>
              </div>
            ) : results.length === 0 ? (
              <EmptyState icon={UserRoundSearch} title={`No faculty found for "${term}"`}>
                <p>Check the spelling, or try a Faculty ID such as FAC101.</p>
              </EmptyState>
            ) : (
              <ul className="m-0 list-none p-0">
                {results.map((f) => (
                  <li key={f.id} className="border-t border-line px-4 py-3.5 first:border-t-0">
                    <PersonRow
                      name={f.full_name}
                      code={f.faculty_code}
                      sub={f.department}
                      src={f.profile_picture_url}
                      actions={<RelationshipActions faculty={f} rel={f.relationship} hasAccess={f.has_access} via={f.access_via} canRequest={f.can_request} ctx={ctx} />}
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      ) : null}

      <section aria-label="Your supporting requests">
        <SectionHeading title="Your supporting requests" />
        <div className={panel}>
          {requests.isPending ? (
            <ListSkeleton rows={2} className="p-3" />
          ) : requests.isError ? (
            <div className="p-3">
              <Notice tone="danger" title="Could not load your requests">{requests.error.message}</Notice>
            </div>
          ) : mine.length === 0 ? (
            <EmptyState icon={UserRoundSearch} compact className="px-4" title="You have not asked anyone yet">
              Search above to find a faculty member. They are told as soon as you send a request.
            </EmptyState>
          ) : (
            <ul className="m-0 list-none p-0">
              {mine.map((r) => {
                const f = r.faculty;
                return (
                  <li key={r.id} className="border-t border-line px-4 py-3.5 first:border-t-0">
                    <PersonRow
                      name={f.full_name}
                      code={f.faculty_code}
                      sub={`${f.department ? `${f.department} - ` : ""}${r.direction === "incoming" ? "asked you" : "you asked"} on ${formatDate(r.created_at)}`}
                      src={f.profile_picture_url}
                      actions={
                        <RelationshipActions
                          faculty={f}
                          rel={{ id: r.id, status: r.status, requested_by: r.requested_by }}
                          hasAccess={r.status === "ACCEPTED"}
                          via="supporting"
                          canRequest={r.status === "REJECTED" && r.requested_by === "STUDENT"}
                          ctx={ctx}
                        />
                      }
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
    </>
  );
}

/** What a student can do with one faculty member, given class access and any supporting relationship. */
function RelationshipActions({ faculty, rel, hasAccess, via, canRequest, ctx }) {
  const { act, open, pendingKey } = ctx;
  const busyAny = act.isPending || open.isPending;

  if (hasAccess) {
    return (
      <>
        <StatusPill status="ACTIVE" tone="ok" label={via === "class" ? "In your class" : "Supporting you"} />
        <SubmitButton type="button" size="sm" loading={open.isPending && open.variables === faculty.id} disabled={busyAny} onClick={() => open.mutate(faculty.id)} aria-label={`Message ${faculty.full_name}`}>
          <MessageSquare aria-hidden="true" /> Message
        </SubmitButton>
        <Button asChild variant="outline" size="sm">
          <Link to={`/student/meetings/request/${faculty.id}`} aria-label={`Request a meeting with ${faculty.full_name}`}><CalendarPlus aria-hidden="true" /> Meet</Link>
        </Button>
      </>
    );
  }

  if (rel?.status === "PENDING") {
    if (rel.requested_by === "FACULTY") {
      return (
        <>
          <SubmitButton type="button" size="sm" loading={pendingKey === `accept:${rel.id}`} disabled={busyAny} onClick={() => act.mutate({ kind: "accept", id: rel.id })} aria-label={`Accept ${faculty.full_name}`}>Accept</SubmitButton>
          <SubmitButton type="button" size="sm" variant="outline" loading={pendingKey === `reject:${rel.id}`} disabled={busyAny} onClick={() => act.mutate({ kind: "reject", id: rel.id })} aria-label={`Decline ${faculty.full_name}`}>Decline</SubmitButton>
        </>
      );
    }
    return <StatusPill status="PENDING" label="Waiting for their answer" />;
  }

  if (rel?.status === "REJECTED") {
    return (
      <>
        <StatusPill status="REJECTED" label="Declined" />
        {canRequest ? (
          <SubmitButton type="button" size="sm" variant="outline" loading={pendingKey === `request:${faculty.id}`} disabled={busyAny} onClick={() => act.mutate({ kind: "request", id: faculty.id })} aria-label={`Ask ${faculty.full_name} again`}>
            Ask again
          </SubmitButton>
        ) : null}
      </>
    );
  }

  if (canRequest || !rel) {
    return (
      <SubmitButton type="button" size="sm" loading={pendingKey === `request:${faculty.id}`} disabled={busyAny} onClick={() => act.mutate({ kind: "request", id: faculty.id })} aria-label={`Ask ${faculty.full_name} to be your supporting faculty`}>
        Request support
      </SubmitButton>
    );
  }
  return null;
}
