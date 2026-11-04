import { useState } from "react";
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
import { usePageTitle } from "@/hooks/usePageTitle";

const ADMIN_EMAIL = "mkkarthik0609@gmail.com";

export default function AdminLogin() {
  usePageTitle("Admin Login");
  const { adminLogin } = useAuth();
  const [email, setEmail] = useState(ADMIN_EMAIL);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (!email.trim() || !password) {
      setError("Enter the authorized admin email and password.");
      return;
    }
    setBusy(true);
    try {
      const user = await adminLogin({ identifier: email.trim(), password });
      toast.success(`Welcome back${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in.");
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Admin Login"
      lead="This portal is restricted to the authorized Campus Connect administrator."
      footer={<span>Not an administrator? <Link to="/login">Sign in as student or faculty</Link></span>}
    >
      <form onSubmit={onSubmit} noValidate className="grid gap-4">
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <FormField label="Admin email">
          <Input
            autoFocus
            type="email"
            autoComplete="username"
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
