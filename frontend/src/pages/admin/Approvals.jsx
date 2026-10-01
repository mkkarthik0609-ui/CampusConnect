import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, CircleCheck, X } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { StatusPill } from "@/components/app/StatusPill";
import { useConfirm } from "@/components/app/dialogs";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import { FilterTabs, ListSkeletonRows, PersonCell, QueryError } from "@/features/admin/common";

const TYPE_LABEL = { FACULTY_PROFILE_CHANGE: "Faculty profile change", STUDENT_PROFILE_CHANGE: "Student profile change" };
const humanKey = (k) => String(k).replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const humanValue = (v) => (Array.isArray(v) ? v.join(", ") : v && typeof v === "object" ? JSON.stringify(v) : String(v ?? ""));

export default function AdminApprovals() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [filter, setFilter] = useState("PENDING");
  const q = useQuery({ queryKey: adminKeys.permissions, queryFn: adminApi.permissionRequests });

  const decide = useMutation({
    mutationFn: ({ id, decision }) => adminApi.decidePermission(id, decision),
    onSuccess: (res) => {
      toast.success(res.message);
      return Promise.all([
        qc.invalidateQueries({ queryKey: adminKeys.permissions }),
        qc.invalidateQueries({ queryKey: adminKeys.dashboard }),
        qc.invalidateQueries({ queryKey: adminKeys.faculty }),
      ]);
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  const items = useMemo(() => q.data?.items || [], [q.data]);
  const rows = useMemo(() => items.filter((r) => (filter === "PENDING" ? r.status === "PENDING" : true)), [items, filter]);

  async function reject(r) {
    const ok = await confirm({
      title: `Reject ${r.requester.full_name}'s change?`,
      description: "Their profile stays as it is and they are notified.",
      confirmLabel: "Reject change",
      destructive: true,
    });
    if (ok) decide.mutate({ id: r.id, decision: "reject" });
  }

  return (
    <>
      <PageHeader title="Profile approvals" description="Faculty ask permission before changing locked profile details. Student requests go to the faculty of their class." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <FilterTabs label="Filter requests" value={filter} onChange={setFilter} options={[{ value: "PENDING", label: "Pending", count: q.data?.pending }, { value: "ALL", label: "All" }]} />
      </div>

      {q.isPending ? <ListSkeletonRows rows={3} /> : null}
      {q.isError ? <QueryError error={q.error} onRetry={q.refetch} /> : null}
      {q.data && !rows.length ? (
        <div className="rounded-lg border bg-card shadow-sm"><EmptyState icon={CircleCheck} title={filter === "PENDING" ? "Nothing waiting for approval" : "No requests yet"}>Profile-change requests will show up here.</EmptyState></div>
      ) : null}

      <ul className="m-0 grid list-none gap-3 p-0">
        {rows.map((r) => {
          const changes = Object.entries(r.requested_changes || {});
          const pendingBusy = decide.isPending && decide.variables?.id === r.id;
          return (
            <li key={r.id} className="rounded-lg border bg-card p-4 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <PersonCell name={r.requester.full_name} src={r.requester.profile_picture_url} sub={`${r.requester.role === "FACULTY" ? r.requester.faculty_code : r.requester.usn} · ${TYPE_LABEL[r.request_type] || r.request_type}`} size="md" className="max-sm:justify-start" />
                <div className="flex items-center gap-2">
                  <span className="num text-sm text-muted-foreground">{formatDateTime(r.created_at)}</span>
                  <StatusPill status={r.status} />
                </div>
              </div>
              <dl className="m-0 mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[repeat(auto-fit,minmax(11rem,1fr))]">
                {changes.map(([k, v]) => (
                  <div key={k} className="rounded-md bg-surface-2 px-3 py-2">
                    <dt className="text-[0.8125rem] text-muted-foreground">Change {humanKey(k).toLowerCase()} to</dt>
                    <dd className="m-0 font-semibold break-words">{humanValue(v)}</dd>
                  </div>
                ))}
              </dl>
              {r.reason ? <p className="mt-3 mb-0 text-sm"><span className="font-semibold text-ink-2">Reason: </span>{r.reason}</p> : null}
              {r.status !== "PENDING" && r.approver ? <p className="mt-2 mb-0 text-sm text-muted-foreground">Reviewed by {r.approver.full_name}{r.reviewed_at ? ` on ${formatDateTime(r.reviewed_at)}` : ""}.</p> : null}
              {r.status === "PENDING" ? (
                r.can_decide ? (
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
                    <Button type="button" size="sm" disabled={pendingBusy} onClick={() => decide.mutate({ id: r.id, decision: "approve" })}><Check aria-hidden="true" />Approve<span className="sr-only"> change for {r.requester.full_name}</span></Button>
                    <Button type="button" size="sm" variant="outline" disabled={pendingBusy} onClick={() => reject(r)}><X aria-hidden="true" />Reject<span className="sr-only"> change for {r.requester.full_name}</span></Button>
                  </div>
                ) : (
                  <p className="mt-3 mb-0 border-t border-line pt-3 text-sm text-muted-foreground">This student request is decided by the faculty of their class, not by admins.</p>
                )
              ) : null}
            </li>
          );
        })}
      </ul>
    </>
  );
}
