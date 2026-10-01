import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { ClassPath } from "@/components/app/ClassPath";
import { StatusPill } from "@/components/app/StatusPill";
import { Notice } from "@/components/app/Notice";
import { EmptyState } from "@/components/app/EmptyState";
import { PageLoader } from "@/components/app/PageLoader";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { pluralize } from "@/lib/format";
import { PersonCell, QueryError } from "@/features/admin/common";
import { StudentsTable } from "@/features/admin/StudentsTable";
import { UserRoundX } from "lucide-react";

export default function AdminClassDetail() {
  const { sectionId } = useParams();
  const q = useQuery({ queryKey: adminKeys.classDetail(sectionId), queryFn: () => adminApi.classDetail(sectionId) });

  if (q.isPending) return <PageLoader />;
  if (q.isError) {
    return (
      <>
        <PageHeader title="Class" back={{ to: "/admin/classes", label: "All classes" }} />
        <QueryError error={q.error} onRetry={q.refetch} />
      </>
    );
  }

  const { class: c, faculty, students } = q.data;
  const live = students.filter((s) => !s.is_removed);

  return (
    <>
      <PageHeader
        title={<ClassPath cls={c} size="lg" />}
        documentTitle={`Class ${c.label}`}
        back={{ to: "/admin/classes", label: "All classes" }}
        description={`${pluralize(c.student_count, "student")} registered, ${pluralize(c.faculty_count, "faculty member")} assigned.`}
        actions={<StatusPill status={c.is_active ? "ACTIVE" : "INACTIVE"} label={c.is_active ? "Active" : "Inactive"} />}
      />

      {!c.is_active ? (
        <Notice tone="warning" className="mb-5" title="This class is inactive">
          It is hidden from registration and faculty access is paused. Reactivate it in Academic structure.
        </Notice>
      ) : null}

      <section aria-label="Faculty" className="mb-8">
        <SectionHeading title="Faculty" />
        {faculty.length ? (
          <ul className="m-0 grid list-none gap-x-6 gap-y-1 p-0 sm:grid-cols-2 lg:grid-cols-3">
            {faculty.map((f) => (
              <li key={f.assignment_id} className="rounded-lg border bg-card px-4 py-3">
                <PersonCell name={f.full_name} src={f.profile_picture_url} sub={f.faculty_code} mono />
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-lg border bg-card shadow-sm">
            <EmptyState icon={UserRoundX} compact title="No faculty assigned" className="px-4">Assign someone from the Assignments page.</EmptyState>
          </div>
        )}
      </section>

      <section aria-label="Students">
        <SectionHeading title={`Students (${live.length})`} />
        <StudentsTable
          rows={students}
          showClass={false}
          caption={`Students in ${c.label}`}
          empty={{ title: "No students in this class yet", children: "They appear once they register and pick this class." }}
        />
      </section>
    </>
  );
}
