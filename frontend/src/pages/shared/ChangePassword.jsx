import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/app/PageHeader";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Notice } from "@/components/app/Notice";
import { useAuth } from "@/auth/AuthProvider";
import { accountApi } from "@/lib/endpoints";
import { ApiError, errorMessage } from "@/lib/api";
import { homeFor } from "@/lib/nav";

/** /account/password -> POST /api/account/password. You stay signed in on this device. */
export default function ChangePassword() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => { setForm((f) => ({ ...f, [key]: e.target.value })); if (errors[key]) setErrors((x) => ({ ...x, [key]: "" })); };

  async function onSubmit(e) {
    e.preventDefault();
    const next = {};
    if (!form.current_password) next.current_password = "Enter your current password.";
    if (!form.new_password) next.new_password = "Enter a new password.";
    if (form.new_password && form.new_password !== form.confirm_password) next.confirm_password = "New password and confirmation do not match.";
    if (Object.keys(next).length) { setErrors(next); setFormError(""); return; }

    setBusy(true);
    setFormError("");
    try {
      await accountApi.changePassword(form);
      toast.success("Your password has been changed.");
      navigate(homeFor(role), { replace: true });
    } catch (err) {
      const fields = err instanceof ApiError ? err.fields : {};
      setErrors(fields);
      setFormError(Object.keys(fields).length ? "" : errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Change password" description="Choose a password you do not use anywhere else. You stay signed in on this device." />
      <div className="max-w-xl rounded-lg border bg-card p-[clamp(1rem,2vw,1.4rem)] shadow-sm">
        <form onSubmit={onSubmit} noValidate className="grid gap-4">
          {formError ? <Notice tone="danger">{formError}</Notice> : null}
          <FormField label="Current password" error={errors.current_password}>
            <PasswordInput autoComplete="current-password" value={form.current_password} onChange={set("current_password")} />
          </FormField>
          <FormField label="New password" hint="At least 8 characters with an uppercase letter, a lowercase letter and a digit." error={errors.new_password}>
            <PasswordInput autoComplete="new-password" minLength={8} value={form.new_password} onChange={set("new_password")} />
          </FormField>
          <FormField label="Confirm new password" error={errors.confirm_password}>
            <PasswordInput autoComplete="new-password" minLength={8} value={form.confirm_password} onChange={set("confirm_password")} />
          </FormField>
          <div className="mt-1 flex flex-wrap gap-2">
            <SubmitButton loading={busy} loadingText="Saving">Change password</SubmitButton>
            <Button type="button" variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
          </div>
        </form>
      </div>
    </>
  );
}
