import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { Notice } from "@/components/app/Notice";
import { Button } from "@/components/ui/button";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";
import { AcademicTree, AddInline } from "@/features/admin/AcademicTree";
import { ListSkeletonRows, QueryError } from "@/features/admin/common";
import { Layers } from "lucide-react";

export default function AdminAcademics() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: adminKeys.academics, queryFn: adminApi.academics });
  const [addingBranch, setAddingBranch] = useState(false);
  const branches = q.data?.branches || [];

  async function addBranch(name) {
    const res = await adminApi.addBranch(name);
    toast.success(res.message);
    await Promise.all([
      qc.invalidateQueries({ queryKey: adminKeys.academics }),
      qc.invalidateQueries({ queryKey: queryKeys.academicTree }),
    ]);
  }

  return (
    <>
      <PageHeader
        title="Academic structure"
        description="Branch, department, year and section. Students and faculty can only pick active classes."
        actions={<Button type="button" onClick={() => setAddingBranch((v) => !v)} aria-expanded={addingBranch}><Plus aria-hidden="true" />Add branch</Button>}
      />

      {addingBranch ? (
        <div className="mb-5 rounded-lg border border-dashed border-line-strong bg-card p-4">
          <AddInline label="Add branch" field="Branch name" placeholder="e.g. ECE" onSubmit={addBranch} onCancel={() => setAddingBranch(false)} />
        </div>
      ) : null}

      <Notice tone="info" className="mb-5" title="Deactivate instead of deleting">
        Deactivating hides a level and everything below it, and keeps all history. Delete is only offered for items with no students and no faculty assignments.
      </Notice>

      {q.isPending ? <ListSkeletonRows rows={3} /> : null}
      {q.isError ? <QueryError error={q.error} onRetry={q.refetch} /> : null}
      {q.data && !branches.length ? (
        <div className="rounded-lg border bg-card shadow-sm">
          <EmptyState icon={Layers} title="No branches yet" action={<Button type="button" onClick={() => setAddingBranch(true)}>Add the first branch</Button>}>
            Start with a branch such as CSE, then add its departments, years and sections.
          </EmptyState>
        </div>
      ) : null}
      {branches.length ? <AcademicTree key={branches.map((b) => b.id).join("-")} branches={branches} /> : null}
    </>
  );
}
