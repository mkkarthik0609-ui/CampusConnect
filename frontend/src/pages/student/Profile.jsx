import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Info } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { ClassPath } from "@/components/app/ClassPath";
import { EmptyState } from "@/components/app/EmptyState";
import { FormField } from "@/components/app/FormField";
import { ListSkeleton } from "@/components/app/PageLoader";
import { Notice } from "@/components/app/Notice";
import { StatusPill } from "@/components/app/StatusPill";
import { SubmitButton } from "@/components/app/SubmitButton";
import { UserAvatar } from "@/components/app/UserAvatar";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError, errorMessage } from "@/lib/api";
import { studentApi } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

const panel = "rounded-lg border border-line bg-card shadow-sm";
const PHOTO_TYPES = ["image/png", "image/jpeg"];
const PHOTO_MAX = 3 * 1024 * 1024;

const FIELD_LABEL = { phone: "Phone", personal_email: "Personal email" };

/** /student/profile - details, profile photo, and contact-detail change requests. */
export default function StudentProfile() {
  const query = useQuery({ queryKey: queryKeys.studentProfile, queryFn: studentApi.profile });
  const s = query.data?.student;

  return (
    <>
      <PageHeader title="My profile" description={s?.class ? <ClassPath cls={s.class} /> : undefined} />
      {query.isPending ? (
        <ListSkeleton rows={4} />
      ) : query.isError ? (
        <Notice tone="danger" title="Could not load your profile">
          {query.error.message}
          <Button variant="outline" size="sm" className="mt-2" onClick={() => query.refetch()}>Try again</Button>
        </Notice>
      ) : (
        <div className="grid items-start gap-6 min-[64rem]:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <section aria-label="Your details" className={panel}>
            <PhotoBlock student={s} />
            <Details student={s} faculty={query.data.assigned_faculty} />
          </section>
          <div className="grid gap-6">
            <ChangeRequestForm student={s} hasFaculty={query.data.assigned_faculty.length > 0} />
            <RequestHistory items={query.data.permission_requests} />
          </div>
        </div>
      )}
    </>
  );
}

function PhotoBlock({ student }) {
  const qc = useQueryClient();
  const { patchUser } = useAuth();
  const input = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!file) { setPreview(null); return undefined; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const upload = useMutation({
    mutationFn: () => studentApi.uploadPicture(file),
    onSuccess: (res) => {
      toast.success(res.message || "Profile picture updated.");
      patchUser({ profile_picture_url: res.profile_picture_url });
      qc.invalidateQueries({ queryKey: queryKeys.studentProfile });
      qc.invalidateQueries({ queryKey: queryKeys.studentDashboard });
      setFile(null);
    },
    onError: (err) => toast.error(errorMessage(err, "Could not update your picture.")),
  });

  function pick(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!PHOTO_TYPES.includes(f.type)) return toast.error("Choose a PNG or JPG image.");
    if (f.size > PHOTO_MAX) return toast.error("That image is larger than 3 MB. Choose a smaller one.");
    setFile(f);
  }

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line p-5">
      {preview ? (
        <img src={preview} alt="Preview of your new profile picture" className="size-[104px] rounded-full border border-line object-cover" />
      ) : (
        <UserAvatar name={student.full_name} src={student.profile_picture_url} size="xl" alt={`Profile picture of ${student.full_name}`} />
      )}
      <div className="min-w-0 flex-1 basis-48">
        <p className="m-0 font-display text-xl font-[650] leading-tight break-words">{student.full_name}</p>
        <p className="m-0 mt-1 font-mono text-sm text-muted-foreground">{student.usn}</p>
        <input ref={input} type="file" accept="image/png,image/jpeg" capture="user" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={pick} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {file ? (
            <>
              <SubmitButton type="button" size="sm" loading={upload.isPending} onClick={() => upload.mutate()}>Save photo</SubmitButton>
              <Button type="button" size="sm" variant="secondary" disabled={upload.isPending} onClick={() => setFile(null)}>Discard</Button>
            </>
          ) : (
            <Button type="button" size="sm" variant="outline" onClick={() => input.current?.click()}>
              <Camera aria-hidden="true" /> {student.profile_picture_url ? "Change photo" : "Add a photo"}
            </Button>
          )}
        </div>
        <p className="m-0 mt-2 text-[0.8125rem] text-muted-foreground">PNG or JPG, up to 3 MB.</p>
      </div>
    </div>
  );
}

function Details({ student: s, faculty }) {
  const rows = [
    ["Branch", s.branch],
    ["Department", s.department],
    ["Year", s.year],
    ["Section", s.section],
    ["Phone", s.phone],
    ["Personal email", s.personal_email],
    ["College email", s.college_email],
    ["Class faculty", faculty.length ? faculty.map((f) => f.full_name).join(", ") : null],
  ];
  return (
    <div className="p-5">
      <dl className="m-0 grid grid-cols-[minmax(7rem,max-content)_minmax(0,1fr)] gap-x-5 gap-y-2.5">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="m-0 min-w-0 font-medium break-words">{value || <span className="text-muted-foreground">Not set</span>}</dd>
          </div>
        ))}
      </dl>
      <Notice tone="info" className="mt-5">
        Your branch, department, year and section cannot be changed here. If they are wrong, contact Admin.
      </Notice>
    </div>
  );
}

function ChangeRequestForm({ student, hasFaculty }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ phone: "", personal_email: "", reason: "" });
  const [errors, setErrors] = useState({});
  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); if (errors[k] || errors.form) setErrors({}); };

  const submit = useMutation({
    mutationFn: (body) => studentApi.changeRequest(body),
    onSuccess: (res) => {
      toast.success(res.message || "Request submitted.");
      setForm({ phone: "", personal_email: "", reason: "" });
      setErrors({});
      qc.invalidateQueries({ queryKey: queryKeys.studentProfile });
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields);
      else setErrors({ form: errorMessage(err) });
    },
  });

  function onSubmit(e) {
    e.preventDefault();
    const phone = form.phone.trim();
    const email = form.personal_email.trim();
    const reason = form.reason.trim();
    const next = {};
    if (!phone && !email) next.form = "Enter a new phone number or personal email.";
    if (!reason) next.reason = "Tell your class faculty why the detail is changing.";
    if (Object.keys(next).length) return setErrors(next);
    submit.mutate({ phone: phone || undefined, personal_email: email || undefined, reason });
  }

  return (
    <section aria-label="Request a contact change" className={`${panel} p-5`}>
      <SectionHeading title="Request a contact change" />
      <p className="mt-0 mb-4 text-[0.9688rem] text-muted-foreground">
        A new phone number or personal email is approved by your class faculty before it changes on your profile.
      </p>
      {!hasFaculty ? (
        <Notice tone="warning" title="No faculty is assigned to your class yet">
          Requests cannot be routed until Admin assigns someone. Please try again later.
        </Notice>
      ) : (
        <form onSubmit={onSubmit} noValidate className="grid gap-4">
          <div className="grid gap-4 min-[34rem]:grid-cols-2">
            <FormField label="New phone" error={errors.phone}>
              <Input type="tel" inputMode="tel" autoComplete="off" value={form.phone} onChange={set("phone")} placeholder={student.phone || undefined} />
            </FormField>
            <FormField label="New personal email" error={errors.personal_email}>
              <Input type="email" autoComplete="off" value={form.personal_email} onChange={set("personal_email")} placeholder={student.personal_email || undefined} />
            </FormField>
          </div>
          <FormField label="Reason" required error={errors.reason} hint="Your class faculty sees this with the request.">
            <Textarea rows={2} value={form.reason} maxLength={500} onChange={set("reason")} />
          </FormField>
          {errors.form ? <p role="alert" className="m-0 text-sm font-semibold text-danger-ink">{errors.form}</p> : null}
          <div>
            <SubmitButton loading={submit.isPending}>Send for approval</SubmitButton>
          </div>
        </form>
      )}
    </section>
  );
}

function summarize(changes) {
  return Object.entries(changes || {})
    .map(([k, v]) => `${FIELD_LABEL[k] || k.replace(/_/g, " ")}: ${v}`)
    .join(" / ");
}

function RequestHistory({ items }) {
  return (
    <section aria-label="Your change requests" className={panel}>
      <div className="px-5 pt-4 pb-1"><SectionHeading title="Your requests" /></div>
      {items.length === 0 ? (
        <EmptyState icon={Info} compact className="px-5 pb-5" title="No change requests yet">
          Requests you send for approval appear here with their status.
        </EmptyState>
      ) : (
        <ul className="m-0 list-none p-0">
          {items.map((r) => (
            <li key={r.id} className="grid gap-1 border-t border-line px-5 py-3.5 first:border-t-0">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <p className="m-0 min-w-0 font-semibold break-words">{summarize(r.requested_changes) || "Profile change"}</p>
                <StatusPill status={r.status} />
              </div>
              {r.reason ? <p className="m-0 text-[0.9688rem] text-ink-2">{r.reason}</p> : null}
              <p className="m-0 text-[0.8125rem] text-muted-foreground tabular-nums">
                Sent {formatDateTime(r.created_at)}
                {r.reviewed_at ? ` - decided ${formatDateTime(r.reviewed_at)}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
