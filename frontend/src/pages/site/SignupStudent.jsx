import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { AuthCard } from "@/components/app/AuthLayout";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { ClassPicker } from "@/components/app/ClassPicker";
import { Notice } from "@/components/app/Notice";
import { CaptchaField } from "@/components/app/CaptchaField";
import { authApi } from "@/lib/endpoints";
import { ApiError, errorMessage } from "@/lib/api";
import { usePageTitle } from "@/hooks/usePageTitle";

const PASSWORD_RULE = "At least 8 characters with an uppercase letter, a lowercase letter and a digit.";

/**
 * /signup/student - one form: college email + details + class (ClassPicker -> section_id) + password + captcha
 * -> POST /api/auth/signup/student. The captcha is single use, so it is reloaded after every failed submit.
 */
export default function SignupStudent() {
  usePageTitle("Student registration");
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [form, setForm] = useState({ college_email: "", full_name: "", usn: "", phone: "", personal_email: "", password: "", confirm_password: "" });
  const [sectionId, setSectionId] = useState("");
  const [captcha, setCaptcha] = useState({ id: "", answer: "" });
  const [captchaKey, setCaptchaKey] = useState(0);

  const set = (key) => (e) => { setForm((f) => ({ ...f, [key]: e.target.value })); if (errors[key]) setErrors((x) => ({ ...x, [key]: "" })); };

  async function register(e) {
    e.preventDefault();
    const next = {};
    for (const [key, label] of [["college_email", "college email"], ["full_name", "full name"], ["usn", "USN"], ["phone", "phone number"], ["personal_email", "personal email"], ["password", "password"]]) {
      if (!String(form[key]).trim()) next[key] = `Enter your ${label}.`;
    }
    if (!sectionId) next.section_id = "Choose your branch, department, year and section.";
    if (form.password && form.password !== form.confirm_password) next.confirm_password = "Passwords do not match.";
    if (!captcha.answer.trim()) next.captcha = "Type the characters shown in the image.";
    if (Object.keys(next).length) { setErrors(next); setFormError("Check the highlighted fields."); return; }

    setBusy(true);
    setFormError("");
    try {
      await authApi.studentSignup({
        college_email: form.college_email.trim(),
        full_name: form.full_name.trim(),
        usn: form.usn.trim(),
        phone: form.phone.trim(),
        personal_email: form.personal_email.trim(),
        section_id: Number(sectionId),
        password: form.password,
        confirm_password: form.confirm_password,
        captcha_id: captcha.id,
        captcha_answer: captcha.answer,
      });
      toast.success("Registration successful. Please sign in.");
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (err) {
      const fields = err instanceof ApiError ? err.fields : {};
      setErrors(fields);
      setFormError(Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err));
      setCaptchaKey((k) => k + 1); // the server consumed this challenge
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      wide
      title="Student registration"
      lead="Create your account with your college email and a password."
      footer={<span>Already have an account? <Link to="/login">Sign in</Link></span>}
    >
      {formError ? <Notice tone="danger" className="mb-4">{formError}</Notice> : null}
      <form onSubmit={register} noValidate className="grid gap-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="College email" required error={errors.college_email} className="sm:col-span-2">
            <Input type="email" autoFocus autoComplete="email" inputMode="email" placeholder="you@college.edu" value={form.college_email} onChange={set("college_email")} />
          </FormField>
          <FormField label="Full name" required error={errors.full_name}>
            <Input autoComplete="name" value={form.full_name} onChange={set("full_name")} />
          </FormField>
          <FormField label="USN" required error={errors.usn} hint="6 to 15 letters and digits.">
            <Input autoCapitalize="characters" spellCheck={false} value={form.usn} onChange={set("usn")} className="font-mono" />
          </FormField>
          <FormField label="Phone" required error={errors.phone}>
            <Input type="tel" autoComplete="tel" inputMode="tel" value={form.phone} onChange={set("phone")} />
          </FormField>
          <FormField label="Personal email" required error={errors.personal_email}>
            <Input type="email" autoComplete="email" value={form.personal_email} onChange={set("personal_email")} />
          </FormField>
        </div>

        <section aria-labelledby="class-h" className="border-t pt-5">
          <h2 id="class-h" className="mb-1 text-xl">Your class</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Choose carefully. You cannot change this yourself later. If you pick the wrong class, contact Admin to remove the registration and register again.
          </p>
          <ClassPicker value={sectionId} onChange={(id) => { setSectionId(id); setErrors((x) => ({ ...x, section_id: "" })); }} error={errors.section_id} />
        </section>

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

        <section className="border-t pt-5">
          <CaptchaField resetKey={captchaKey} onChange={setCaptcha} error={errors.captcha} />
        </section>

        <SubmitButton className="w-full" loading={busy} loadingText="Creating account">Create account</SubmitButton>
      </form>
    </AuthCard>
  );
}
