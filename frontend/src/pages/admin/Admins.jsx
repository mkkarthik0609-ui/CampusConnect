import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Mail, ShieldCheck } from "lucide-react";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { DataTable } from "@/components/app/DataTable";
import { FormField } from "@/components/app/FormField";
import { SubmitButton } from "@/components/app/SubmitButton";
import { StatusPill } from "@/components/app/StatusPill";
import { Notice } from "@/components/app/Notice";
import { useConfirm } from "@/components/app/dialogs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import { ActivePill, PersonCell } from "@/features/admin/common";

const INVITE_TONE = { PENDING: "warn", EXPIRED: "neutral", ACCEPTED: "ok", REVOKED: "danger" };

/** After adding / renewing an admin: nothing is e-mailed, so remind the primary admin to pass on the admin ID. */
function InviteResult({ result, onDismiss }) {
  return (
    <Notice tone="success" title={`${result.invitation?.email} can now sign in at Admin Login with that e-mail and the admin ID. Tell them yourself.`}>
      <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>Dismiss</Button>
    </Notice>
  );
}

function InviteForm({ onResult }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ email: "", full_name: "" });
  const [errors, setErrors] = useState({});

  const invite = useMutation({
    mutationFn: () => adminApi.inviteAdmin({ email: form.email.trim(), ...(form.full_name.trim() ? { full_name: form.full_name.trim() } : {}) }),
    onSuccess: (res) => {
      setForm({ email: "", full_name: "" });
      onResult(res);
      return qc.invalidateQueries({ queryKey: adminKeys.adminInvitations });
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields || {}).length) setErrors(err.fields);
      else toast.error(errorMessage(err));
    },
  });

  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); if (errors[k]) setErrors((x) => ({ ...x, [k]: "" })); };

  function submit(e) {
    e.preventDefault();
    if (!form.email.trim()) { setErrors({ email: "Enter an email address." }); return; }
    setErrors({});
    invite.mutate();
  }

  return (
    <section aria-label="Invite administrator" className="rounded-lg border bg-card p-5 shadow-sm">
      <SectionHeading title="Invite administrator" />
      <p className="-mt-1 mb-4 text-sm text-muted-foreground">
        Nothing is e-mailed. Give them the admin ID yourself; they sign in at Admin Login with this e-mail and that ID. Admins have the same permissions as you apart from managing admins.
      </p>
      <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-start">
        <FormField label="Email" required error={errors.email}>
          <Input type="email" value={form.email} onChange={set("email")} autoComplete="off" />
        </FormField>
        <FormField label="Name (optional)" error={errors.full_name}>
          <Input value={form.full_name} onChange={set("full_name")} autoComplete="off" maxLength={120} />
        </FormField>
        <SubmitButton className="sm:mt-[1.625rem]" loading={invite.isPending} loadingText="Inviting...">
          <Mail aria-hidden="true" />Send invitation
        </SubmitButton>
      </form>
    </section>
  );
}

function InvitationsTable({ onResult }) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: adminKeys.adminInvitations, queryFn: adminApi.adminInvitations });
  const refresh = () => qc.invalidateQueries({ queryKey: adminKeys.adminInvitations });

  async function resend(inv) {
    try {
      onResult(await adminApi.resendAdminInvitation(inv.id));
      await refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function revoke(inv) {
    const ok = await confirm({
      title: `Revoke the invitation for ${inv.email}?`,
      description: "They will no longer be able to sign in as an admin.",
      confirmLabel: "Revoke",
      destructive: true,
    });
    if (!ok) return;
    try {
      await adminApi.revokeAdminInvitation(inv.id);
      toast.success("Invitation revoked.");
      await refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <section aria-label="Invitations">
      <SectionHeading title="Invitations" />
      <DataTable
        caption="Administrator invitations"
        rows={q.data?.items}
        loading={q.isPending}
        error={q.error}
        empty={{ icon: Mail, title: "No invitations yet" }}
        columns={[
          { key: "email", header: "Invitee", primary: true, cell: (i) => (
            <div className="min-w-0">
              <div className="truncate font-semibold">{i.full_name || i.email}</div>
              {i.full_name ? <div className="truncate text-[0.8125rem] text-muted-foreground">{i.email}</div> : null}
            </div>
          ) },
          { key: "status", header: "Status", cell: (i) => <StatusPill status={i.status} tone={INVITE_TONE[i.status]} /> },
          { key: "expires", header: "Expires", cell: (i) => <span className="num text-sm">{formatDate(i.expires_at)}</span> },
          { key: "actions", header: <span className="sr-only">Actions</span>, label: "", align: "right", cell: (i) => (
            i.status === "PENDING" || i.status === "EXPIRED" ? (
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => resend(i)}>Resend</Button>
                {i.status === "PENDING" ? <Button type="button" size="sm" variant="outline" onClick={() => revoke(i)}>Revoke</Button> : null}
              </div>
            ) : null
          ) },
        ]}
      />
    </section>
  );
}

export default function AdminAdmins() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: adminKeys.admins, queryFn: adminApi.admins });
  const [result, setResult] = useState(null);

  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: adminKeys.admins }), qc.invalidateQueries({ queryKey: adminKeys.dashboard })]);

  async function toggleActive(a) {
    const next = !a.is_active;
    const ok = await confirm({
      title: `${next ? "Reactivate" : "Deactivate"} ${a.full_name}?`,
      description: next ? "They will be able to sign in again." : "They are signed out and cannot sign in until you reactivate them.",
      confirmLabel: next ? "Reactivate" : "Deactivate",
      destructive: !next,
    });
    if (!ok) return;
    try {
      const res = await adminApi.setAdminActive(a.id, next);
      toast.success(res.message);
      await refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const isPrimary = Boolean(q.data?.items.find((a) => a.is_you)?.is_primary);

  return (
    <>
      <PageHeader
        title="Admin accounts"
        description={isPrimary
          ? "You are the primary administrator. Only you can invite, deactivate or reactivate other admins. Only invite people you trust."
          : "Only the primary administrator can invite or manage admin accounts."}
      />

      <div className="grid grid-cols-1 gap-8">
        <section aria-label="Admins">
          <SectionHeading title="Administrators" />
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
                  {a.is_primary ? <StatusPill status="INFO" tone="info" label="Primary" /> : null}
                  {a.is_you ? <StatusPill status="INFO" tone="info" label="You" /> : null}
                </div>
              ) },
              { key: "status", header: "Status", cell: (a) => <ActivePill active={a.is_active} /> },
              { key: "created", header: "Created", cell: (a) => <span className="num text-sm">{formatDate(a.created_at)}</span> },
              { key: "last", header: "Last sign-in", cell: (a) => <span className="num text-sm">{a.last_login_at ? formatDate(a.last_login_at) : "Never"}</span> },
              { key: "actions", header: <span className="sr-only">Actions</span>, label: "", align: "right", cell: (a) => (
                a.is_primary ? <span className="text-sm text-muted-foreground">Protected</span> : !isPrimary ? null : (
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button type="button" size="sm" variant="outline" disabled={a.is_you && a.is_active} onClick={() => toggleActive(a)}>
                      {a.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                  </div>
                )
              ) },
            ]}
          />
        </section>

        {isPrimary ? (
          <>
            {result ? <InviteResult result={result} onDismiss={() => setResult(null)} /> : null}
            <InviteForm onResult={setResult} />
            <InvitationsTable onResult={setResult} />
          </>
        ) : null}
      </div>
    </>
  );
}
