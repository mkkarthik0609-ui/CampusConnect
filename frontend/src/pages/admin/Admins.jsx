import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Circle, ShieldCheck, UserPlus } from "lucide-react";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { DataTable } from "@/components/app/DataTable";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { StatusPill } from "@/components/app/StatusPill";
import { Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import { ActivePill, PersonCell } from "@/features/admin/common";
import { cn } from "@/lib/utils";

const EMPTY = { full_name: "", email: "", password: "", confirm_password: "" };

function policy(password, email) {
  const local = email.split("@")[0]?.toLowerCase();
  const p = password.toLowerCase();
  return [
    { ok: password.length >= 8 && password.length <= 128, text: "8 to 128 characters" },
    { ok: /[A-Z]/.test(password), text: "An upper-case letter" },
    { ok: /[a-z]/.test(password), text: "A lower-case letter" },
    { ok: /\d/.test(password), text: "A digit" },
    { ok: !!password && p !== email.toLowerCase() && p !== local, text: "Not the same as the email" },
  ];
}

export default function AdminAdmins() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: adminKeys.admins, queryFn: adminApi.admins });
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});

  const create = useMutation({
    mutationFn: () => adminApi.createAdmin({ ...form, email: form.email.trim(), full_name: form.full_name.trim() }),
    onSuccess: (res) => {
      toast.success(res.message);
      setForm(EMPTY);
      setErrors({});
      return Promise.all([qc.invalidateQueries({ queryKey: adminKeys.admins }), qc.invalidateQueries({ queryKey: adminKeys.dashboard })]);
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields || {}).length) setErrors(err.fields);
      else toast.error(errorMessage(err));
    },
  });

  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); if (errors[k]) setErrors((x) => ({ ...x, [k]: "" })); };
  const rules = policy(form.password, form.email);

  function submit(e) {
    e.preventDefault();
    const next = {};
    if (!form.full_name.trim()) next.full_name = "Enter a full name.";
    if (!form.email.trim()) next.email = "Enter an email address.";
    if (rules.some((r) => !r.ok)) next.password = "The password does not meet every rule below.";
    if (form.password !== form.confirm_password) next.confirm_password = "Passwords do not match.";
    setErrors(next);
    if (!Object.keys(next).length) create.mutate();
  }

  return (
    <>
      <PageHeader title="Admin accounts" description="People who can manage Campus Connect. Create accounts only for people you trust." />

      <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <section aria-label="Admins">
          <SectionHeading title="Current admins" />
          <DataTable
            caption="Admin accounts"
            rows={q.data?.items}
            loading={q.isPending}
            error={q.error}
            empty={{ icon: ShieldCheck, title: "No admins" }}
            columns={[
              { key: "name", header: "Admin", primary: true, cell: (a) => (
                <div className="flex flex-wrap items-center gap-2">
                  <PersonCell name={a.full_name} src={a.profile_picture_url} sub={a.email} />
                  {a.is_you ? <StatusPill status="INFO" tone="info" label="You" /> : null}
                </div>
              ) },
              { key: "status", header: "Status", cell: (a) => <ActivePill active={a.is_active} /> },
              { key: "created", header: "Created", cell: (a) => <span className="num text-sm">{formatDate(a.created_at)}</span> },
              { key: "last", header: "Last sign-in", cell: (a) => <span className="num text-sm">{a.last_login_at ? formatDate(a.last_login_at) : "Never"}</span> },
            ]}
          />
        </section>

        <section aria-label="Create an admin" className="rounded-lg border bg-card p-5 shadow-sm">
          <SectionHeading title="Add an admin" />
          <form onSubmit={submit} noValidate className="grid gap-4">
            <FormField label="Full name" error={errors.full_name} required>
              <Input value={form.full_name} onChange={set("full_name")} autoComplete="off" maxLength={80} />
            </FormField>
            <FormField label="Email" error={errors.email} required>
              <Input type="email" value={form.email} onChange={set("email")} autoComplete="off" />
            </FormField>
            <FormField label="Password" error={errors.password} required>
              <PasswordInput value={form.password} onChange={set("password")} autoComplete="new-password" />
            </FormField>
            <ul className="m-0 -mt-1 grid list-none gap-1 p-0 text-[0.8125rem]" aria-label="Password rules">
              {rules.map((r) => (
                <li key={r.text} className={cn("flex items-center gap-1.5", r.ok ? "text-ok-ink" : "text-muted-foreground")}>
                  {r.ok ? <Check aria-hidden="true" className="size-3.5" /> : <Circle aria-hidden="true" className="size-3.5" />}
                  {r.text}
                  <span className="sr-only">{r.ok ? " (met)" : " (not met yet)"}</span>
                </li>
              ))}
            </ul>
            <FormField label="Confirm password" error={errors.confirm_password} required>
              <PasswordInput value={form.confirm_password} onChange={set("confirm_password")} autoComplete="new-password" />
            </FormField>
            <div>
              <SubmitButton loading={create.isPending} loadingText="Creating..."><UserPlus aria-hidden="true" />Create admin</SubmitButton>
            </div>
          </form>
        </section>
      </div>
    </>
  );
}
