import { PageHeader } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/StatusPill";
import { EmptyState } from "@/components/app/EmptyState";
import { formatDate } from "@/lib/format";
import { ChangedFields, ClassLinkRow, ListSkeleton, NoClassesEmpty, Panel, QueryError, Row, RowList } from "@/features/faculty/ui";
import { PhotoUpload } from "@/features/faculty/PhotoUpload";
import { ProfileChangeForm } from "@/features/faculty/ProfileChangeForm";
import { useFacultyProfile } from "@/features/faculty/hooks";

function Detail({ label, children }) {
  return (
    <div className="grid gap-0.5 py-3 first:pt-0 last:pb-0 sm:grid-cols-[10rem_1fr] sm:gap-4">
      <dt className="text-sm font-semibold text-muted-foreground">{label}</dt>
      <dd className="m-0 min-w-0 break-words font-medium">{children}</dd>
    </div>
  );
}

export default function FacultyProfile() {
  const query = useFacultyProfile();
  const data = query.data;
  const profile = data?.profile;

  return (
    <>
      <PageHeader title="Profile" description="Your photo is yours to change. Department and professional email are changed by Admin after you ask." />

      {query.isError ? <QueryError error={query.error} onRetry={() => query.refetch()} title="Could not load your profile" /> : null}
      {query.isPending ? <ListSkeleton rows={4} /> : null}

      {data ? (
        <div className="grid items-start gap-x-10 gap-y-9 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
          <div className="grid min-w-0 gap-9">
            <section aria-label="Your details" className="grid gap-6 rounded-lg border bg-card p-5 shadow-sm">
              <PhotoUpload name={profile.full_name} src={profile.profile_picture_url} />
              <dl className="m-0 divide-y divide-line">
                <Detail label="Name">{profile.full_name}</Detail>
                <Detail label="Faculty ID"><span className="font-mono text-[0.9375rem]">{profile.faculty_code}</span></Detail>
                <Detail label="Department">{profile.department || "Not set"}</Detail>
                <Detail label="Professional email">{profile.professional_email || profile.email}</Detail>
                <Detail label="Subjects">
                  {data.subjects.length ? (
                    <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                      {data.subjects.map((s) => <li key={s} className="rounded-full bg-sunken px-2.5 py-0.5 text-sm font-semibold text-ink-2">{s}</li>)}
                    </ul>
                  ) : <span className="text-muted-foreground">None listed</span>}
                </Detail>
              </dl>
            </section>

            <Panel title="Assigned classes" count={data.classes.length || null}>
              {data.classes.length ? (
                <RowList label="Assigned classes">{data.classes.map((c) => <ClassLinkRow key={c.section_id} cls={c} />)}</RowList>
              ) : (
                <div className="rounded-lg border bg-card shadow-sm"><NoClassesEmpty /></div>
              )}
            </Panel>
          </div>

          <div className="grid min-w-0 gap-9">
            <Panel title="Ask Admin for a change">
              <div className="rounded-lg border bg-card p-5 shadow-sm">
                <ProfileChangeForm current={profile} fallbackDepartments={data.departments} />
              </div>
            </Panel>

            <Panel title="Change requests" count={data.change_requests.length || null}>
              {data.change_requests.length ? (
                <RowList label="My profile change requests">
                  {data.change_requests.map((r) => (
                    <Row key={r.id} className="items-start">
                      <div className="grid min-w-0 flex-1 basis-52 gap-1.5">
                        <ChangedFields changes={r.requested_changes} />
                        {r.reason ? <p className="m-0 text-sm text-ink-2">&ldquo;{r.reason}&rdquo;</p> : null}
                        <p className="m-0 text-[0.8125rem] text-muted-foreground">
                          Sent {formatDate(r.created_at)}{r.reviewed_at ? <> &middot; reviewed {formatDate(r.reviewed_at)}</> : null}
                        </p>
                      </div>
                      <StatusPill status={r.status} />
                    </Row>
                  ))}
                </RowList>
              ) : (
                <div className="rounded-lg border bg-card shadow-sm">
                  <EmptyState compact className="px-4" title="No requests yet">Changes you ask Admin for are listed here with their outcome.</EmptyState>
                </div>
              )}
            </Panel>
          </div>
        </div>
      ) : null}
    </>
  );
}
