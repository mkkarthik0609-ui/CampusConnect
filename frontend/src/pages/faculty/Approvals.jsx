import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/app/dialogs";
import { EmptyState } from "@/components/app/EmptyState";
import { PageHeader } from "@/components/app/PageHeader";
import { ClassPath } from "@/components/app/ClassPath";
import { facultyApi } from "@/lib/endpoints";
import { timeAgo } from "@/lib/format";
import { ChangedFields, ListSkeleton, PersonCell, QueryError, RowList } from "@/features/faculty/ui";
import { usePermissionRequests, useRefreshFaculty } from "@/features/faculty/hooks";

export default function FacultyApprovals() {
  const query = usePermissionRequests();
  const refresh = useRefreshFaculty();
  const [pending, setPending] = useState(null); // { request, decision }

  const decide = useMutation({
    mutationFn: ({ request, decision }) => facultyApi.decidePermissionRequest(request.id, decision),
    onSuccess: (data) => {
      toast.success(data.message || "Done.");
      refresh();
    },
    onError: () => refresh(), // e.g. already reviewed elsewhere: reload the list
  });

  const items = query.data?.items || [];
  const approving = pending?.decision === "approve";
  const name = pending?.request.student?.full_name || pending?.request.requester_name;

  return (
    <>
      <PageHeader
        title="Approvals"
        description="Students in your classes need your say before their phone number or personal email changes. Approving applies the change straight away."
      />

      {query.isPending ? <ListSkeleton rows={3} /> : null}
      {query.isError ? <QueryError error={query.error} onRetry={() => query.refetch()} title="Could not load approvals" /> : null}

      {query.data ? (
        items.length ? (
          <RowList label="Pending student profile changes" className="max-w-3xl">
            {items.map((r) => (
              <li key={r.id} className="grid gap-4 px-4 py-4 sm:grid-cols-[1fr_auto] sm:items-start">
                <div className="grid min-w-0 gap-3">
                  <div className="grid gap-1.5">
                    <PersonCell name={r.student?.full_name || r.requester_name} src={r.student?.profile_picture_url} code={r.student?.usn} extra={<span>asked {timeAgo(r.created_at)}</span>} />
                    {r.student?.class ? <div className="pl-12"><ClassPath cls={r.student.class} /></div> : null}
                  </div>
                  <div className="grid gap-2 rounded-md bg-sunken px-3.5 py-3 sm:ml-12">
                    <p className="m-0 text-xs font-bold tracking-[0.04em] text-muted-foreground uppercase">Wants to change</p>
                    <ChangedFields changes={r.requested_changes} />
                    {r.reason ? <p className="m-0 text-sm text-ink-2">Reason: {r.reason}</p> : null}
                  </div>
                </div>
                <div className="flex items-center gap-2 sm:flex-col sm:items-stretch">
                  <Button type="button" size="sm" onClick={() => setPending({ request: r, decision: "approve" })} aria-label={`Approve change for ${r.student?.full_name || r.requester_name}`}>
                    <Check aria-hidden="true" /> Approve
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => setPending({ request: r, decision: "reject" })} aria-label={`Reject change for ${r.student?.full_name || r.requester_name}`}>
                    <X aria-hidden="true" /> Reject
                  </Button>
                </div>
              </li>
            ))}
          </RowList>
        ) : (
          <div className="max-w-3xl rounded-lg border bg-card shadow-sm">
            <EmptyState icon={ShieldCheck} title="Nothing waiting for you">
              <p>When a student in one of your classes asks to change their phone or personal email, it lands here.</p>
            </EmptyState>
          </div>
        )
      ) : null}

      <ConfirmDialog
        open={!!pending}
        onOpenChange={(open) => { if (!open) setPending(null); }}
        title={approving ? `Approve the change for ${name}?` : `Reject the change for ${name}?`}
        description={approving ? "Their profile is updated immediately and they are notified." : "Their profile stays as it is and they are notified."}
        confirmLabel={approving ? "Approve change" : "Reject change"}
        destructive={!approving}
        onConfirm={() => decide.mutateAsync(pending)}
      >
        {pending ? <ChangedFields changes={pending.request.requested_changes} className="rounded-md bg-sunken px-3.5 py-3" /> : null}
      </ConfirmDialog>
    </>
  );
}
