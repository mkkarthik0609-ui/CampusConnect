import { memo, useRef, useState } from "react";
import { Ban, Check, CheckCheck, ChevronDown, Clock, Copy, CornerUpLeft, FileText, Pencil, Trash2, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { uploadUrl } from "@/lib/api";
import { clock } from "./time";

const SWIPE_TRIGGER = 56;
const LONG_PRESS_MS = 480;

/** Delivery ticks: clock (sending), one grey tick (sent), two grey (delivered), two blue (seen). */
export function Tick({ status }) {
  const label = { pending: "Sending", sent: "Sent", delivered: "Delivered", seen: "Seen" }[status] || "Sent";
  const Icon = status === "pending" ? Clock : status === "sent" ? Check : CheckCheck;
  return (
    <span className="wa-tick" data-status={status}>
      <Icon aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

function Quote({ quote, otherName, onJump }) {
  const who = quote.is_mine ? "You" : quote.sender_name || otherName;
  let text = quote.text_preview;
  if (quote.unsent) text = "This message was unsent";
  else if (!text && quote.attachment_kind) text = quote.attachment_kind === "image" ? "Photo" : quote.attachment_name || "File";
  return (
    <button type="button" className="wa-quote" onClick={() => onJump(quote.id)} aria-label={`Go to the message from ${who}: ${text}`}>
      <span className="wa-quote-name">{who}</span>
      <span className="wa-quote-text" data-unsent={quote.unsent || undefined}>{text}</span>
    </button>
  );
}

function Attachment({ att }) {
  if (!att.url) {
    return (
      <span className="wa-file"><FileText aria-hidden="true" /><span><b>{att.name}</b><small>Sending...</small></span></span>
    );
  }
  const href = uploadUrl(att.url);
  if (att.is_image) {
    return (
      <a className="wa-media" href={href} target="_blank" rel="noopener noreferrer">
        <img src={href} alt={`Attached image: ${att.name}`} loading="lazy" />
      </a>
    );
  }
  return (
    <a className="wa-file" href={href} download={att.name} target="_blank" rel="noopener noreferrer">
      <FileText aria-hidden="true" />
      <span><b>{att.name}</b><small>{att.type} file - download</small></span>
    </a>
  );
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Copied.");
  } catch {
    toast.error("Could not copy that message.");
  }
}

/**
 * One message bubble (WhatsApp Web). Desktop: hover chevron / right-click opens the menu. Touch: long-press opens it,
 * swipe right replies. `pending` = optimistic message that is still being sent.
 */
export const MessageBubble = memo(function MessageBubble({ m, first, flash, otherName, pending, onReply, onEdit, onUnsend, onHide, onJump }) {
  const [open, setOpen] = useState(false);
  const [drag, setDrag] = useState(0);
  const touch = useRef(null);
  const timer = useRef(null);

  const mine = m.is_mine;
  const sender = mine ? "You" : m.sender_name || otherName;
  const canAct = !pending;
  const canReply = canAct && !m.is_unsent;

  const stop = () => { clearTimeout(timer.current); timer.current = null; };
  function onTouchStart(e) {
    if (!canAct) return;
    const t = e.touches[0];
    touch.current = { x: t.clientX, y: t.clientY, moved: false };
    timer.current = setTimeout(() => { if (touch.current && !touch.current.moved) { navigator.vibrate?.(15); setOpen(true); } }, LONG_PRESS_MS);
  }
  function onTouchMove(e) {
    const s = touch.current;
    if (!s) return;
    const dx = e.touches[0].clientX - s.x;
    const dy = e.touches[0].clientY - s.y;
    if (Math.abs(dy) > 10 || dx < -10) { s.moved = true; stop(); setDrag(0); return; }
    if (dx > 8 && canReply) { s.moved = true; stop(); setDrag(Math.min(dx, 80)); }
  }
  function onTouchEnd() {
    stop();
    if (drag >= SWIPE_TRIGGER) { navigator.vibrate?.(10); onReply(m); }
    touch.current = null;
    setDrag(0);
  }

  return (
    <li
      id={`wa-msg-${m.id}`}
      className="wa-row"
      data-mid={m.id}
      data-mine={mine}
      data-first={first}
      data-flash={flash || undefined}
      data-drag={drag > 0}
    >
      <div
        className="wa-bubble wa-bubble-in"
        data-mine={mine}
        data-tail={first}
        style={drag ? { transform: `translateX(${drag}px)` } : undefined}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchEnd}
        onContextMenu={(e) => { if (canAct) { e.preventDefault(); setOpen(true); } }}
      >
        <span className="sr-only">{sender}: </span>

        {m.is_unsent ? (
          <p className="wa-tombstone">
            <Ban aria-hidden="true" />
            {mine ? "You unsent a message" : `${sender} unsent a message`}
            <Meta m={m} pending={pending} bare />
          </p>
        ) : (
          <>
            {m.reply_to ? <Quote quote={m.reply_to} otherName={otherName} onJump={onJump} /> : null}
            {m.attachment ? <Attachment att={m.attachment} /> : null}
            <p className="wa-text">
              {m.message_text}
              <Meta m={m} pending={pending} />
            </p>
          </>
        )}

        {canAct ? (
          <DropdownMenu open={open} onOpenChange={setOpen}>
            <DropdownMenuTrigger asChild>
              <button type="button" className="wa-chevron" aria-label="Message options"><ChevronDown aria-hidden="true" /></button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align={mine ? "end" : "start"} className="min-w-44">
              {canReply ? <DropdownMenuItem onSelect={() => onReply(m)}><CornerUpLeft aria-hidden="true" /> Reply</DropdownMenuItem> : null}
              {m.message_text ? <DropdownMenuItem onSelect={() => copyText(m.message_text)}><Copy aria-hidden="true" /> Copy</DropdownMenuItem> : null}
              {m.can_edit ? <DropdownMenuItem onSelect={() => onEdit(m)}><Pencil aria-hidden="true" /> Edit</DropdownMenuItem> : null}
              {(canReply || m.message_text || m.can_edit) ? <DropdownMenuSeparator /> : null}
              {m.can_unsend ? <DropdownMenuItem className="wa-menu-danger" onSelect={() => onUnsend(m)}><Undo2 aria-hidden="true" /> Unsend</DropdownMenuItem> : null}
              <DropdownMenuItem className="wa-menu-danger" onSelect={() => onHide(m)}><Trash2 aria-hidden="true" /> Delete for me</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </li>
  );
});

function Meta({ m, pending, bare }) {
  return (
    <span className="wa-meta" style={bare ? { marginLeft: "0.6rem" } : undefined}>
      {m.is_edited && !bare ? <span>Edited</span> : null}
      {pending ? null : <time dateTime={m.created_at}>{clock(m.created_at)}</time>}
      {m.is_mine ? <Tick status={pending ? "pending" : m.status} /> : null}
    </span>
  );
}
