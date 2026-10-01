import { PageHeader } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/StatusPill";
import { ClassPath } from "@/components/app/ClassPath";
import { formatDate } from "@/lib/format";
import { ClassLinkRow, ListSkeleton, NoClassesEmpty, Panel, QueryError, Row, RowList } from "@/features/faculty/ui";
import { RequestClassForm } from "@/features/faculty/RequestClassForm";
import { useFacultyClasses } from "@/features/faculty/hooks";

const REQUEST_NOTE = {
  PENDING: "Waiting for Admin",
  APPROVED: "Approved",
  REJECTED: "Declined by Admin",
};

export default function FacultyClasses() {
  const query = useFacultyClasses();
  const assignments = query.data?.assignments || [];
  const requests = query.data?.requests || [];

  return (
    <>
      <PageHeader
        title="My classes"
        description="Admin decides which classes you teach. Once a class is assigned you can see its students, message them and approve their profile changes."
      />

      <div className="grid items-start gap-x-10 gap-y-9 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <div className="grid min-w-0 gap-9">
          <Panel title="Assigned to you" count={assignments.length || null}>
            {query.isPending ? <ListSkeleton rows={3} /> : null}
            {query.isError ? <QueryError error={query.error} onRetry={() => query.refetch()} title="Could not load your classes" /> : null}
            {query.data ? (
              assignments.length ? (
                <RowList label="Assigned classes">{assignments.map((c) => <ClassLinkRow key={c.section_id} cls={c} />)}</RowList>
              ) : (
                <div className="rounded-lg border bg-card shadow-sm"><NoClassesEmpty /></div>
              )
            ) : null}
          </Panel>

          <Panel title="My requests" count={requests.length || null}>
            {query.isPending ? <ListSkeleton rows={2} /> : null}
            {query.data ? (
              requests.length ? (
                <RowList label="My class requests">
                  {requests.map((r) => (
                    <Row key={r.id} className="items-start">
                      <div className="grid min-w-0 flex-1 basis-56 gap-1.5">
                        <ClassPath cls={r.class} />
                        {r.note ? <p className="m-0 text-sm text-ink-2">&ldquo;{r.note}&rdquo;</p> : null}
                        <p className="m-0 text-[0.8125rem] text-muted-foreground">
                          Sent {formatDate(r.created_at)}
                          {r.reviewed_at ? <> &middot; {REQUEST_NOTE[r.status] || "Reviewed"} {formatDate(r.reviewed_at)}</> : null}
                        </p>
                      </div>
                      <StatusPill status={r.status} />
                    </Row>
                  ))}
                </RowList>
              ) : (
                <p className="m-0 rounded-lg border border-dashed border-line-strong px-4 py-3 text-sm text-muted-foreground">
                  You have not asked for any class yet.
                </p>
              )
            ) : null}
          </Panel>
        </div>

        <Panel title="Request a class" className="lg:sticky lg:top-6">
          <RequestClassForm />
        </Panel>
      </div>
    </>
  );
}
