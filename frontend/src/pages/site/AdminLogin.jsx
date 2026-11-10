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
import { errorMessage } from "@/lib/api";
import { usePageTitle } from "@/hooks/usePageTitle";

export default function AdminLogin() {
  usePageTitle("Admin Login");
  const { adminLogin } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    const identifier = email.trim();
    if (!identifier) { setError("Enter your email address."); return; }
    if (!password) { setError("Enter your password."); return; }
    setBusy(true);
    try {
      const user = await adminLogin({ identifier, password });
      toast.success(`Welcome back${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}.`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Admin Login"
      lead="Sign in with your administrator email and password."
      footer={<span>Not an administrator? <Link to="/login">Sign in as student or faculty</Link></span>}
    >
      <form onSubmit={onSubmit} noValidate className="grid gap-4">
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <FormField label="Email" required>
          <Input autoFocus type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        </FormField>
        <FormField label="Password" required>
          <PasswordInput autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </FormField>
        <SubmitButton className="mt-1 w-full" loading={busy} loadingText="Signing in">Open admin portal</SubmitButton>
      </form>
    </AuthCard>
  );
}
