import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Link2, Plus, Trash2, UserRoundX } from "lucide-react";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { FormField } from "@/components/app/FormField";
import { SubmitButton } from "@/components/app/SubmitButton";
import { ClassPicker } from "@/components/app/ClassPicker";
import { ClassPath } from "@/components/app/ClassPath";
import { ConfirmDialog } from "@/components/app/dialogs";
import { StatusPill } from "@/components/app/StatusPill";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, errorMessage } from "@/lib/api";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { pluralize } from "@/lib/format";
import { ListSkeletonRows, PersonCell, QueryError, SearchBox, includesText } from "@/features/admin/common";

export default function AdminAssignments() {
  const qc = useQueryClient();
  const formRef = useRef(null);
  const q = useQuery({ queryKey: adminKeys.assignments, queryFn: adminApi.assignments });
  const [facultyId, setFacultyId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [errors, setErrors] = useState({});
  const [search, setSearch] = useState("");
  const [removing, setRemoving] = useState(null); // { faculty, assignment }

  const items = useMemo(() => q.data?.items || [], [q.data]);
  const shown = useMemo(
    () => items.filter((f) => includesText(`${f.full_name} ${f.faculty_code} ${f.department}`, search)),
    [items, search],
  );

  const refresh = () => Promise.all([
    qc.invalidateQueries({ queryKey: adminKeys.assignments }),
    qc.invalidateQueries({ queryKey: adminKeys.faculty }),
    qc.invalidateQueries({ queryKey: adminKeys.classes }),
    qc.invalidateQueries({ queryKey: adminKeys.requestsAll }),
    qc.invalidateQueries({ queryKey: adminKeys.dashboard }),
  ]);

  const assign = useMutation({
    mutationFn: () => adminApi.assign(Number(facultyId), Number(sectionId)),
    onSuccess: (res) => { toast.success(res.message); setSectionId(""); setErrors({}); return refresh(); },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields || {}).length) setErrors(err.fields);
      else setErrors({});
      toast.error(errorMessage(err));
    },
  });

  function submit(e) {
    e.preventDefault();
    const next = {};
    if (!facultyId) next.faculty_id = "Choose a faculty member.";
    if (!sectionId) next.section_id = "Choose a class.";
    setErrors(next);
    if (Object.keys(next).length === 0) assign.mutate();
  }

  function startAssign(f) {
    setFacultyId(String(f.faculty_id));
    formRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
    formRef.current?.querySelector("button")?.focus({ preventScroll: true });
  }

  return (
    <>
      <PageHeader
        title="Faculty assignments"
        description="A faculty member sees, chats with and meets only the students of the classes assigned to them."
        actions={q.data?.pending_count ? <Button asChild variant="saffron"><Link to="/admin/assignment-requests">{pluralize(q.data.pending_count, "pending request")}</Link></Button> : null}
      />

      <section ref={formRef} aria-label="Assign a faculty member to a class" className="mb-8 rounded-lg border bg-card p-5 shadow-sm">
        <SectionHeading title="Assign a class" />
        <form onSubmit={submit} noValidate className="grid gap-4">
          <FormField label="Faculty member" error={errors.faculty_id} required>
            {({ id, describedBy, invalid }) => (
              <Select value={facultyId} onValueChange={(v) => { setFacultyId(v); setErrors((p) => ({ ...p, faculty_id: "" })); }}>
                <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid || undefined} className="w-full sm:max-w-md">
                  <SelectValue placeholder={q.isPending ? "Loading faculty..." : "Select faculty"} />
                </SelectTrigger>
                <SelectContent position="popper">
                  {items.map((f) => (
                    <SelectItem key={f.faculty_id} value={String(f.faculty_id)}>{f.full_name} ({f.faculty_code})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
          <ClassPicker value={sectionId} onChange={(id) => { setSectionId(id); setErrors((p) => ({ ...p, section_id: "" })); }} error={errors.section_id} />
          <div>
            <SubmitButton loading={assign.isPending} loadingText="Assigning..."><Link2 aria-hidden="true" />Assign to class</SubmitButton>
          </div>
        </form>
      </section>

      <SectionHeading title="Who is assigned where" actions={<SearchBox value={search} onChange={setSearch} label="Search faculty" placeholder="Search faculty" className="w-64 max-w-full" />} />

      {q.isPending ? <ListSkeletonRows rows={3} /> : null}
      {q.isError ? <QueryError error={q.error} onRetry={q.refetch} /> : null}
      {q.data && !shown.length ? (
        <div className="rounded-lg border bg-card shadow-sm">
          <EmptyState icon={UserRoundX} title={items.length ? "No faculty match your search" : "No faculty have registered yet"}>
            {items.length ? "Try a different name or code." : "Faculty appear here after they sign up."}
          </EmptyState>
        </div>
      ) : null}

      <ul className="m-0 grid list-none gap-3 p-0">
        {shown.map((f) => (
          <li key={f.faculty_id} className="rounded-lg border bg-card p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <PersonCell name={f.full_name} src={f.profile_picture_url} sub={`${f.faculty_code} · ${f.department}`} size="md" className="max-sm:justify-start" />
              <div className="flex flex-wrap items-center gap-2">
                {f.pending_requests?.length ? (
                  <Link to="/admin/assignment-requests" className="no-underline">
                    <StatusPill status="PENDING" label={`${pluralize(f.pending_requests.length, "request")} waiting`} />
                  </Link>
                ) : null}
                <Button type="button" variant="outline" size="sm" onClick={() => startAssign(f)}>
                  <Plus aria-hidden="true" />Assign class<span className="sr-only"> to {f.full_name}</span>
                </Button>
              </div>
            </div>
            {f.assignments.length ? (
              <ul className="m-0 mt-3 list-none divide-y divide-line border-t border-line p-0">
                {f.assignments.map((a) => (
                  <li key={a.assignment_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 py-2.5">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <ClassPath cls={a} />
                      {!a.class_active ? <StatusPill status="INACTIVE" label="Class paused" /> : null}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="num text-sm text-muted-foreground">{pluralize(a.student_count, "student")}</span>
                      <Button type="button" variant="ghost" size="sm" disabled={a.can_remove === false} onClick={() => setRemoving({ faculty: f, assignment: a })} className="text-destructive hover:bg-danger hover:text-danger-ink">
                        <Trash2 aria-hidden="true" />Remove<span className="sr-only"> {a.label} from {f.full_name}</span>
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 border-t border-line pt-3 text-sm text-muted-foreground">Not assigned to any class yet.</p>
            )}
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => { if (!o) setRemoving(null); }}
        title={removing ? `Remove ${removing.faculty.full_name} from this class?` : "Remove assignment"}
        description={removing ? `${removing.assignment.label}. They lose chat, meeting and class access for it straight away. History is kept, and you can assign them again later.` : ""}
        confirmLabel="Remove assignment"
        destructive
        onConfirm={async () => {
          const res = await adminApi.removeAssignment(removing.assignment.assignment_id);
          toast.success(res.message);
          await refresh();
        }}
      />
    </>
  );
}
