import { AlertTriangle, CircleCheck, Info, OctagonAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const TONES = {
  info: { box: "border-info-line bg-info text-info-ink", icon: Info },
  success: { box: "border-ok-line bg-ok text-ok-ink", icon: CircleCheck },
  warning: { box: "border-warn-line bg-warn text-warn-ink", icon: AlertTriangle },
  danger: { box: "border-danger-line bg-danger text-danger-ink", icon: OctagonAlert },
};

/**
 * Inline message inside a page or form (toasts are for results of actions; Notice is for standing context).
 * `danger` and `warning` announce as alerts; the rest as status.
 *   <Notice tone="warning" title="Admin has not created any classes yet.">Please try again later.</Notice>
 */
export function Notice({ tone = "info", title, children, className, icon: IconOverride }) {
  const { box, icon: Icon } = TONES[tone] || TONES.info;
  const I = IconOverride || Icon;
  return (
    <div
      role={tone === "danger" || tone === "warning" ? "alert" : "status"}
      className={cn("flex items-start gap-3 rounded-lg border px-4 py-3 text-[0.9375rem]", box, className)}
    >
      <I aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
      <div className="min-w-0 [&_a]:font-semibold [&_a]:text-inherit">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className={title ? "mt-0.5" : undefined}>{children}</div> : null}
      </div>
    </div>
  );
}
