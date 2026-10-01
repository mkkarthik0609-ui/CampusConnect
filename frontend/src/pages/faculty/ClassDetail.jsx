import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Search, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DataTable } from "@/components/app/DataTable";
import { EmptyState } from "@/components/app/EmptyState";
import { ClassPath } from "@/components/app/ClassPath";
import { PageHeader } from "@/components/app/PageHeader";
import { pluralize } from "@/lib/format";
import { MessageButton, Panel, PersonCell, QueryError, Row, RowList } from "@/features/faculty/ui";
import { useClassDetail, useMessageStudent } from "@/features/faculty/hooks";

export default function FacultyClassDetail() {
  const { sectionId } = useParams();
  const query = useClassDetail(sectionId);
  const message = useMessageStudent();
  const [filter, setFilter] = useState("");

  const students = useMemo(() => {
    const all = query.data?.students || [];
    const q = filter.trim().toLowerCase();
    return q ? all.filter((s) => s.full_name.toLowerCase().includes(q) || s.usn.toLowerCase().includes(q)) : all;
  }, [query.data, filter]);

  if (query.error?.isForbidden) {
    return (
      <>
        <PageHeader title="Class not available" documentTitle="Class not available" back={{ to: "/faculty/classes", label: "My classes" }} />
        <div className="rounded-lg border bg-card shadow-sm">
          <EmptyState
            icon={ShieldAlert}
            title="You are not assigned to this class"
            action={<Button asChild><Link to="/faculty/classes">Back to my classes</Link></Button>}
          >
            <p>Admin controls who can see a class. If you should be teaching it, send a request from My classes and you will get access once it is approved.</p>
          </EmptyState>
        </div>
      </>
    );
  }

  const cls = query.data?.class;
  const total = query.data?.students?.length ?? 0;

  return (
    <>
      <PageHeader
        title={cls ? <ClassPath cls={cls} size="lg" /> : "Class"}
        documentTitle={cls ? `Class ${cls.label}` : "Class"}
        back={{ to: "/faculty/classes", label: "My classes" }}
        description={query.data ? `${pluralize(total, "registered student")}, ${pluralize(query.data.co_faculty.length, "faculty member")} teaching.` : undefined}
      />

      {query.isError && !query.error?.isForbidden ? <QueryError error={query.error} onRetry={() => query.refetch()} title="Could not load this class" /> : null}

      {!query.isError ? (
        <div className="grid items-start gap-x-10 gap-y-9 lg:grid-cols-[minmax(0,1fr)_16rem]">
          <Panel
            title="Students"
            count={query.data ? total : null}
            actions={
              total > 6 ? (
                <div className="relative w-full min-w-56 sm:w-64">
                  <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="search"
                    aria-label="Filter students by name or USN"
                    placeholder="Filter by name or USN"
                    className="pl-9"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  />
                </div>
              ) : null
            }
          >
            <DataTable
              caption="Students in this class"
              rows={students}
              loading={query.isPending}
              empty={
                filter
                  ? { title: "No student matches that filter", children: "Check the spelling or clear the filter." }
                  : { title: "No students registered yet", children: "Students appear here once they sign up and pick this section." }
              }
              columns={[
                {
                  key: "name",
                  header: "Student",
                  primary: true,
                  cell: (s) => <PersonCell name={s.full_name} src={s.profile_picture_url} />,
                },
                { key: "usn", header: "USN", cell: (s) => <span className="font-mono text-[0.8125rem]">{s.usn}</span> },
                { key: "phone", header: "Phone", cell: (s) => s.phone || <span className="text-muted-foreground">Not given</span> },
                {
                  key: "email",
                  header: "College email",
                                    cell: (s) => <span className="block max-w-40 truncate max-sm:max-w-none max-sm:whitespace-normal max-sm:break-all" title={s.college_email}>{s.college_email}</span>,
                },
                {
                  key: "actions",
                  header: <span className="sr-only">Actions</span>,
                  label: "",
                  align: "right",
                  cell: (s) => (
                    <MessageButton name={s.full_name} pending={message.isPending && message.variables === s.id} onClick={() => message.mutate(s.id)} />
                  ),
                },
              ]}
            />
          </Panel>

          <Panel title="Teaching this class" count={query.data?.co_faculty.length || null}>
            {query.data ? (
              <RowList label="Faculty assigned to this class">
                {query.data.co_faculty.map((f) => (
                  <Row key={f.id}>
                    <PersonCell
                      name={f.full_name}
                      src={f.profile_picture_url}
                      code={f.faculty_code}
                      extra={f.is_me ? <span className="rounded-full bg-primary-soft px-2 py-px text-xs font-bold text-primary-ink">You</span> : null}
                    />
                  </Row>
                ))}
              </RowList>
            ) : null}
          </Panel>
        </div>
      ) : null}
    </>
  );
}
