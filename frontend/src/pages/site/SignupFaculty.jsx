import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AuthCard } from "@/components/app/AuthLayout";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Notice } from "@/components/app/Notice";
import { authApi } from "@/lib/endpoints";
import { ApiError, errorMessage } from "@/lib/api";
import { useFacultyDepartments } from "@/hooks/useFacultyDepartments";
import { usePageTitle } from "@/hooks/usePageTitle";

const PASSWORD_RULE = "At least 8 characters with an uppercase letter, a lowercase letter and a digit.";

/** /signup/faculty -> POST /api/auth/signup/faculty. Classes are assigned by Admin after registration. */
export default function SignupFaculty() {
  usePageTitle("Faculty registration");
  const navigate = useNavigate();
  const departments = useFacultyDepartments();
  const [form, setForm] = useState({ full_name: "", faculty_code: "", department: "", professional_email: "", subjects: "", password: "", confirm_password: "" });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => { setForm((f) => ({ ...f, [key]: e.target.value })); if (errors[key]) setErrors((x) => ({ ...x, [key]: "" })); };

  async function onSubmit(e) {
    e.preventDefault();
    const subjects = form.subjects.split(",").map((s) => s.trim()).filter(Boolean);
    const next = {};
    for (const [key, label] of [["full_name", "full name"], ["faculty_code", "Faculty ID"], ["professional_email", "professional email"], ["password", "password"]]) {
      if (!String(form[key]).trim()) next[key] = `Enter your ${label}.`;
    }
    if (!form.department) next.department = "Choose your department.";
    if (!subjects.length) next.subjects = "List at least one subject, separated by commas.";
    if (form.password && form.password !== form.confirm_password) next.confirm_password = "Passwords do not match.";
    if (Object.keys(next).length) { setErrors(next); setFormError("Check the highlighted fields."); return; }

    setBusy(true);
    setFormError("");
    try {
      await authApi.facultySignup({
        full_name: form.full_name.trim(),
        faculty_code: form.faculty_code.trim(),
        department: form.department,
        professional_email: form.professional_email.trim(),
        subjects,
        password: form.password,
        confirm_password: form.confirm_password,
      });
      toast.success("Registration successful. Please sign in.");
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (err) {
      const fields = err instanceof ApiError ? err.fields : {};
      setErrors(fields);
      setFormError(Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      wide
      title="Faculty registration"
      lead="Create your account with your Faculty ID. Admin assigns your classes once you have registered."
      footer={<span>Already have an account? <Link to="/login">Sign in</Link></span>}
    >
      <form onSubmit={onSubmit} noValidate className="grid gap-5">
        {formError ? <Notice tone="danger">{formError}</Notice> : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Full name" required error={errors.full_name}>
            <Input autoComplete="name" value={form.full_name} onChange={set("full_name")} />
          </FormField>
          <FormField label="Faculty ID" required error={errors.faculty_code}>
            <Input autoCapitalize="characters" spellCheck={false} value={form.faculty_code} onChange={set("faculty_code")} className="font-mono" />
          </FormField>
          <FormField label="Department" required error={errors.department}>
            {({ id, describedBy, invalid }) => (
              <Select value={form.department} onValueChange={(v) => { setForm((f) => ({ ...f, department: v })); setErrors((x) => ({ ...x, department: "" })); }}>
                <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid || undefined} className="w-full">
                  <SelectValue placeholder={departments.isPending ? "Loading departments" : "Select department"} />
                </SelectTrigger>
                <SelectContent position="popper">
                  {(departments.data || []).map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </FormField>
          <FormField label="Professional email" required error={errors.professional_email}>
            <Input type="email" autoComplete="email" value={form.professional_email} onChange={set("professional_email")} />
          </FormField>
        </div>
        <FormField label="Subjects you teach" required hint="Separate subjects with commas." error={errors.subjects}>
          <Input placeholder="Data Structures, Operating Systems" value={form.subjects} onChange={set("subjects")} />
        </FormField>
        <Notice tone="info">
          Classes and sections are assigned by Admin. After you sign in you can request additional classes from the My Classes page.
        </Notice>

        <section aria-labelledby="pw-h" className="border-t pt-5">
          <h2 id="pw-h" className="mb-4 text-xl">Password</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Campus Connect password" required hint={PASSWORD_RULE} error={errors.password}>
              <PasswordInput autoComplete="new-password" minLength={8} value={form.password} onChange={set("password")} />
            </FormField>
            <FormField label="Confirm password" required error={errors.confirm_password}>
              <PasswordInput autoComplete="new-password" minLength={8} value={form.confirm_password} onChange={set("confirm_password")} />
            </FormField>
          </div>
        </section>

        <SubmitButton className="w-full" loading={busy} loadingText="Creating account">Create account</SubmitButton>
      </form>
    </AuthCard>
  );
}
