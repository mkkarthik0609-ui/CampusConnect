import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { AuthCard, Steps } from "@/components/app/AuthLayout";
import { FormField } from "@/components/app/FormField";
import { PasswordInput } from "@/components/app/PasswordInput";
import { SubmitButton } from "@/components/app/SubmitButton";
import { ClassPicker } from "@/components/app/ClassPicker";
import { Notice } from "@/components/app/Notice";
import { authApi } from "@/lib/endpoints";
import { ApiError, errorMessage } from "@/lib/api";
import { usePageTitle } from "@/hooks/usePageTitle";

const STEP_LABELS = ["College email", "Verify code", "Your details"];
const PASSWORD_RULE = "At least 8 characters with an uppercase letter, a lowercase letter and a digit.";

/**
 * /signup/student - three steps on one route:
 *   1. college email  -> POST /api/auth/signup/student/start
 *   2. 6-digit code   -> POST /api/auth/signup/student/verify
 *   3. details + class (ClassPicker -> section_id) + password -> POST /api/auth/signup/student/register
 * The server remembers the verified email in the session, so a reload mid-way restarts at step 1.
 */
export default function SignupStudent() {
  usePageTitle("Student registration");
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [demoOtp, setDemoOtp] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [form, setForm] = useState({ full_name: "", usn: "", phone: "", personal_email: "", password: "", confirm_password: "" });
  const [sectionId, setSectionId] = useState("");
  const headingRef = useRef(null);

  const set = (key) => (e) => { setForm((f) => ({ ...f, [key]: e.target.value })); if (errors[key]) setErrors((x) => ({ ...x, [key]: "" })); };

  function fail(err) {
    setFormError(err instanceof ApiError && Object.keys(err.fields).length ? "" : errorMessage(err));
    setErrors(err instanceof ApiError ? err.fields : {});
  }

  function go(next) {
    setStep(next);
    setErrors({});
    setFormError("");
    // Move the reader to the new step heading.
    window.requestAnimationFrame(() => document.getElementById("step-title")?.focus());
  }

  async function sendCode(e) {
    e?.preventDefault();
    if (!email.trim()) { setErrors({ college_email: "Enter your college email." }); return; }
    setBusy(true);
    setFormError("");
    try {
      const data = await authApi.studentStart(email.trim());
      setEmail(data.email || email.trim().toLowerCase());
      setDemoOtp(data.demo_otp || "");
      setNotice(data.message || "");
      setOtp("");
      go(2);
    } catch (err) {
      setErrors({}); fail(err);
      if (err instanceof ApiError && err.fields.college_email) setErrors({ college_email: err.fields.college_email });
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(e) {
    e.preventDefault();
    if (!/^\d{6}$/.test(otp)) { setErrors({ otp: "Enter the 6-digit code." }); return; }
    setBusy(true);
    setFormError("");
    try {
      await authApi.studentVerify(email, otp);
      toast.success("Email verified.");
      go(3);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function register(e) {
    e.preventDefault();
    const next = {};
    for (const [key, label] of [["full_name", "full name"], ["usn", "USN"], ["phone", "phone number"], ["personal_email", "personal email"], ["password", "password"]]) {
      if (!String(form[key]).trim()) next[key] = `Enter your ${label}.`;
    }
    if (!sectionId) next.section_id = "Choose your branch, department, year and section.";
    if (form.password && form.password !== form.confirm_password) next.confirm_password = "Passwords do not match.";
    if (Object.keys(next).length) { setErrors(next); setFormError("Check the highlighted fields."); return; }

    setBusy(true);
    setFormError("");
    try {
      await authApi.studentRegister({
        college_email: email,
        full_name: form.full_name.trim(),
        usn: form.usn.trim(),
        phone: form.phone.trim(),
        personal_email: form.personal_email.trim(),
        section_id: Number(sectionId),
        password: form.password,
        confirm_password: form.confirm_password,
      });
      toast.success("Registration successful. Please sign in.");
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (err) {
      fail(err);
      if (err instanceof ApiError && err.code === "otp_not_verified") go(2);
    } finally {
      setBusy(false);
    }
  }

  const titles = {
    1: ["Student registration", "Step 1 of 3. Verify your college email with a one-time code."],
    2: ["Verify your email", <>Step 2 of 3. Enter the 6-digit code for <strong className="break-all text-foreground">{email}</strong>.</>],
    3: ["Complete your registration", <>Step 3 of 3. Verified email: <strong className="break-all text-foreground">{email}</strong></>],
  };

  return (
    <AuthCard
      wide={step === 3}
      steps={<Steps current={step} labels={STEP_LABELS} />}
      title={<span id="step-title" tabIndex={-1} ref={headingRef} className="outline-none">{titles[step][0]}</span>}
      lead={titles[step][1]}
      footer={
        step === 1 ? <span>Already have an account? <Link to="/login">Sign in</Link></span> : step === 2 ? (
          <span>No code, or it expired?{" "}
            <button type="button" onClick={sendCode} disabled={busy} className="rounded-sm font-semibold text-primary underline underline-offset-2 hover:text-primary-hover disabled:opacity-60">Send a new code</button>
            {" "}or{" "}
            <button type="button" onClick={() => go(1)} className="rounded-sm font-semibold text-primary underline underline-offset-2 hover:text-primary-hover">use a different email</button>.
          </span>
        ) : null
      }
    >
      {formError ? <Notice tone="danger" className="mb-4">{formError}</Notice> : null}

      {step === 1 ? (
        <form onSubmit={sendCode} noValidate className="grid gap-4">
          <FormField label="College email" hint="We send a one-time code to confirm this address is yours." error={errors.college_email}>
            <Input type="email" autoFocus autoComplete="email" inputMode="email" placeholder="you@college.edu" value={email} onChange={(e) => { setEmail(e.target.value); setErrors({}); }} />
          </FormField>
          <SubmitButton className="w-full" loading={busy} loadingText="Sending code">Send code</SubmitButton>
        </form>
      ) : null}

      {step === 2 ? (
        <form onSubmit={verifyCode} noValidate className="grid gap-4">
          {demoOtp ? (
            <div role="status" className="grid gap-2 rounded-lg border-2 border-saffron bg-saffron-soft p-4 text-saffron-ink">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="text-[0.9375rem] font-semibold">Your demo code</span>
                <strong aria-label={demoOtp.split("").join(" ")} className="font-mono text-[2rem] sm:text-[2.5rem] leading-none font-semibold tracking-[0.22em] text-foreground">{demoOtp}</strong>
              </div>
              <p className="m-0 text-sm font-medium">Demo mode: the code is shown here instead of being emailed. Type it below.</p>
            </div>
          ) : notice ? <Notice tone="info">{notice}</Notice> : null}
          <FormField label="Verification code" hint="Six digits." error={errors.otp}>
            <Input
              autoFocus
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              pattern="[0-9]{6}"
              value={otp}
              onChange={(e) => { setOtp(e.target.value.replace(/\D/g, "").slice(0, 6)); setErrors({}); }}
              className="py-3 text-center font-mono text-2xl tracking-[0.35em]"
            />
          </FormField>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => go(1)} disabled={busy}>Back</Button>
            <SubmitButton className="flex-1" loading={busy} loadingText="Verifying">Verify</SubmitButton>
          </div>
        </form>
      ) : null}

      {step === 3 ? (
        <form onSubmit={register} noValidate className="grid gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
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

          <SubmitButton className="w-full" loading={busy} loadingText="Creating account">Create account</SubmitButton>
        </form>
      ) : null}
    </AuthCard>
  );
}
