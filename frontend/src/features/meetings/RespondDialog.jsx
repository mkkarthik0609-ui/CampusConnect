import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/app/FormField";
import { SubmitButton } from "@/components/app/SubmitButton";
import { ApiError } from "@/lib/api";

/**
 * Faculty answer to a meeting request. Accepting needs a time in the faculty member's own words
 * ("Tomorrow after 3:30 PM"); there are no fixed slots. Declining only needs an optional note.
 * `onRespond({ decision, faculty_response, meeting_time_text })` returns a promise.
 */
export function RespondDialog({ meeting, open, onOpenChange, onRespond }) {
  const [time, setTime] = useState("");
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(null); // "accept" | "reject" | null

  useEffect(() => {
    if (open) { setTime(""); setNote(""); setErrors({}); setBusy(null); }
  }, [open, meeting?.id]);

  async function decide(decision) {
    if (decision === "accept" && !time.trim()) {
      setErrors({ meeting_time_text: "Tell the student when you can meet, for example \"Tomorrow after 3:30 PM\"." });
      return;
    }
    setBusy(decision);
    setErrors({});
    try {
      await onRespond({
        decision,
        faculty_response: note.trim() || undefined,
        meeting_time_text: decision === "accept" ? time.trim() : undefined,
      });
      onOpenChange(false);
    } catch (err) {
      setErrors(err instanceof ApiError && Object.keys(err.fields).length ? err.fields : { form: err.message });
    } finally {
      setBusy(null);
    }
  }

  const student = meeting?.student;
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent>
        <form onSubmit={(e) => { e.preventDefault(); decide("accept"); }} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Respond to {student?.full_name || "this request"}</DialogTitle>
            <DialogDescription>
              {meeting?.reason ? <>They asked: <span className="font-semibold text-foreground">{meeting.reason}</span>. </> : null}
              Accepting needs a time, in your own words.
            </DialogDescription>
          </DialogHeader>
          <FormField label="When can you meet?" required error={errors.meeting_time_text} hint="For example: Tomorrow after 3:30 PM, in my cabin.">
            <Input autoFocus value={time} maxLength={200} onChange={(e) => { setTime(e.target.value); if (errors.meeting_time_text) setErrors({}); }} placeholder="Tomorrow after 3:30 PM" />
          </FormField>
          <FormField label="Note to the student" hint="Optional. Shown with your answer." error={errors.faculty_response}>
            <Textarea value={note} maxLength={1000} rows={3} onChange={(e) => setNote(e.target.value)} />
          </FormField>
          {errors.form ? <p role="alert" className="text-sm font-semibold text-danger-ink">{errors.form}</p> : null}
          <DialogFooter className="max-sm:flex-col-reverse">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={!!busy}>Close</Button>
            <SubmitButton type="button" variant="outline" loading={busy === "reject"} disabled={!!busy} onClick={() => decide("reject")}>Decline</SubmitButton>
            <SubmitButton loading={busy === "accept"} disabled={!!busy}>Accept</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
