import { useState } from "react";
import { Check, CheckCheck, Clock, FileText, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { SubmitButton } from "@/components/app/SubmitButton";
import { uploadUrl } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** One chat message. `pending` = optimistic message still being sent. */
export function MessageBubble({ message, otherName, pending = false, editing, onEdit, onCancelEdit, onSaveEdit, saving }) {
  const mine = message.is_mine;
  const att = message.attachment;
  return (
    <li className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "min-w-0 max-w-[min(34rem,86%)] rounded-2xl px-3.5 py-2.5 text-[0.9688rem] leading-snug shadow-xs",
          mine
            ? "rounded-br-md bg-primary text-primary-foreground"
            : "rounded-bl-md border border-line bg-card text-foreground",
          pending && "opacity-70",
        )}
      >
        <span className="sr-only">{mine ? "You" : otherName}: </span>
        {att ? <Attachment att={att} mine={mine} /> : null}
        {editing ? (
          <EditForm initial={message.message_text || ""} onCancel={onCancelEdit} onSave={onSaveEdit} saving={saving} />
        ) : message.message_text ? (
          <p className={cn("m-0 break-words whitespace-pre-wrap", att && "mt-2")}>{message.message_text}</p>
        ) : null}
        {!editing ? (
          <p className={cn("m-0 mt-1 flex flex-wrap items-center justify-end gap-x-2 gap-y-0.5 text-xs tabular-nums", mine ? "text-primary-foreground/80" : "text-muted-foreground")}>
            {message.is_edited ? <span>Edited</span> : null}
            {mine && message.can_edit && !pending ? (
              <button
                type="button"
                onClick={onEdit}
                className="inline-flex min-h-6 items-center gap-1 rounded-sm font-semibold underline underline-offset-2 outline-none hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-primary-foreground pointer-coarse:min-h-9"
              >
                <Pencil aria-hidden="true" className="size-3" /> Edit
              </button>
            ) : null}
            <time dateTime={message.created_at}>{pending ? "Sending" : formatTime(message.created_at)}</time>
            {mine ? (
              <span className="inline-flex items-center gap-1 font-semibold">
                {pending ? (
                  <Clock aria-hidden="true" className="size-3.5" />
                ) : message.is_seen ? (
                  <CheckCheck aria-hidden="true" className="size-3.5" />
                ) : (
                  <Check aria-hidden="true" className="size-3.5" />
                )}
                <span>{pending ? "" : message.is_seen ? "Seen" : "Sent"}</span>
              </span>
            ) : null}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function Attachment({ att, mine }) {
  const href = uploadUrl(att.url);
  if (att.is_image) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-lg">
        <img src={href} alt={`Attached image: ${att.name}`} loading="lazy" className="max-h-60 w-auto max-w-full rounded-lg bg-sunken object-cover" />
      </a>
    );
  }
  return (
    <a
      href={href}
      download={att.name}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "flex min-w-0 items-center gap-2.5 rounded-lg px-3 py-2 no-underline outline-none focus-visible:ring-2",
        mine
          ? "bg-white/15 text-primary-foreground hover:bg-white/25 focus-visible:ring-primary-foreground"
          : "bg-sunken text-foreground hover:bg-line focus-visible:ring-ring",
      )}
    >
      <FileText aria-hidden="true" className="size-5 shrink-0" />
      <span className="min-w-0">
        <span className="block truncate font-semibold">{att.name}</span>
        <span className="block text-xs uppercase opacity-80">{att.type} file - download</span>
      </span>
    </a>
  );
}

function EditForm({ initial, onSave, onCancel, saving }) {
  const [value, setValue] = useState(initial);
  const trimmed = value.trim();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (trimmed && trimmed !== initial.trim()) onSave(trimmed);
        else if (!saving) onCancel();
      }}
      className="grid min-w-[min(18rem,70vw)] gap-2"
    >
      <label className="sr-only" htmlFor="edit-message">Edit your message</label>
      <Textarea
        id="edit-message"
        autoFocus
        onFocus={(e) => e.target.setSelectionRange(e.target.value.length, e.target.value.length)}
        value={value}
        maxLength={4000}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape") onCancel(); }}
        className="min-h-16 border-transparent text-foreground"
      />
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
        <SubmitButton size="sm" variant="saffron" loading={saving} disabled={!trimmed}>Save</SubmitButton>
      </div>
    </form>
  );
}
