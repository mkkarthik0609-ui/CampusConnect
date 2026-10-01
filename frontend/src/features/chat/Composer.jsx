import { useRef, useState } from "react";
import { Paperclip, SendHorizontal, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { SubmitButton } from "@/components/app/SubmitButton";

export const ATTACH_ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx";
const ALLOWED = ["pdf", "png", "jpg", "jpeg", "docx"];
const MAX_BYTES = 8 * 1024 * 1024;

function prettySize(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Message box: Enter sends, Shift+Enter adds a line, the paperclip attaches one file (PDF / PNG / JPG / DOCX, up to 8 MB).
 * `onSend({ text, file })` must return a promise that rejects when the send failed (the text is then put back).
 * Text-only sends clear the box immediately (the parent shows the message optimistically); file sends wait.
 */
export function Composer({ onSend, disabled, placeholder = "Write a message" }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const areaRef = useRef(null);
  const fileRef = useRef(null);

  function resize() {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }

  function pickFile(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const ext = f.name.split(".").pop().toLowerCase();
    if (!ALLOWED.includes(ext)) return toast.error("That file type is not supported. Attach a PDF, PNG, JPG or DOCX.");
    if (f.size > MAX_BYTES) return toast.error(`That file is ${prettySize(f.size)}. The limit is 8 MB.`);
    if (f.size === 0) return toast.error("That file is empty.");
    setFile(f);
  }

  async function submit(e) {
    e?.preventDefault();
    const body = text.trim();
    if ((!body && !file) || busy || disabled) return;
    if (file) {
      setBusy(true);
      try {
        await onSend({ text: body, file });
        setFile(null);
        setText("");
        requestAnimationFrame(resize);
      } catch {
        /* the parent already showed the error; keep the draft */
      } finally {
        setBusy(false);
      }
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
    }
  }

  return (
    <form onSubmit={submit} className="border-t border-line bg-card p-3">
      {file ? (
        <div className="mb-2 flex items-center gap-2 rounded-lg bg-sunken px-3 py-1.5 text-sm" aria-live="polite">
          <Paperclip aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate font-semibold">{file.name}</span>
          <span className="shrink-0 text-muted-foreground tabular-nums">{prettySize(file.size)}</span>
          <Button type="button" variant="ghost" size="icon-xs" aria-label={`Remove attachment ${file.name}`} onClick={() => setFile(null)} disabled={busy}>
            <X aria-hidden="true" />
          </Button>
        </div>
      ) : null}
      <div className="flex items-end gap-2">
        <input ref={fileRef} type="file" accept={ATTACH_ACCEPT} className="sr-only" tabIndex={-1} aria-hidden="true" onChange={pickFile} />
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Attach a file (PDF, image or DOCX, up to 8 MB)"
          onClick={() => fileRef.current?.click()}
          disabled={disabled || busy}
        >
          <Paperclip aria-hidden="true" />
        </Button>
        <label htmlFor="chat-message" className="sr-only">Message</label>
        <textarea
          id="chat-message"
          ref={areaRef}
          rows={1}
          value={text}
          maxLength={4000}
          disabled={disabled || busy}
          placeholder={file ? "Add a caption (optional)" : placeholder}
          onChange={(e) => { setText(e.target.value); resize(); }}
          onKeyDown={onKeyDown}
          className="max-h-[168px] min-h-11 min-w-0 flex-1 resize-none rounded-md border border-input bg-surface px-3 py-[0.6rem] text-base leading-snug text-foreground shadow-xs outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-muted-foreground hover:border-muted-foreground focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-ring/35 disabled:bg-sunken"
        />
        <SubmitButton size="icon" loading={busy} disabled={disabled || (!text.trim() && !file)} aria-label="Send message">
          <SendHorizontal aria-hidden="true" />
        </SubmitButton>
      </div>
      <p className="m-0 mt-1.5 hidden text-xs text-muted-foreground min-[40rem]:block">Enter to send, Shift+Enter for a new line.</p>
    </form>
  );
}
