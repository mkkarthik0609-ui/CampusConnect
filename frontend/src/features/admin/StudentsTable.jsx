import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UserMinus, Users } from "lucide-react";
import { DataTable } from "@/components/app/DataTable";
import { ClassPath } from "@/components/app/ClassPath";
import { ConfirmDialog } from "@/components/app/dialogs";
import { StatusPill } from "@/components/app/StatusPill";
import { Button } from "@/components/ui/button";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import { PersonCell } from "@/features/admin/common";

function ClassCell({ s }) {
  if (s.class) return <ClassPath cls={s.class} />;
  const l = s.legacy_class;
  return (
    <div className="flex flex-col items-start gap-1 max-sm:items-end">
      <StatusPill status="PENDING" label="Unmapped" />
      {l ? <span className="text-[0.8125rem] text-muted-foreground">Old entry: {[l.branch, l.department, l.year, l.section].filter(Boolean).join(" / ") || "none"}</span> : null}
    </div>
  );
}

/** Student list used by Students and ClassDetail. Owns the "Remove registration" dialog. */
export function StudentsTable({ rows, loading, error, empty, showClass = true, caption = "Students" }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState(null);

  const columns = [
    { key: "name", header: "Student", primary: true, cell: (s) => <PersonCell name={s.full_name} src={s.profile_picture_url} sub={s.usn} mono /> },
    showClass && { key: "class", header: "Class", cell: (s) => <ClassCell s={s} /> },
    { key: "contact", header: "Contact", cell: (s) => (
      <div className="min-w-0 text-left text-[0.8125rem] max-sm:text-right">
        <div className="truncate">{s.email}</div>
        {s.phone ? <div className="num text-muted-foreground">{s.phone}</div> : null}
      </div>
    ) },
    { key: "registered", header: "Registered", cell: (s) => <span className="num text-sm">{formatDate(s.registered_at)}</span> },
    { key: "status", header: "Status", cell: (s) => (s.is_removed ? <StatusPill status="CANCELLED" label="Removed" /> : <StatusPill status="ACTIVE" label="Active" />) },
    {
      key: "actions", header: <span className="sr-only">Actions</span>, label: "", align: "right",
      cell: (s) => s.can_remove_registration && !s.is_removed ? (
        <Button type="button" variant="ghost" size="sm" className="text-destructive hover:bg-danger hover:text-danger-ink" onClick={() => setTarget(s)}>
          <UserMinus aria-hidden="true" />Remove registration<span className="sr-only"> for {s.full_name}</span>
        </Button>
      ) : s.is_removed ? <span className="text-sm text-muted-foreground">Can register again</span> : null,
    },
  ].filter(Boolean);

  return (
    <>
      <DataTable
        caption={caption}
        rows={rows}
        loading={loading}
        error={error}
        empty={{ icon: Users, ...empty }}
        columns={columns}
      />
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => { if (!o) setTarget(null); }}
        title={target ? `Remove ${target.full_name}'s registration?` : "Remove registration"}
        description={target ? `This deactivates the account for ${target.usn}. The student can register again with the same USN and email, for example with the correct class. Their open meetings are cancelled; chats and history are kept.` : ""}
        confirmLabel="Remove registration"
        destructive
        onConfirm={async () => {
          const res = await adminApi.removeRegistration(target.id);
          toast.success(res.message);
          await Promise.all([
            qc.invalidateQueries({ queryKey: adminKeys.students }),
            qc.invalidateQueries({ queryKey: adminKeys.classes }),
            qc.invalidateQueries({ queryKey: adminKeys.dashboard }),
            qc.invalidateQueries({ queryKey: adminKeys.faculty }),
            qc.invalidateQueries({ queryKey: adminKeys.assignments }),
          ]);
        }}
      />
    </>
  );
}
