import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, LayoutGrid } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { ClassPath } from "@/components/app/ClassPath";
import { StatusPill } from "@/components/app/StatusPill";
import { EmptyState } from "@/components/app/EmptyState";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { pluralize } from "@/lib/format";
import { FilterSelect, FilterTabs, ListSkeletonRows, QueryError, SearchBox, includesText } from "@/features/admin/common";

const uniq = (arr) => [...new Set(arr)];

export default function AdminClasses() {
  const q = useQuery({ queryKey: adminKeys.classes, queryFn: adminApi.classes });
  const [search, setSearch] = useState("");
  const [branch, setBranch] = useState("");
  const [department, setDepartment] = useState("");
  const [year, setYear] = useState("");
  const [state, setState] = useState("");

  const items = useMemo(() => q.data?.items || [], [q.data]);
  const branches = useMemo(() => uniq(items.map((c) => c.branch)), [items]);
  const departments = useMemo(() => uniq(items.filter((c) => !branch || c.branch === branch).map((c) => c.department)), [items, branch]);
  const years = useMemo(() => uniq(items.map((c) => c.year)).sort(), [items]);

  const rows = useMemo(() => items.filter((c) => {
    if (branch && c.branch !== branch) return false;
    if (department && c.department !== department) return false;
    if (year && c.year !== year) return false;
    if (state === "active" && !c.is_active) return false;
    if (state === "inactive" && c.is_active) return false;
    if (state === "nofaculty" && c.faculty_count > 0) return false;
    return includesText(`${c.label} ${c.faculty.map((f) => `${f.faculty_code} ${f.full_name}`).join(" ")}`, search);
  }), [items, search, branch, department, year, state]);

  return (
    <>
      <PageHeader title="Classes" description="Every class with the faculty assigned to it. Open one to see its students." />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))]">
        <SearchBox value={search} onChange={setSearch} label="Search classes" placeholder="Class, faculty name or ID" className="sm:col-span-2 lg:col-span-1" />
        <FilterSelect label="Branch" allLabel="All branches" value={branch} onChange={(v) => { setBranch(v); setDepartment(""); }} options={branches} />
        <FilterSelect label="Department" allLabel="All departments" value={department} onChange={setDepartment} options={departments} />
        <FilterSelect label="Year" allLabel="All years" value={year} onChange={setYear} options={years} />
      </div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <FilterTabs
          label="Class status"
          value={state}
          onChange={setState}
          options={[
            { value: "", label: "All" },
            { value: "active", label: "Active" },
            { value: "inactive", label: "Inactive" },
            { value: "nofaculty", label: "No faculty" },
          ]}
        />
        {q.data ? <p className="m-0 text-sm text-muted-foreground" aria-live="polite">{rows.length} of {items.length} classes</p> : null}
      </div>

      {q.isPending ? <ListSkeletonRows rows={6} /> : null}
      {q.isError ? <QueryError error={q.error} onRetry={q.refetch} /> : null}
      {q.data && !rows.length ? (
        <div className="rounded-lg border bg-card shadow-sm"><EmptyState icon={LayoutGrid} title="No classes match">Try clearing a filter.</EmptyState></div>
      ) : null}

      {rows.length ? (
        <ul className="m-0 list-none overflow-hidden rounded-lg border bg-card p-0 shadow-sm">
          {rows.map((c) => (
            <li key={c.section_id} className="border-b border-line last:border-b-0">
              <Link to={`/admin/classes/${c.section_id}`} className="group flex items-center gap-3 px-4 py-3 text-inherit no-underline transition-colors hover:bg-primary-soft">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <ClassPath cls={c} />
                    {!c.is_active ? <StatusPill status="INACTIVE" label="Inactive" /> : null}
                  </div>
                  <p className="mt-1 mb-0 text-[0.8125rem] text-muted-foreground">
                    {c.faculty.length ? (
                      <>
                        <span className="sr-only">Faculty: </span>
                        {c.faculty.map((f, i) => (
                          <span key={f.assignment_id}>{i > 0 ? ", " : ""}<span className="font-mono text-ink-2" title={f.full_name}>{f.faculty_code}</span></span>
                        ))}
                      </>
                    ) : "No faculty assigned"}
                  </p>
                </div>
                <span className="num shrink-0 text-sm text-muted-foreground">{pluralize(c.student_count, "student")}</span>
                <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
