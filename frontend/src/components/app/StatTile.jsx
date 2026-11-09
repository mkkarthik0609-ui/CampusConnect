import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A single figure with a label (dashboards). Pass `to` to make the whole tile a link; `alert` tints it saffron
 * for things that need attention.
 *   <StatTile label="Pending requests" value={3} to="/faculty/meetings" alert />
 */
export function StatTile({ label, value, to, alert = false, className }) {
  const cls = cn(
    "group relative block min-w-0 rounded-xl border bg-card px-5 py-4 text-inherit no-underline",
    alert ? "border-warn-line bg-saffron-soft text-saffron-ink" : "border-line",
    to && "transition-[border-color,transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-md motion-reduce:hover:translate-y-0",
    className,
  );
  const body = (
    <>
      <div className={cn("micro", alert ? "text-saffron-ink" : "text-muted-foreground")}>{label}</div>
      <div className="mt-2 font-display text-[clamp(1.9rem,1.4rem+1.6vw,2.6rem)] leading-none font-light tracking-[-0.04em] break-words tabular-nums">{value}</div>
      {to ? <ArrowUpRight aria-hidden="true" className="absolute top-4 right-4 size-4 text-muted-foreground opacity-0 transition-[opacity,transform] duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100" /> : null}
    </>
  );
  return to ? <Link to={to} className={cls}>{body}</Link> : <div className={cls}>{body}</div>;
}
