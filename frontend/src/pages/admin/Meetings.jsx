import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { DataTable } from "@/components/app/DataTable";
import { ClassPath } from "@/components/app/ClassPath";
import { StatusPill } from "@/components/app/StatusPill";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import { FilterTabs, PersonCell, SearchBox, includesText, statusParam } from "@/features/admin/common";

const STATUSES = [
  { value: "", label: "All" },
  { value: "PENDING", label: "Pending" },
  { value: "ACCEPTED", label: "Accepted" },
  { value: "COMPLETED", label: "Completed" },
  { value: "REJECTED", label: "Rejected" },
  { value: "CANCELLED", label: "Cancelled" },
];

export default function AdminMeetings() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const q = useQuery({ queryKey: adminKeys.meetings(status), queryFn: () => adminApi.meetings(statusParam(status)) });
  const items = useMemo(() => q.data?.items || [], [q.data]);
  const rows = useMemo(
    () => items.filter((m) => includesText(`${m.student.full_name} ${m.student.usn} ${m.faculty.full_name} ${m.faculty.faculty_code} ${m.reason}`, search)),
    [items, search],
  );

  return (
    <>
      <PageHeader title="Meetings" description="All meeting requests between students and faculty. Faculty decide them; this view is read-only." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchBox value={search} onChange={setSearch} label="Search meetings" placeholder="Student, faculty or reason" className="w-full sm:w-72" />
        <FilterTabs label="Filter by status" value={status} onChange={setStatus} options={STATUSES} />
        {q.data ? <p className="m-0 text-sm text-muted-foreground" aria-live="polite">{rows.length} shown</p> : null}
      </div>
      <DataTable
        caption="Meeting requests"
        rows={rows}
        loading={q.isPending}
        error={q.error}
        empty={{ icon: CalendarDays, title: "No meetings found", children: status || search ? "Try another filter." : "Meeting requests appear here once students send them." }}
        columns={[
          { key: "student", header: "Student", primary: true, cell: (m) => (
            <div className="grid min-w-0 gap-1 max-sm:justify-items-start">
              <PersonCell name={m.student.full_name} src={m.student.profile_picture_url} sub={m.student.usn} mono />
              {m.student.class ? <ClassPath cls={m.student.class} /> : null}
            </div>
          ) },
          { key: "faculty", header: "Faculty", cell: (m) => <PersonCell name={m.faculty.full_name} src={m.faculty.profile_picture_url} sub={m.faculty.faculty_code} mono /> },
          { key: "reason", header: "Reason", cell: (m) => (
            <div className="max-w-[26ch] text-left text-sm max-sm:max-w-none max-sm:text-right">
              <div className="font-semibold text-foreground">{m.reason}</div>
              {m.faculty_response ? <div className="text-muted-foreground">Reply: {m.faculty_response}</div> : null}
              {m.cancellation_reason ? <div className="text-muted-foreground">Cancelled: {m.cancellation_reason}</div> : null}
            </div>
          ) },
          { key: "status", header: "Status", cell: (m) => <StatusPill status={m.status} /> },
          { key: "when", header: "When", cell: (m) => (
            <div className="num text-left text-sm max-sm:text-right">
              <div>{formatDateTime(m.requested_at)}</div>
              {m.meeting_time_text ? <div className="text-muted-foreground">Meet: {m.meeting_time_text}</div> : null}
            </div>
          ) },
        ]}
      />
    </>
  );
}
