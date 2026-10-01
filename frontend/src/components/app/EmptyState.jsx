import { Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Something is empty: say what, and what to do next. Always give the person a next step when there is one.
 *   <EmptyState icon={Bell} title="No notifications yet" action={<Button>...</Button>}>Requests and replies show up here.</EmptyState>
 * `compact` drops the tile and padding for use inside a card row or table.
 */
export function EmptyState({ icon: Icon = Inbox, title, children, action, compact = false, className }) {
  if (compact) {
    return (
      <div className={cn("py-4 text-muted-foreground", className)}>
        {title ? <p className="font-semibold text-ink-2">{title}</p> : null}
        {children ? <div className="text-sm">{children}</div> : null}
        {action ? <div className="mt-3">{action}</div> : null}
      </div>
    );
  }
  return (
    <div className={cn("grid justify-items-center gap-1.5 px-4 py-[clamp(1.5rem,4vw,2.5rem)] text-center", className)}>
      <span className="mb-1.5 inline-flex size-[54px] items-center justify-center rounded-2xl bg-primary-soft text-primary-ink">
        <Icon aria-hidden="true" className="size-6" />
      </span>
      {title ? <h2 className="font-display text-lg font-[650] text-balance">{title}</h2> : null}
      {children ? <div className="grid max-w-[34rem] justify-items-center gap-3 text-muted-foreground">{children}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
