import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/app/PageHeader";
import { Notice } from "@/components/app/Notice";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { FilterTabs, SearchBox, includesText } from "@/features/admin/common";
import { StudentsTable } from "@/features/admin/StudentsTable";

export default function AdminStudents() {
  const q = useQuery({ queryKey: adminKeys.students, queryFn: () => adminApi.students() });
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");

  const items = useMemo(() => q.data?.items || [], [q.data]);
  const unmapped = items.filter((s) => s.is_unmapped && !s.is_removed).length;
  const removed = items.filter((s) => s.is_removed).length;
  const rows = useMemo(
    () => items.filter((s) => {
      if (state === "live" && s.is_removed) return false;
      if (state === "unmapped" && !(s.is_unmapped && !s.is_removed)) return false;
      if (state === "removed" && !s.is_removed) return false;
      return includesText(`${s.full_name} ${s.usn} ${s.email} ${s.class?.label || ""}`, search);
    }),
    [items, search, state],
  );

  return (
    <>
      <PageHeader title="Students" description="Every registration, with the class each student belongs to." />

      {unmapped > 0 && state !== "unmapped" ? (
        <Notice tone="warning" className="mb-4" title={`${unmapped} ${unmapped === 1 ? "student has" : "students have"} no class`}>
          Their old class text matched no class, so they cannot reach faculty. Remove the registration and they can register again with the right class.
        </Notice>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchBox value={search} onChange={setSearch} label="Search students" placeholder="Name, USN, email or class" className="w-full sm:w-72" />
        <FilterTabs
          label="Filter students"
          value={state}
          onChange={setState}
          options={[
            { value: "", label: "All", count: q.data ? items.length : undefined },
            { value: "live", label: "Registered", count: q.data ? items.length - removed : undefined },
            { value: "unmapped", label: "Unmapped", count: q.data ? unmapped : undefined },
            { value: "removed", label: "Removed", count: q.data ? removed : undefined },
          ]}
        />
      </div>

      <StudentsTable
        rows={rows}
        loading={q.isPending}
        error={q.error}
        caption="All students"
        empty={{ title: items.length ? "No students match" : "No students yet", children: items.length ? "Try a different search or filter." : "Students appear here after they register with a class." }}
      />
    </>
  );
}
