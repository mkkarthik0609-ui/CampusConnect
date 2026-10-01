import { CalendarClock, CheckCheck, MessageSquareReply, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ClassPath } from "@/components/app/ClassPath";
import { StatusPill } from "@/components/app/StatusPill";
import { UserAvatar } from "@/components/app/UserAvatar";
import { formatDateTime } from "@/lib/format";

const WHO = { STUDENT: "the student", FACULTY: "the faculty member" };

/** One meeting request, from either side. The actions it offers come straight from the API's can_* flags. */
export function MeetingCard({ meeting: m, role, onRespond, onCancel, onComplete }) {
  const faculty = role === "FACULTY";
  const person = m.counterpart || (faculty ? m.student : m.faculty);
  const code = m.counterpart_code;
  const hasActions = m.can_respond || m.can_complete || m.can_cancel;

  return (
    <article aria-label={`Meeting with ${m.counterpart_name}: ${m.reason}`} className="grid gap-3 border-t border-line px-[clamp(0.9rem,2.5vw,1.4rem)] py-4 first:border-t-0">
      <div className="flex items-start gap-3">
        <UserAvatar name={m.counterpart_name} src={person?.profile_picture_url} size="md" />
        <div className="min-w-0 flex-1">
          <p className="m-0 font-[650] leading-snug">
            {m.counterpart_name}
            {code ? <span className="ml-2 font-mono text-[0.8125rem] font-medium text-muted-foreground">{code}</span> : null}
          </p>
          {faculty && m.student?.class ? <ClassPath cls={m.student.class} className="mt-0.5 text-[0.75rem]" /> : null}
          {!faculty && m.faculty?.department ? <p className="m-0 mt-0.5 text-sm text-muted-foreground">{m.faculty.department}</p> : null}
        </div>
        <StatusPill status={m.status} />
      </div>

      <div className="grid gap-1.5 sm:pl-14">
        <p className="m-0 font-semibold">{m.reason}</p>
        {m.student_message ? <p className="m-0 whitespace-pre-wrap text-[0.9688rem] text-ink-2">{m.student_message}</p> : null}

        {m.meeting_time_text ? (
          <p className="m-0 mt-1 inline-flex w-fit max-w-full items-start gap-2 rounded-lg bg-saffron-soft px-3 py-1.5 text-[0.9375rem] font-semibold text-saffron-ink">
            <CalendarClock aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span className="min-w-0 break-words"><span className="sr-only">Meeting time: </span>{m.meeting_time_text}</span>
          </p>
        ) : null}

        {m.faculty_response ? (
          <p className="m-0 mt-1 flex items-start gap-2 text-[0.9688rem] text-ink-2">
            <MessageSquareReply aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 break-words"><span className="font-semibold">{faculty ? "Your note" : "Faculty note"}:</span> {m.faculty_response}</span>
          </p>
        ) : null}

        {m.status === "CANCELLED" ? (
          <p className="m-0 text-[0.9688rem] text-ink-2">
            <span className="font-semibold">Cancelled{m.cancelled_by ? ` by ${m.cancelled_by === (faculty ? "FACULTY" : "STUDENT") ? "you" : WHO[m.cancelled_by] || m.cancelled_by.toLowerCase()}` : ""}</span>
            {m.cancellation_reason ? `: ${m.cancellation_reason}` : "."}
          </p>
        ) : null}
        {m.status === "COMPLETED" && m.completed_by ? (
          <p className="m-0 text-sm text-muted-foreground">Marked completed by {m.completed_by === (faculty ? "FACULTY" : "STUDENT") ? "you" : WHO[m.completed_by]}, {formatDateTime(m.completed_at)}.</p>
        ) : null}

        <p className="m-0 text-[0.8125rem] text-muted-foreground tabular-nums">
          Requested <time dateTime={m.requested_at}>{formatDateTime(m.requested_at)}</time>
          {m.responded_at ? <> - answered <time dateTime={m.responded_at}>{formatDateTime(m.responded_at)}</time></> : null}
        </p>
      </div>

      {hasActions ? (
        <div className="flex flex-wrap gap-2 sm:pl-14">
          {m.can_respond ? (
            <Button size="sm" onClick={() => onRespond(m)}>
              <MessageSquareReply aria-hidden="true" /> Respond
            </Button>
          ) : null}
          {m.can_complete ? (
            <Button size="sm" variant={m.can_respond ? "outline" : "default"} onClick={() => onComplete(m)}>
              <CheckCheck aria-hidden="true" /> Mark completed
            </Button>
          ) : null}
          {m.can_cancel ? (
            <Button size="sm" variant="secondary" onClick={() => onCancel(m)}>
              <X aria-hidden="true" /> Cancel meeting
            </Button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
