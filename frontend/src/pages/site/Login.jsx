import { useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { AuthCard } from "@/components/app/AuthLayout";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Notice } from "@/components/app/Notice";
import { CaptchaField } from "@/components/app/CaptchaField";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError } from "@/lib/api";
import { usePageTitle } from "@/hooks/usePageTitle";

export default function Login() {
  usePageTitle("Sign in");
  const { login } = useAuth();
  const location = useLocation();
  const [params] = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null); // { message, fields }
  const [needsCaptcha, setNeedsCaptcha] = useState(false); // the server asks for one after repeated failures
  const [captcha, setCaptcha] = useState({ id: "", answer: "" });
  const [captchaKey, setCaptchaKey] = useState(0);

  const justRegistered = location.state?.registered;
  const needsSignIn = params.get("next");

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!identifier.trim() || !password) {
      setError({ message: "", fields: { ...(!identifier.trim() && { identifier: "Enter your email, USN or Faculty ID." }), ...(!password && { password: "Enter your password." }) } });
      return;
    }
    if (needsCaptcha && !captcha.answer.trim()) {
      setError({ message: "", fields: { captcha: "Type the characters shown in the image." } });
      return;
    }
    setBusy(true);
    try {
      const user = await login({
        identifier: identifier.trim(), password,
        ...(needsCaptcha ? { captcha_id: captcha.id, captcha_answer: captcha.answer } : {}),
      });
      toast.success(`Welcome back${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}.`);
      // GuestOnly sees the new session and redirects to ?next= or the role's home.
    } catch (err) {
      const fields = err instanceof ApiError ? err.fields : {};
      if (err instanceof ApiError && (err.code === "captcha_required" || fields.captcha)) setNeedsCaptcha(true);
      if (needsCaptcha || fields.captcha) setCaptchaKey((k) => k + 1); // challenges are single use
      setError({ message: err.message, fields, rateLimited: err.isRateLimited });
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Sign in"
      lead="Use your email, Faculty ID or USN with your Campus Connect password."
      footer={
        <>
          <span>New student? <Link to="/signup/student">Create a student account</Link></span>
          <span>New faculty? <Link to="/signup/faculty">Register as faculty</Link></span>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="grid gap-4">
        {justRegistered ? <Notice tone="success">Your account is ready. Sign in to get started.</Notice> : null}
        {needsSignIn && !justRegistered ? <Notice tone="info">Sign in to continue where you left off.</Notice> : null}
        {error?.message && !Object.keys(error.fields || {}).length ? (
          <Notice tone={error.rateLimited ? "warning" : "danger"}>{error.message}</Notice>
        ) : null}

        <FormField label="Email, Faculty ID or USN" hint="Students can use their USN, faculty their Faculty ID, and everyone their email." error={error?.fields?.identifier}>
          <Input
            autoFocus
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
          />
        </FormField>
        <FormField label="Password" error={error?.fields?.password}>
          <PasswordInput autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </FormField>
        {needsCaptcha ? (
          <CaptchaField label="Security check" resetKey={captchaKey} onChange={setCaptcha} error={error?.fields?.captcha} />
        ) : null}
        <SubmitButton className="mt-1 w-full" loading={busy} loadingText="Signing in">Sign in</SubmitButton>
      </form>
    </AuthCard>
  );
}
