import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, KeyRound, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { DataTable } from "@/components/app/DataTable";
import { FormField } from "@/components/app/FormField";
import { SubmitButton } from "@/components/app/SubmitButton";
import { StatusPill } from "@/components/app/StatusPill";
import { Notice } from "@/components/app/Notice";
import { useConfirm } from "@/components/app/dialogs";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import { createPasskey, passkeyErrorMessage, passkeysSupported } from "@/lib/passkey";
import { ActivePill, PersonCell } from "@/features/admin/common";

const EMPTY = { full_name: "", email: "" };

/** Shows a generated temporary password exactly once (create / reset). */
function TemporaryPasswordDialog({ secret, onClose }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(secret.password);
      toast.success("Password copied.");
    } catch {
      toast.error("Could not copy. Select the password and copy it manually.");
    }
  }
  return (
    <Dialog open={!!secret} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{secret?.title}</DialogTitle>
          <DialogDescription>
            Share this temporary password with {secret?.email} through a secure channel. It is shown only once. They sign in with it on the
            admin login page, then can add a passkey.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <code className="num min-w-0 flex-1 rounded-md border bg-sunken px-3 py-2 font-mono text-base break-all select-all">{secret?.password}</code>
          <Button type="button" variant="outline" onClick={copy}><Copy aria-hidden="true" />Copy</Button>
        </div>
        <DialogFooter>
          <Button type="button" onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddAdminDialog({ open, onOpenChange, onCreated }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});

  useEffect(() => { if (open) { setForm(EMPTY); setErrors({}); } }, [open]);

  const create = useMutation({
    mutationFn: () => adminApi.createAdmin({ full_name: form.full_name.trim(), email: form.email.trim() }),
    onSuccess: (res) => {
      onOpenChange(false);
      onCreated({ title: "Admin account created", email: res.admin.email, password: res.temporary_password });
      return Promise.all([qc.invalidateQueries({ queryKey: adminKeys.admins }), qc.invalidateQueries({ queryKey: adminKeys.dashboard })]);
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields || {}).length) setErrors(err.fields);
      else toast.error(errorMessage(err));
    },
  });

  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); if (errors[k]) setErrors((x) => ({ ...x, [k]: "" })); };

  function submit(e) {
    e.preventDefault();
    const next = {};
    if (!form.full_name.trim()) next.full_name = "Enter a full name.";
    if (!form.email.trim()) next.email = "Enter an email address.";
    setErrors(next);
    if (!Object.keys(next).length) create.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!create.isPending) onOpenChange(next); }}>
      <DialogContent>
        <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-4">
          <DialogHeader>
            <DialogTitle>Add an admin</DialogTitle>
            <DialogDescription>
              New admins have the same permissions as you, including adding other admins. A one-time temporary password is generated for them.
            </DialogDescription>
          </DialogHeader>
          <FormField label="Full name" error={errors.full_name} required>
            <Input autoFocus value={form.full_name} onChange={set("full_name")} autoComplete="off" maxLength={120} />
          </FormField>
          <FormField label="Email" error={errors.email} required>
            <Input type="email" value={form.email} onChange={set("email")} autoComplete="off" />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={create.isPending} onClick={() => onOpenChange(false)}>Cancel</Button>
            <SubmitButton loading={create.isPending} loadingText="Creating...">Create admin</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PasskeysPanel() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: adminKeys.passkeys, queryFn: adminApi.passkeys });
  const [label, setLabel] = useState("");
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: adminKeys.passkeys }), qc.invalidateQueries({ queryKey: adminKeys.admins })]);

  const add = useMutation({
    mutationFn: async () => {
      const { options } = await adminApi.passkeyOptions();
      return adminApi.addPasskey(await createPasskey(options), label.trim() || undefined);
    },
    onSuccess: () => { toast.success("Passkey added."); setLabel(""); return refresh(); },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : passkeyErrorMessage(err)),
  });

  async function remove(p) {
    if (!(await confirm({ title: `Remove "${p.label}"?`, description: "You will no longer be able to sign in with it.", confirmLabel: "Remove", destructive: true }))) return;
    try {
      await adminApi.removePasskey(p.id);
      toast.success("Passkey removed.");
      await refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <section aria-label="Your passkeys" className="rounded-lg border bg-card p-5 shadow-sm">
      <SectionHeading title="Your passkeys" />
      <p className="-mt-1 mb-4 text-sm text-muted-foreground">
        Sign in with your fingerprint, face or screen lock instead of a password. Leave the password empty on the admin login page.
      </p>
      {!passkeysSupported() ? <Notice tone="warning" className="mb-4">This browser does not support passkeys.</Notice> : null}
      <ul className="m-0 mb-4 grid grid-cols-1 list-none gap-2 p-0">
        {(q.data?.items || []).map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
            <div className="min-w-0">
              <p className="m-0 flex items-center gap-2 font-semibold"><KeyRound aria-hidden="true" className="size-4 shrink-0" /><span className="truncate">{p.label}</span></p>
              <p className="m-0 text-[0.8125rem] text-muted-foreground">
                Added {formatDate(p.created_at)} · {p.last_used_at ? `last used ${formatDate(p.last_used_at)}` : "never used"}
              </p>
            </div>
            <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove ${p.label}`} onClick={() => remove(p)}><Trash2 aria-hidden="true" /></Button>
          </li>
        ))}
        {q.data && !q.data.items.length ? <li className="text-sm text-muted-foreground">No passkeys yet.</li> : null}
        {q.error ? <li><Notice tone="danger">{errorMessage(q.error)}</Notice></li> : null}
      </ul>
      <form
        onSubmit={(e) => { e.preventDefault(); add.mutate(); }}
        className="grid grid-cols-1 gap-3"
      >
        <FormField label="Name (optional)">
          <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} placeholder="e.g. Work laptop" autoComplete="off" />
        </FormField>
        <div>
          <SubmitButton disabled={!passkeysSupported()} loading={add.isPending} loadingText="Waiting for your device...">Add a passkey</SubmitButton>
        </div>
      </form>
    </section>
  );
}

export default function AdminAdmins() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: adminKeys.admins, queryFn: adminApi.admins });
  const [adding, setAdding] = useState(false);
  const [secret, setSecret] = useState(null);

  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: adminKeys.admins }), qc.invalidateQueries({ queryKey: adminKeys.dashboard })]);

  async function run(action) {
    try {
      const res = await action();
      toast.success(res.message);
      await refresh();
      return res;
    } catch (err) {
      toast.error(errorMessage(err));
      return null;
    }
  }

  async function toggleActive(a) {
    const next = !a.is_active;
    const ok = await confirm({
      title: `${next ? "Reactivate" : "Deactivate"} ${a.full_name}?`,
      description: next ? "They will be able to sign in again." : "They are signed out and cannot sign in until you reactivate them.",
      confirmLabel: next ? "Reactivate" : "Deactivate",
      destructive: !next,
    });
    if (ok) await run(() => adminApi.setAdminActive(a.id, next));
  }

  async function resetPassword(a) {
    const ok = await confirm({
      title: `Reset the password for ${a.full_name}?`,
      description: "Their current password stops working. You get a new temporary password to share with them.",
      confirmLabel: "Reset password",
      destructive: true,
    });
    if (!ok) return;
    const res = await run(() => adminApi.resetAdminPassword(a.id));
    if (res) setSecret({ title: "Temporary password set", email: a.email, password: res.temporary_password });
  }

  async function revokePasskeys(a) {
    const ok = await confirm({
      title: `Revoke all passkeys for ${a.full_name}?`,
      description: "They can still sign in with their password.",
      confirmLabel: "Revoke passkeys",
      destructive: true,
    });
    if (ok) await run(() => adminApi.revokeAdminPasskeys(a.id));
  }

  const isPrimary = Boolean(q.data?.items.find((a) => a.is_you)?.is_primary);

  return (
    <>
      <PageHeader
        title="Admin accounts"
        description={isPrimary
          ? "You are the primary administrator. Only you can appoint, deactivate or reset other admins. Only appoint people you trust."
          : "Only the primary administrator can appoint or manage admin accounts."}
        actions={isPrimary ? <Button type="button" onClick={() => setAdding(true)}><UserPlus aria-hidden="true" />Add an admin</Button> : null}
      />

      <div className="grid grid-cols-1 items-start gap-8 min-[100rem]:grid-cols-[minmax(0,1fr)_24rem]">
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
              { key: "passkeys", header: "Passkeys", cell: (a) => <span className="num text-sm">{a.passkey_count}</span> },
              { key: "created", header: "Created", cell: (a) => <span className="num text-sm">{formatDate(a.created_at)}</span> },
              { key: "last", header: "Last sign-in", cell: (a) => <span className="num text-sm">{a.last_login_at ? formatDate(a.last_login_at) : "Never"}</span> },
              { key: "actions", header: <span className="sr-only">Actions</span>, label: "", align: "right", cell: (a) => (
                a.is_primary ? <span className="text-sm text-muted-foreground">Protected</span> : !isPrimary ? null : (
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button type="button" size="sm" variant="outline" disabled={a.is_you && a.is_active} onClick={() => toggleActive(a)}>
                      {a.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                    <Button type="button" size="sm" variant="outline" onClick={() => resetPassword(a)}>Reset password</Button>
                    {a.passkey_count ? <Button type="button" size="sm" variant="outline" onClick={() => revokePasskeys(a)}>Revoke passkeys</Button> : null}
                  </div>
                )
              ) },
            ]}
          />
        </section>

        <PasskeysPanel />
      </div>

      <AddAdminDialog open={adding} onOpenChange={setAdding} onCreated={setSecret} />
      <TemporaryPasswordDialog secret={secret} onClose={() => setSecret(null)} />
    </>
  );
}
