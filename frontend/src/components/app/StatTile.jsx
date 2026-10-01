import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/**
 * A single figure with a label (dashboards). Pass `to` to make the whole tile a link; `alert` tints it saffron
 * for things that need attention.
 *   <StatTile label="Pending requests" value={3} to="/faculty/meetings" alert />
 */
export function StatTile({ label, value, to, alert = false, className }) {
  const cls = cn(
    "block min-w-0 rounded-lg border bg-card px-[1.1rem] py-4 text-inherit no-underline",
    alert ? "border-warn-line bg-saffron-soft text-saffron-ink" : "border-line",
    to && "transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-primary motion-reduce:hover:translate-y-0",
    className,
  );
  const body = (
    <>
      <div className="font-display text-[clamp(1.4rem,1.1rem+1vw,1.9rem)] leading-[1.15] font-bold tracking-[-0.02em] break-words tabular-nums">{value}</div>
      <div className={cn("mt-0.5 text-sm", alert ? "text-saffron-ink" : "text-muted-foreground")}>{label}</div>
    </>
  );
  return to ? <Link to={to} className={cls}>{body}</Link> : <div className={cls}>{body}</div>;
}
