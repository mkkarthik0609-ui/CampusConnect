import { useEffect, useRef, useState } from "react";
import { FileText, Paperclip, Pencil, SendHorizontal, Smile, X } from "lucide-react";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export const ATTACH_ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx";
const ALLOWED = ["pdf", "png", "jpg", "jpeg", "docx"];
const MAX_BYTES = 8 * 1024 * 1024;
const MAX_TEXT = 4000;

const EMOJI = [
  "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "🙂", "😉", "😍", "🥰", "😘", "😋", "😎",
  "🤔", "😐", "😴", "😢", "😭", "😡", "🤯", "😱", "🙏", "👍", "👎", "👏", "🙌", "💪", "👋", "🤝",
  "✅", "❌", "⭐", "🔥", "🎉", "💯", "❤️", "💔", "📚", "📝", "📎", "📅", "⏰", "💡", "🎓", "☕",
];

function prettySize(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

const quoteLabel = (m) => (m.is_mine ? "You" : m.sender_name || "Them");
const quoteText = (m) => m.message_text || (m.attachment ? `Attachment: ${m.attachment.name || "file"}` : "");

/**
 * WhatsApp-style message bar. Enter sends, Shift+Enter adds a line; the box grows with the text. Handles four modes:
 * plain send, reply (`replyTo` bar), edit (`editing` bar - Enter saves, Esc cancels) and attachment (preview chip).
 * `onSend({ text, file })` / `onSave(text)` must return a promise that rejects when it failed (the draft is kept).
 */
export function Composer({ onSend, onSave, onTyping, canAttach = true, replyTo, onCancelReply, editing, onCancelEdit, placeholder = "Type a message", disabled }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const areaRef = useRef(null);
  const fileRef = useRef(null);

  function resize() {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`;
  }

  // Entering edit mode puts the message in the box; leaving it restores an empty box.
  const editingId = editing?.id;
  const editingText = editing?.message_text;
  useEffect(() => {
    if (editingId === undefined) return;
    setText(editingText || "");
    setFile(null);
    requestAnimationFrame(() => { resize(); areaRef.current?.focus(); });
  }, [editingId, editingText]);
  useEffect(() => { if (replyTo) areaRef.current?.focus(); }, [replyTo]);

  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) { setPreview(null); return undefined; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function pickFile(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const ext = f.name.split(".").pop().toLowerCase();
    if (!ALLOWED.includes(ext)) return toast.error("That file type is not supported. Attach a PDF, PNG, JPG or DOCX.");
    if (f.size > MAX_BYTES) return toast.error(`That file is ${prettySize(f.size)}. The limit is 8 MB.`);
    if (f.size === 0) return toast.error("That file is empty.");
    setFile(f);
    areaRef.current?.focus();
  }

  function insertEmoji(emoji) {
    const el = areaRef.current;
    const start = el?.selectionStart ?? text.length;
    const end = el?.selectionEnd ?? text.length;
    const next = text.slice(0, start) + emoji + text.slice(end);
    if (next.length > MAX_TEXT) return;
    setText(next);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(start + emoji.length, start + emoji.length); resize(); });
    onTyping?.();
  }

  async function submit(e) {
    e?.preventDefault();
    const body = text.trim();
    if (busy || disabled) return;
    if (editing) {
      if (!body) return;
      if (body === (editing.message_text || "").trim()) return onCancelEdit?.();
      setBusy(true);
      try {
        await onSave(body);
        setText("");
        onCancelEdit?.();
      } catch { /* the caller already showed the error; keep the draft */ } finally { setBusy(false); }
      return;
    }
    if (!body && !file) return;
    if (file) {
      setBusy(true);
      try {
        await onSend({ text: body, file });
        setFile(null);
        setText("");
        requestAnimationFrame(resize);
      } catch { /* keep the draft */ } finally { setBusy(false); }
      return;
    }
    setText("");
    requestAnimationFrame(resize);
    try {
      await onSend({ text: body });
    } catch {
      setText((cur) => cur || body);
      requestAnimationFrame(resize);
    }
    areaRef.current?.focus();
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape") {
      if (editing) { setText(""); onCancelEdit?.(); } else if (replyTo) onCancelReply?.();
    }
  }

  const canSend = (editing ? !!text.trim() : !!text.trim() || !!file) && !busy && !disabled;

  return (
    <form onSubmit={submit} className="wa-composer" aria-label="Write a message">
      <div className="wa-composer-bar">
        <Popover open={emojiOpen} onOpenChange={setEmojiOpen}>
          <PopoverTrigger asChild>
            <button type="button" className="wa-icon-btn" aria-label="Emoji" disabled={disabled || busy}><Smile aria-hidden="true" /></button>
          </PopoverTrigger>
          <PopoverContent side="top" align="start" className="w-[19rem] p-2" aria-label="Emoji picker">
            <div className="wa-emoji">
              {EMOJI.map((e) => (
                <button key={e} type="button" onClick={() => insertEmoji(e)} aria-label={`Insert ${e}`}>{e}</button>
              ))}
            </div>
          </PopoverContent>
        </Popover>
        {canAttach && !editing ? (
          <>
            <input ref={fileRef} type="file" accept={ATTACH_ACCEPT} className="sr-only" tabIndex={-1} aria-hidden="true" onChange={pickFile} />
            <button
              type="button"
              className="wa-icon-btn"
              aria-label="Attach a file (PDF, image or DOCX, up to 8 MB)"
              onClick={() => fileRef.current?.click()}
              disabled={disabled || busy}
            >
              <Paperclip aria-hidden="true" />
            </button>
          </>
        ) : null}

        <div className="wa-field">
          {editing ? (
            <div className="wa-context" role="status">
              <Pencil aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[var(--wa-quote-name)]" />
              <div><b>Edit message</b><span>{editing.message_text}</span></div>
              <button type="button" className="wa-icon-btn" aria-label="Cancel editing" onClick={() => { setText(""); onCancelEdit?.(); }}><X aria-hidden="true" /></button>
            </div>
          ) : replyTo ? (
            <div className="wa-context">
              <div><b>{quoteLabel(replyTo)}</b><span>{quoteText(replyTo)}</span></div>
              <button type="button" className="wa-icon-btn" aria-label="Cancel reply" onClick={onCancelReply}><X aria-hidden="true" /></button>
            </div>
          ) : null}
          {file ? (
            <div className="wa-attach-chip" aria-live="polite">
              {preview ? <img src={preview} alt="" /> : <FileText aria-hidden="true" className="wa-file-ico" />}
              <div><b>{file.name}</b><small>{prettySize(file.size)}</small></div>
              <button type="button" className="wa-icon-btn" aria-label={`Remove attachment ${file.name}`} onClick={() => setFile(null)} disabled={busy}><X aria-hidden="true" /></button>
            </div>
          ) : null}
          <label htmlFor="wa-message" className="sr-only">Message</label>
          <textarea
            id="wa-message"
            ref={areaRef}
            rows={1}
            value={text}
            maxLength={MAX_TEXT}
            disabled={disabled}
            placeholder={file ? "Add a caption" : placeholder}
            onChange={(e) => { setText(e.target.value); resize(); if (e.target.value && !editing) onTyping?.(); }}
            onKeyDown={onKeyDown}
          />
        </div>

        <button type="submit" className="wa-send" disabled={!canSend} aria-label={editing ? "Save edited message" : "Send message"}>
          <SendHorizontal aria-hidden="true" />
        </button>
      </div>
      <p className="wa-hint">Enter to send, Shift+Enter for a new line.</p>
    </form>
  );
}
