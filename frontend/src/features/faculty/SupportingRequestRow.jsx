import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SubmitButton } from "@/components/app/SubmitButton";
import { ClassPath } from "@/components/app/ClassPath";
import { useConfirm } from "@/components/app/dialogs";
import { timeAgo } from "@/lib/format";
import { PersonCell, Row } from "@/features/faculty/ui";
import { useRespondSupporting } from "@/features/faculty/hooks";

/** A student asking me to be their supporting faculty. Accept opens chat + meetings with them. */
export function SupportingRequestRow({ request }) {
  const respond = useRespondSupporting();
  const confirm = useConfirm();
  const { student } = request;
  const pendingDecision = respond.isPending ? respond.variables?.decision : null;

  async function reject() {
    const ok = await confirm({
      title: `Decline ${student.full_name}?`,
      description: "They are told you declined. They can ask again later.",
      confirmLabel: "Decline request",
      destructive: true,
    });
    if (ok) respond.mutate({ id: request.id, decision: "reject" });
  }

  return (
    <Row>
      <div className="grid min-w-0 flex-1 basis-60 gap-1.5">
        <PersonCell name={student.full_name} src={student.profile_picture_url} code={student.usn} />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pl-12 text-sm text-muted-foreground">
          {student.class ? <ClassPath cls={student.class} /> : null}
          <span>asked {timeAgo(request.created_at)}</span>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" disabled={respond.isPending} onClick={reject} aria-label={`Decline ${student.full_name}`}>
          <X aria-hidden="true" /> Decline
        </Button>
        <SubmitButton
          type="button"
          size="sm"
          loading={pendingDecision === "accept"}
          disabled={respond.isPending}
          onClick={() => respond.mutate({ id: request.id, decision: "accept" })}
          aria-label={`Accept ${student.full_name}`}
        >
          {pendingDecision === "accept" ? null : <Check aria-hidden="true" />} Accept
        </SubmitButton>
      </div>
    </Row>
  );
}
