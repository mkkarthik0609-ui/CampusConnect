/**
 * Replacements for window.confirm / window.prompt.
 *
 * Promise style (recommended; <DialogsProvider> is mounted once in src/App.jsx):
 *
 *   const confirm = useConfirm();
 *   const prompt = usePrompt();
 *
 *   if (await confirm({ title: "Remove this class?", description: "Students in it keep their accounts.", confirmLabel: "Remove", destructive: true })) { ... }
 *
 *   const reason = await prompt({ title: "Cancel this meeting", label: "Reason", required: true, confirmLabel: "Cancel meeting" });
 *   if (reason === null) return;            // dismissed
 *
 * Controlled style: <ConfirmDialog open onOpenChange title ... onConfirm={async () => ...} /> and <PromptDialog ... onSubmit={async (text) => ...} />.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/FormField";
import { SubmitButton } from "@/components/app/SubmitButton";
import { errorMessage } from "@/lib/api";

// ------------------------------------------------------------------------------------------------
// Controlled components
// ------------------------------------------------------------------------------------------------
export function ConfirmDialog({
  open, onOpenChange, title, description, confirmLabel = "Confirm", cancelLabel = "Cancel", destructive = false, onConfirm, children,
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (open) { setBusy(false); setError(""); } }, [open]);

  async function handleConfirm(e) {
    e.preventDefault(); // we close it ourselves, after the work succeeds
    setBusy(true);
    setError("");
    try {
      await onConfirm?.();
      onOpenChange(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description ? <AlertDialogDescription>{description}</AlertDialogDescription> : null}
        </AlertDialogHeader>
        {children}
        {error ? <p role="alert" className="text-sm font-semibold text-danger-ink">{error}</p> : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{cancelLabel}</AlertDialogCancel>
          <SubmitButton type="button" variant={destructive ? "destructive" : "default"} loading={busy} onClick={handleConfirm}>
            {confirmLabel}
          </SubmitButton>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function PromptDialog({
  open, onOpenChange, title, description, label = "Reason", placeholder, required = false, multiline = true, maxLength = 500,
  initialValue = "", confirmLabel = "Submit", cancelLabel = "Cancel", destructive = false, onSubmit,
}) {
  const [value, setValue] = useState(initialValue);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (open) { setValue(initialValue); setBusy(false); setError(""); } }, [open, initialValue]);

  async function handleSubmit(e) {
    e.preventDefault();
    const text = value.trim();
    if (required && !text) {
      setError(`${label} is required.`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmit?.(text);
      onOpenChange(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const Control = multiline ? Textarea : Input;
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent>
        <form onSubmit={handleSubmit} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description ? <DialogDescription>{description}</DialogDescription> : <DialogDescription className="sr-only">{label}</DialogDescription>}
          </DialogHeader>
          <FormField label={label} required={required} error={error}>
            <Control
              autoFocus
              value={value}
              maxLength={maxLength}
              placeholder={placeholder}
              onChange={(e) => { setValue(e.target.value); if (error) setError(""); }}
            />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>{cancelLabel}</Button>
            <SubmitButton variant={destructive ? "destructive" : "default"} loading={busy}>{confirmLabel}</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------------------------------------
// Promise-based provider + hooks
// ------------------------------------------------------------------------------------------------
const DialogsContext = createContext(null);

export function DialogsProvider({ children }) {
  const [confirmState, setConfirmState] = useState(null); // { options, resolve }
  const [promptState, setPromptState] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const settled = useRef({ confirm: false, prompt: false });

  const confirm = useCallback((options = {}) => new Promise((resolve) => {
    settled.current.confirm = false;
    setConfirmState({ options, resolve });
    setConfirmOpen(true);
  }), []);

  const prompt = useCallback((options = {}) => new Promise((resolve) => {
    settled.current.prompt = false;
    setPromptState({ options, resolve });
    setPromptOpen(true);
  }), []);

  const value = useMemo(() => ({ confirm, prompt }), [confirm, prompt]);

  return (
    <DialogsContext.Provider value={value}>
      {children}
      <ConfirmDialog
        {...(confirmState?.options || {})}
        open={confirmOpen}
        onOpenChange={(open) => {
          setConfirmOpen(open);
          if (!open && !settled.current.confirm) { settled.current.confirm = true; confirmState?.resolve(false); }
        }}
        onConfirm={() => { settled.current.confirm = true; confirmState?.resolve(true); }}
      />
      <PromptDialog
        {...(promptState?.options || {})}
        open={promptOpen}
        onOpenChange={(open) => {
          setPromptOpen(open);
          if (!open && !settled.current.prompt) { settled.current.prompt = true; promptState?.resolve(null); }
        }}
        onSubmit={(text) => { settled.current.prompt = true; promptState?.resolve(text); }}
      />
    </DialogsContext.Provider>
  );
}

function useDialogs() {
  const ctx = useContext(DialogsContext);
  if (!ctx) throw new Error("useConfirm / usePrompt must be used inside <DialogsProvider>");
  return ctx;
}

/** `const ok = await confirm({ title, description, confirmLabel, destructive })` -> boolean */
export const useConfirm = () => useDialogs().confirm;
/** `const text = await prompt({ title, label, required })` -> string | null (null = dismissed) */
export const usePrompt = () => useDialogs().prompt;
