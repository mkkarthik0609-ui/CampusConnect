import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Inbox, X } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { DataTable } from "@/components/app/DataTable";
import { ClassPath } from "@/components/app/ClassPath";
import { StatusPill } from "@/components/app/StatusPill";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/app/dialogs";
import { errorMessage } from "@/lib/api";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import { FilterTabs, PersonCell, statusParam } from "@/features/admin/common";

const FILTERS = [
  { value: "PENDING", label: "Pending" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
  { value: "", label: "All" },
];

export default function AdminAssignmentRequests() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [status, setStatus] = useState("PENDING");
  const q = useQuery({ queryKey: adminKeys.requests(status), queryFn: () => adminApi.assignmentRequests(statusParam(status)) });

  const decide = useMutation({
    mutationFn: ({ id, decision }) => adminApi.decideAssignmentRequest(id, decision),
    onSuccess: (res) => {
      toast.success(res.message);
      return Promise.all([
        qc.invalidateQueries({ queryKey: adminKeys.requestsAll }),
        qc.invalidateQueries({ queryKey: adminKeys.assignments }),
        qc.invalidateQueries({ queryKey: adminKeys.dashboard }),
        qc.invalidateQueries({ queryKey: adminKeys.faculty }),
        qc.invalidateQueries({ queryKey: adminKeys.classes }),
      ]);
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  async function reject(r) {
    const ok = await confirm({
      title: `Reject ${r.faculty.full_name}'s request?`,
      description: `${r.class.label}. They will be notified. They can ask again later.`,
      confirmLabel: "Reject request",
      destructive: true,
    });
    if (ok) decide.mutate({ id: r.id, decision: "reject" });
  }

  const pending = q.data?.pending_count;
  const busyId = decide.isPending ? decide.variables?.id : null;

  return (
    <>
      <PageHeader
        title="Class requests"
        description="Faculty ask to join a class. Nothing is granted until you approve it."
      />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <FilterTabs label="Filter by status" value={status} onChange={setStatus} options={FILTERS.map((f) => (f.value === "PENDING" && pending != null ? { ...f, count: pending } : f))} />
        {q.data ? <p className="m-0 text-sm text-muted-foreground" aria-live="polite">{q.data.total} shown</p> : null}
      </div>
      <DataTable
        caption="Faculty class requests"
        rows={q.data?.items}
        loading={q.isPending}
        error={q.error}
        empty={{ icon: Inbox, title: status === "PENDING" ? "No pending requests" : "No requests here", children: status === "PENDING" ? "When a faculty member asks to join a class it shows up here." : undefined }}
        columns={[
          { key: "faculty", header: "Faculty", primary: true, cell: (r) => <PersonCell name={r.faculty.full_name} src={r.faculty.profile_picture_url} sub={`${r.faculty.faculty_code} · ${r.faculty.department}`} /> },
          { key: "class", header: "Class", cell: (r) => (
            <div className="flex flex-col items-start gap-1 max-sm:items-end">
              <ClassPath cls={r.class} />
              {!r.class_active ? <StatusPill status="INACTIVE" label="Class inactive" /> : null}
            </div>
          ) },
          { key: "note", header: "Note", cell: (r) => r.note ? <span className="text-ink-2">{r.note}</span> : <span className="text-muted-foreground">No note</span> },
          { key: "created", header: "Requested", cell: (r) => <span className="num text-sm">{formatDateTime(r.created_at)}</span> },
          { key: "status", header: "Status", cell: (r) => <StatusPill status={r.status} /> },
          {
            key: "actions", header: <span className="sr-only">Actions</span>, label: "", align: "right",
            cell: (r) => r.can_decide ? (
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" size="sm" disabled={!r.class_active || busyId === r.id} onClick={() => decide.mutate({ id: r.id, decision: "approve" })} title={!r.class_active ? "Reactivate the class before approving" : undefined}>
                  <Check aria-hidden="true" />Approve<span className="sr-only"> {r.faculty.full_name}</span>
                </Button>
                <Button type="button" size="sm" variant="outline" disabled={busyId === r.id} onClick={() => reject(r)}>
                  <X aria-hidden="true" />Reject<span className="sr-only"> {r.faculty.full_name}</span>
                </Button>
              </div>
            ) : <span className="text-sm text-muted-foreground">{r.reviewed_at ? formatDateTime(r.reviewed_at) : ""}</span>,
          },
        ]}
      />
    </>
  );
}
