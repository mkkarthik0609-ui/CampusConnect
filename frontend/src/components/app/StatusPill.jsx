import { cn } from "@/lib/utils";

const TONES = {
  warn: "border-warn-line bg-warn text-warn-ink",
  ok: "border-ok-line bg-ok text-ok-ink",
  danger: "border-danger-line bg-danger text-danger-ink",
  info: "border-info-line bg-info text-info-ink",
  neutral: "border-line bg-neutral text-neutral-ink",
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
        "inline-flex items-center gap-1.5 rounded-full border py-[0.15rem] pr-2.5 pl-2 text-[0.6875rem] leading-[1.3] font-medium tracking-[0.08em] whitespace-nowrap uppercase",
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
