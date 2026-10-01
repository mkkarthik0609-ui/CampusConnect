import { useMemo } from "react";
import { Check, Minus, X } from "lucide-react";
import { DataTable } from "@/components/app/DataTable";
import { cn } from "@/lib/utils";
import { METHODS, TABLE_ROWS, bestMethod, fmtCi, fmtPct, fmtValue, unitOf } from "./model";

function Delta({ imp }) {
  if (!imp) return <span className="text-muted-foreground">n/a</span>;
  const { verdict, pct_improvement: pct } = imp;
  if (verdict === "informational") {
    return <span className="text-sm text-muted-foreground">No good or bad direction</span>;
  }
  if (pct == null) return <span className="text-sm text-muted-foreground">n/a (baseline is 0)</span>;
  const tone = verdict === "better" ? "text-ok-ink" : verdict === "worse" ? "text-danger-ink" : "text-muted-foreground";
  const Icon = verdict === "better" ? Check : verdict === "worse" ? X : Minus;
  const word = verdict === "better" ? (pct >= 99.95 ? "eliminated" : `${fmtPct(pct)} better`) : verdict === "worse" ? `${fmtPct(pct)} worse` : "No clear difference";
  return (
    <span className={cn("inline-flex flex-col items-start gap-0.5 max-sm:items-end", tone)}>
      <span className="inline-flex items-center gap-1 font-semibold">
        <Icon aria-hidden="true" className="size-4 shrink-0" />
        {word}
      </span>
      <span className="text-xs font-normal text-muted-foreground">
        {verdict === "no_clear_difference" ? `${pct >= 0 ? "+" : "-"}${fmtPct(pct)}, within noise` : "outside the 95% interval"}
      </span>
    </span>
  );
}

/**
 * Mean +/- 95% CI for every method, and the % improvement of the intelligent method against FCFS and rule-based.
 * `table[method][metric] = {mean, ci95, n}`; `improvement.intelligent_vs_fcfs[metric] = {pct_improvement, verdict}`.
 */
export function ComparisonTable({ table, improvement, metrics, caption }) {
  const rows = useMemo(() => TABLE_ROWS.filter((r) => table?.fcfs?.[r.key]), [table]);

  return (
    <DataTable
      caption={caption}
      rows={rows}
      rowKey={(r) => r.key}
      empty={{ title: "No results" }}
      columns={[
        {
          key: "metric", header: "Metric", primary: true,
          cell: (r) => (
            <div className="text-left max-sm:text-left">
              <div className="font-semibold">{r.label}</div>
              <div className="text-xs font-normal text-muted-foreground">
                {metrics?.[r.key]?.better === "lower" ? "Lower is better" : metrics?.[r.key]?.better === "higher" ? "Higher is better" : "No direction"}
                {unitOf(metrics, r.key) === "min" ? ", minutes" : ""}
              </div>
            </div>
          ),
        },
        ...METHODS.map((m, mi) => ({
          key: m.id,
          header: m.short,
          className: "num",
          cell: (r) => {
            const cells = METHODS.map((x) => table[x.id]?.[r.key]);
            const cell = cells[mi];
            const unit = unitOf(metrics, r.key);
            const best = bestMethod(cells, metrics?.[r.key]?.better) === mi;
            if (!cell) return <span className="text-muted-foreground">n/a</span>;
            return (
              <span className={cn("inline-flex items-baseline gap-1", best && "font-bold")}>
                <span className="inline-block size-2 shrink-0 rounded-[2px]" style={{ background: m.css }} aria-hidden="true" />
                <span>{fmtValue(cell.mean, unit)}</span>
                {cell.ci95 != null ? <span className="text-xs font-normal text-muted-foreground">&plusmn; {fmtCi(cell.ci95, unit)}</span> : null}
                {best ? <span className="sr-only"> (best)</span> : null}
              </span>
            );
          },
        })),
        { key: "vs_fcfs", header: "Intelligent vs FCFS", cell: (r) => <Delta imp={improvement?.intelligent_vs_fcfs?.[r.key]} /> },
        { key: "vs_rule", header: "Intelligent vs rule-based", cell: (r) => <Delta imp={improvement?.intelligent_vs_rule_based?.[r.key]} /> },
      ]}
    />
  );
}
