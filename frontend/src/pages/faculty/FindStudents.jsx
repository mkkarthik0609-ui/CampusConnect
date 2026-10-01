import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search, UserPlus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { SubmitButton } from "@/components/app/SubmitButton";
import { EmptyState } from "@/components/app/EmptyState";
import { PageHeader } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/StatusPill";
import { ClassPath } from "@/components/app/ClassPath";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { errorMessage } from "@/lib/api";
import { facultyApi } from "@/lib/endpoints";
import { ListSkeleton, MessageButton, NoClassesEmpty, PersonCell, QueryError, Row, RowList } from "@/features/faculty/ui";
import { facultyKeys, useFacultyClasses, useMessageStudent, useRefreshFaculty } from "@/features/faculty/hooks";

const RELATION_LABEL = {
  PENDING: { out: "Request sent", in: "Wants you as mentor" },
  ACCEPTED: { out: "Supporting student", in: "Supporting student" },
  REJECTED: { out: "Declined", in: "Declined" },
};

function relationPill(rel) {
  if (!rel) return null;
  const mine = rel.requested_by === "FACULTY";
  const label = RELATION_LABEL[rel.status]?.[mine ? "out" : "in"];
  return <StatusPill status={rel.status} label={label} />;
}

export default function FacultyFindStudents() {
  const [text, setText] = useState("");
  const q = useDebouncedValue(text.trim(), 300);
  const refresh = useRefreshFaculty();
  const qc = useQueryClient();
  const classes = useFacultyClasses();
  const message = useMessageStudent();

  const search = useQuery({
    queryKey: facultyKeys.search(q),
    queryFn: () => facultyApi.searchStudents(q),
    enabled: q.length > 0,
    staleTime: 10_000,
  });

  const invite = useMutation({
    mutationFn: (studentId) => facultyApi.requestSupporting(studentId),
    onSuccess: (data) => {
      toast.success(data.message || "Request sent.");
      qc.invalidateQueries({ queryKey: ["faculty", "student-search"] });
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  const noClasses = classes.data && classes.data.assignments.length === 0;
  const results = search.data?.items || [];
  const typing = text.trim() !== q || (search.isFetching && !search.data);

  return (
    <>
      <PageHeader
        title="Find students"
        description="Search by name or USN. Results are limited to students in the classes Admin has assigned to you."
      />

      {noClasses ? (
        <div className="rounded-lg border bg-card shadow-sm"><NoClassesEmpty /></div>
      ) : (
        <div className="grid max-w-3xl gap-5">
          <form role="search" onSubmit={(e) => e.preventDefault()} className="relative">
            <label htmlFor="student-search" className="sr-only">Search students by name or USN</label>
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3.5 size-[1.15rem] -translate-y-1/2 text-muted-foreground" />
            <Input
              id="student-search"
              type="search"
              autoComplete="off"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Asha Rao or 1AB21CS001"
              className="h-12 pl-11 text-base"
            />
          </form>

          <div aria-live="polite">
            {!q && !text.trim() ? (
              <div className="rounded-lg border border-dashed border-line-strong">
                <EmptyState icon={Search} title="Start typing a name or USN">
                  <p>Only students in your assigned classes can be found here, even with a partial name.</p>
                </EmptyState>
              </div>
            ) : null}

            {typing ? <ListSkeleton rows={2} /> : null}
            {search.isError ? <QueryError error={search.error} onRetry={() => search.refetch()} title="Search failed" /> : null}

            {!typing && search.data && q ? (
              results.length ? (
                <>
                  <p className="mb-2 text-sm text-muted-foreground">
                    {search.data.total === 1 ? "1 student" : `${search.data.total} students`} for &ldquo;{q}&rdquo;
                  </p>
                  <RowList label="Matching students">
                    {results.map((s) => (
                      <Row key={s.id}>
                        <div className="grid min-w-0 flex-1 basis-60 gap-1.5">
                          <PersonCell name={s.full_name} src={s.profile_picture_url} code={s.usn} />
                          {s.class ? <div className="pl-12"><ClassPath cls={s.class} /></div> : null}
                        </div>
                        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
                          {relationPill(s.relationship)}
                          <MessageButton name={s.full_name} pending={message.isPending && message.variables === s.id} onClick={() => message.mutate(s.id)} />
                          {s.can_request ? (
                            <SubmitButton
                              type="button"
                              size="sm"
                              loading={invite.isPending && invite.variables === s.id}
                              disabled={invite.isPending}
                              onClick={() => invite.mutate(s.id)}
                              aria-label={`Send ${s.full_name} a supporting request`}
                            >
                              {invite.isPending && invite.variables === s.id ? null : <UserPlus aria-hidden="true" />}
                              Send supporting request
                            </SubmitButton>
                          ) : null}
                        </div>
                      </Row>
                    ))}
                  </RowList>
                </>
              ) : (
                <div className="rounded-lg border bg-card shadow-sm">
                  <EmptyState title={`No student found for “${q}”`}>
                    <p>Check the spelling, or try the USN. Students outside your assigned classes never appear here.</p>
                  </EmptyState>
                </div>
              )
            ) : null}
          </div>
        </div>
      )}
    </>
  );
}
