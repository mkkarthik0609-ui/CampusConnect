import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { ClassPicker, classPayload } from "@/components/app/ClassPicker";
import { FormField } from "@/components/app/FormField";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, errorMessage } from "@/lib/api";
import { facultyApi } from "@/lib/endpoints";
import { useRefreshFaculty } from "@/features/faculty/hooks";

/** Ask the Admin for a class. Nothing opens until the Admin approves. */
export function RequestClassForm() {
  const refresh = useRefreshFaculty();
  const [sectionId, setSectionId] = useState("");
  const [classInfo, setClassInfo] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const request = useMutation({
    mutationFn: () => facultyApi.requestClass({ ...classPayload(sectionId, classInfo), ...(note.trim() ? { note: note.trim() } : {}) }),
    onSuccess: (data) => {
      toast.success(data.message || "Request sent to Admin.");
      setSectionId("");
      setClassInfo(null);
      setNote("");
      setError("");
      refresh();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.isValidation && err.fields?.section_id) setError(err.fields.section_id);
      else toast.error(errorMessage(err));
    },
  });

  function submit(e) {
    e.preventDefault();
    if (!sectionId && !classInfo?.custom) {
      setError("Choose a branch, department, year and section first.");
      return;
    }
    setError("");
    request.mutate();
  }

  return (
    <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-5 rounded-lg border bg-card p-5 shadow-sm">
      <ClassPicker
        allowCustom
        value={sectionId}
        error={error}
        onChange={(id, info) => { setSectionId(id); setClassInfo(info); if (id || info) setError(""); }}
        disabled={request.isPending}
      />
      <FormField label="Note to Admin" hint="Optional. For example which subject you teach this section." error={note.length > 500 ? "Keep the note under 500 characters." : ""}>
        <Textarea rows={3} value={note} maxLength={520} onChange={(e) => setNote(e.target.value)} placeholder="I take Operating Systems for this section" />
      </FormField>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 max-w-[40ch] text-sm text-muted-foreground">Nothing opens until Admin approves. You will get a notification either way.</p>
        <SubmitButton loading={request.isPending} loadingText="Sending..." disabled={note.length > 500}>
          <Send aria-hidden="true" /> Send request
        </SubmitButton>
      </div>
    </form>
  );
}
