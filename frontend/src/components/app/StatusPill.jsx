import { cn } from "@/lib/utils";

const TONES = {
  warn: "bg-warn text-warn-ink",
  ok: "bg-ok text-ok-ink",
  danger: "bg-danger text-danger-ink",
  info: "bg-info text-info-ink",
  neutral: "bg-neutral text-neutral-ink",
};

const STATUS_TONE = {
  PENDING: "warn",
  ACCEPTED: "ok",
  APPROVED: "ok",
  ACTIVE: "ok",
  REJECTED: "danger",
  COMPLETED: "info",
  CANCELLED: "neutral",
  INACTIVE: "neutral",
};

/**
 * Workflow state pill. Colour is never the only signal: the label is always present.
 *   <StatusPill status="PENDING" />   <StatusPill status="ACTIVE" label="Live" tone="ok" />
 */
export function StatusPill({ status, label, tone, className }) {
  const key = String(status || "").toUpperCase();
  const resolved = tone || STATUS_TONE[key] || "neutral";
  const hollow = key === "CANCELLED" || key === "INACTIVE";
  return (
    <span
      data-status={key}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full py-[0.18rem] pr-2.5 pl-2 text-xs leading-[1.3] font-bold tracking-[0.04em] whitespace-nowrap uppercase",
        TONES[resolved],
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn("size-[0.45rem] shrink-0 rounded-full", hollow ? "bg-transparent shadow-[inset_0_0_0_1.5px_currentColor]" : "bg-current")}
      />
      {label ?? key.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}
    </span>
  );
}
