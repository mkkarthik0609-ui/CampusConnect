import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { AuthCard } from "@/components/app/AuthLayout";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Notice } from "@/components/app/Notice";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError } from "@/lib/api";
import { authApi } from "@/lib/endpoints";
import { conditionalPasskeysAvailable, getPasskey, passkeyErrorMessage, passkeysSupported } from "@/lib/passkey";
import { usePageTitle } from "@/hooks/usePageTitle";

const failure = (err) => (err instanceof ApiError ? err.message : passkeyErrorMessage(err));

export default function AdminLogin() {
  usePageTitle("Admin Login");
  const { adminLogin, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const conditional = useRef(null); // AbortController of the autofill ("conditional UI") passkey request

  const welcome = (user) => toast.success(`Welcome back${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}.`);

  const passkeySignIn = useCallback(async (credential, identifier) => {
    await authApi.adminPasskeyLogin({ credential, identifier });
    const fresh = await refresh();
    welcome(fresh?.user);
  }, [refresh]);

  // Offer passkeys in the browser's autofill list of the email field; sign in as soon as one is chosen.
  const startConditional = useCallback(async () => {
    conditional.current?.abort();
    const ctl = new AbortController();
    conditional.current = ctl;
    try {
      if (!(await conditionalPasskeysAvailable()) || ctl.signal.aborted) return;
      const { options } = await authApi.adminPasskeyOptions();
      if (ctl.signal.aborted) return;
      const credential = await getPasskey(options, { mediation: "conditional", signal: ctl.signal });
      if (ctl.signal.aborted) return;
      setBusy(true);
      await passkeySignIn(credential, "");
    } catch (err) {
      if (!ctl.signal.aborted) { setBusy(false); setError(failure(err)); }
    }
  }, [passkeySignIn]);

  useEffect(() => {
    startConditional();
    return () => conditional.current?.abort();
  }, [startConditional]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    conditional.current?.abort();
    const identifier = email.trim();
    if (!password) { // empty password -> passkey (modal prompt)
      if (!passkeysSupported()) {
        setError("Enter your password, or use a browser that supports passkeys.");
        return;
      }
      setBusy(true);
      try {
        const { options } = await authApi.adminPasskeyOptions();
        await passkeySignIn(await getPasskey(options), identifier);
      } catch (err) {
        setError(failure(err));
        setBusy(false);
        startConditional();
      }
      return;
    }
    if (!identifier) {
      setError("Enter your email address.");
      startConditional();
      return;
    }
    setBusy(true);
    try {
      welcome(await adminLogin({ identifier, password }));
    } catch (err) {
      setError(failure(err));
      setBusy(false);
      startConditional();
    }
  }

  return (
    <AuthCard
      title="Admin Login"
      lead="Have a passkey? Leave the password empty."
      footer={<span>Not an administrator? <Link to="/login">Sign in as student or faculty</Link></span>}
    >
      <form onSubmit={onSubmit} noValidate className="grid gap-4">
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <FormField label="Email">
          <Input
            autoFocus
            type="email"
            autoComplete="username webauthn"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </FormField>
        <FormField label="Password">
          <PasswordInput autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </FormField>
        <SubmitButton className="mt-1 w-full" loading={busy} loadingText="Signing in">Open admin portal</SubmitButton>
      </form>
    </AuthCard>
  );
}
