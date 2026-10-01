import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { FormField } from "@/components/app/FormField";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, errorMessage } from "@/lib/api";
import { facultyApi } from "@/lib/endpoints";
import { useFacultyDepartments } from "@/hooks/useFacultyDepartments";
import { useRefreshFaculty } from "@/features/faculty/hooks";

/** Ask Admin to change department and/or professional email. Nothing changes until it is approved. */
export function ProfileChangeForm({ current, fallbackDepartments = [] }) {
  const refresh = useRefreshFaculty();
  const departmentsQuery = useFacultyDepartments();
  const departments = departmentsQuery.data?.length ? departmentsQuery.data : fallbackDepartments;

  const [department, setDepartment] = useState("");
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState({});

  const submit = useMutation({
    mutationFn: (body) => facultyApi.requestProfileChange(body),
    onSuccess: (data) => {
      toast.success(data.message || "Request sent to Admin.");
      setDepartment("");
      setEmail("");
      setReason("");
      setErrors({});
      refresh();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.isValidation && Object.keys(err.fields || {}).length) setErrors(err.fields);
      else toast.error(errorMessage(err));
    },
  });

  function onSubmit(e) {
    e.preventDefault();
    const next = {};
    const emailValue = email.trim();
    if (!department && !emailValue) next.form = "Choose a new department or enter a new professional email.";
    if (emailValue && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailValue)) next.professional_email = "Enter a valid email address.";
    if (!reason.trim()) next.reason = "Tell Admin why you need this change.";
    setErrors(next);
    if (Object.keys(next).length) return;
    submit.mutate({
      ...(department ? { department } : {}),
      ...(emailValue ? { professional_email: emailValue } : {}),
      reason: reason.trim(),
    });
  }

  const formError = errors.form || errors.department || (errors.validation_error ?? "");

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <FormField label="New department" error={errors.department} hint={current?.department ? `Currently ${current.department}` : undefined}>
          {({ id, describedBy, invalid }) => (
            <Select value={department} onValueChange={setDepartment} disabled={submit.isPending}>
              <SelectTrigger id={id} className="w-full" aria-describedby={describedBy} aria-invalid={invalid || undefined}>
                <SelectValue placeholder={departmentsQuery.isPending && !departments.length ? "Loading departments" : "Keep current"} />
              </SelectTrigger>
              <SelectContent position="popper">
                {departments.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        </FormField>
        <FormField label="New professional email" error={errors.professional_email} hint={current?.professional_email ? `Currently ${current.professional_email}` : undefined}>
          <Input type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@college.edu" />
        </FormField>
      </div>
      <FormField label="Reason" required error={errors.reason} hint="Admin reads this before approving.">
        <Textarea rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="I moved to the AIML department this semester" />
      </FormField>
      {formError ? <p role="alert" className="m-0 text-sm font-semibold text-danger-ink">{formError}</p> : null}
      <div>
        <SubmitButton loading={submit.isPending} loadingText="Sending...">
          <Send aria-hidden="true" /> Send to Admin
        </SubmitButton>
      </div>
    </form>
  );
}
