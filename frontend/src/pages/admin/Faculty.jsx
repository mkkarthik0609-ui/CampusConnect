import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { DataTable } from "@/components/app/DataTable";
import { ClassPath } from "@/components/app/ClassPath";
import { StatusPill } from "@/components/app/StatusPill";
import { Badge } from "@/components/ui/badge";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDate, pluralize } from "@/lib/format";
import { ActivePill, FilterSelect, PersonCell, SearchBox, includesText } from "@/features/admin/common";

function Classes({ f }) {
  const list = f.assignments;
  if (!list.length) return <span className="text-sm text-muted-foreground">None yet</span>;
  return (
    <details className="group text-left max-sm:text-right">
      <summary className="inline-flex min-h-8 cursor-pointer list-none items-center gap-1.5 rounded-md text-sm font-semibold text-primary hover:text-primary-hover [&::-webkit-details-marker]:hidden">
        {pluralize(list.length, "class", "classes")}
        <span className="text-muted-foreground group-open:hidden">(show)</span>
        <span className="hidden text-muted-foreground group-open:inline">(hide)</span>
      </summary>
      <ul className="m-0 mt-1.5 grid list-none gap-1.5 p-0">
        {list.map((a) => (
          <li key={a.assignment_id} className="flex flex-wrap items-center gap-1.5 max-sm:justify-end">
            <ClassPath cls={a} />
            {!a.class_active ? <StatusPill status="INACTIVE" label="Paused" /> : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function AdminFaculty() {
  const q = useQuery({ queryKey: adminKeys.faculty, queryFn: adminApi.faculty });
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("");
  const items = useMemo(() => q.data?.items || [], [q.data]);
  const depts = useMemo(() => [...new Set(items.map((f) => f.department).filter(Boolean))].sort(), [items]);
  const rows = useMemo(
    () => items.filter((f) => (!dept || f.department === dept) && includesText(`${f.full_name} ${f.faculty_code} ${f.email} ${f.subjects.join(" ")}`, search)),
    [items, search, dept],
  );

  return (
    <>
      <PageHeader title="Faculty" description="Everyone who teaches, with their subjects and assigned classes. Assign classes on the Assignments page." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchBox value={search} onChange={setSearch} label="Search faculty" placeholder="Name, ID, email or subject" className="w-full sm:w-72" />
        <FilterSelect label="Department" allLabel="All departments" value={dept} onChange={setDept} options={depts} className="w-full sm:w-56" />
        {q.data ? <p className="m-0 text-sm text-muted-foreground" aria-live="polite">{rows.length} of {items.length}</p> : null}
      </div>
      <DataTable
        caption="Faculty"
        rows={rows}
        rowKey={(f) => f.id}
        loading={q.isPending}
        error={q.error}
        empty={{ icon: BookOpen, title: items.length ? "No faculty match" : "No faculty yet", children: items.length ? "Try a different search." : "Faculty appear here after they sign up." }}
        columns={[
          { key: "name", header: "Faculty", primary: true, cell: (f) => <PersonCell name={f.full_name} src={f.profile_picture_url} sub={f.faculty_code} mono /> },
          { key: "dept", header: "Department", cell: (f) => f.department },
          { key: "subjects", header: "Subjects", cell: (f) => f.subjects.length ? (
            <div className="flex flex-wrap gap-1 max-sm:justify-end">{f.subjects.map((s) => <Badge key={s} variant="secondary">{s}</Badge>)}</div>
          ) : <span className="text-muted-foreground">None listed</span> },
          { key: "classes", header: "Classes", cell: (f) => <Classes f={f} /> },
          { key: "pending", header: "Requests", cell: (f) => f.pending_request_count ? (
            <Link to="/admin/assignment-requests" className="no-underline"><StatusPill status="PENDING" label={`${f.pending_request_count} pending`} /></Link>
          ) : <span className="text-muted-foreground">None</span> },
          { key: "status", header: "Status", cell: (f) => <ActivePill active={f.is_active} /> },
          { key: "last", header: "Last sign-in", cell: (f) => <span className="num text-sm">{f.last_login_at ? formatDate(f.last_login_at) : "Never"}</span> },
        ]}
      />
    </>
  );
}
