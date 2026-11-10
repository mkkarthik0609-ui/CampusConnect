import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { AuthCard } from "@/components/app/AuthLayout";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Notice } from "@/components/app/Notice";
import { PageLoader } from "@/components/app/PageLoader";
import { ApiError, errorMessage } from "@/lib/api";
import { authApi } from "@/lib/endpoints";
import { formatDate } from "@/lib/format";
import { usePageTitle } from "@/hooks/usePageTitle";

const PASSWORD_RULE = "At least 8 characters with an uppercase letter, a lowercase letter and a digit.";

/** The token lives in the URL fragment (never sent to a server): read it once, then strip it from the address bar. */
function takeToken() {
  const token = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("t") || "";
  if (window.location.hash) window.history.replaceState(null, "", window.location.pathname + window.location.search);
  return token;
}

export default function AdminInvite() {
  usePageTitle("Accept admin invitation");
  const [token] = useState(takeToken);
  const [invite, setInvite] = useState(null);
  const [loadError, setLoadError] = useState(token ? "" : "This invitation link is incomplete. Ask the primary administrator to send a new one.");
  const [form, setForm] = useState({ full_name: "", password: "", confirm_password: "" });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) return undefined;
    let live = true;
    authApi.inspectAdminInvite(token).then(
      (data) => { if (live) { setInvite(data); setForm((f) => ({ ...f, full_name: data.full_name || "" })); } },
      (err) => { if (live) setLoadError(errorMessage(err)); },
    );
    return () => { live = false; };
  }, [token]);

  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); if (errors[k]) setErrors((x) => ({ ...x, [k]: "" })); };

  async function onSubmit(e) {
    e.preventDefault();
    setFormError("");
    const next = {};
    if (!form.full_name.trim()) next.full_name = "Enter your full name.";
    if (!form.password) next.password = "Choose a password.";
    if (form.password && form.password !== form.confirm_password) next.confirm_password = "Passwords do not match.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setBusy(true);
    try {
      await authApi.acceptAdminInvite({ token, full_name: form.full_name.trim(), password: form.password, confirm_password: form.confirm_password });
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields || {}).length) setErrors(err.fields);
      else setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthCard title="Account ready" lead="Your administrator account has been created.">
        <Notice tone="success">You can now sign in with {invite?.email || "your email"} and the password you just chose.</Notice>
        <Link to="/admin-login" className="mt-6 inline-block font-semibold">Go to admin login</Link>
      </AuthCard>
    );
  }

  if (loadError) {
    return (
      <AuthCard title="Invitation unavailable" footer={<Link to="/admin-login">Back to admin login</Link>}>
        <Notice tone="danger">{loadError}</Notice>
      </AuthCard>
    );
  }

  if (!invite) return <PageLoader label="Checking your invitation" />;

  return (
    <AuthCard
      title="Accept invitation"
      lead={`You have been invited to administer Campus Connect${invite.expires_at ? `. This link expires ${formatDate(invite.expires_at)}` : ""}.`}
      footer={<Link to="/admin-login">Already have an account? Admin login</Link>}
    >
      <form onSubmit={onSubmit} noValidate className="grid gap-4">
        {formError ? <Notice tone="danger">{formError}</Notice> : null}
        <FormField label="Email">
          <Input type="email" value={invite.email} readOnly autoComplete="username" />
        </FormField>
        <FormField label="Full name" required error={errors.full_name}>
          <Input autoFocus autoComplete="name" maxLength={120} value={form.full_name} onChange={set("full_name")} />
        </FormField>
        <FormField label="Password" required hint={PASSWORD_RULE} error={errors.password}>
          <PasswordInput autoComplete="new-password" minLength={8} value={form.password} onChange={set("password")} />
        </FormField>
        <FormField label="Confirm password" required error={errors.confirm_password}>
          <PasswordInput autoComplete="new-password" minLength={8} value={form.confirm_password} onChange={set("confirm_password")} />
        </FormField>
        <SubmitButton className="mt-1 w-full" loading={busy} loadingText="Creating account">Create administrator account</SubmitButton>
      </form>
    </AuthCard>
  );
}
