import { useId, useMemo } from "react";
import { cn } from "@/lib/utils";
import { LOADS, METHODS, TABLE_ROWS, fmtCi, fmtValue, unitOf } from "./model";

/**
 * Grouped horizontal bars: one group per load level, one bar per method, with the 95% CI as a whisker.
 * Plain HTML/CSS so it reflows to 360px and stays selectable text; the comparison table has the same numbers.
 */
export function MetricChart({ levels, metrics, metricKey, onMetricChange, load, onLoadChange }) {
  const uid = useId();
  const unit = unitOf(metrics, metricKey);
  const better = metrics?.[metricKey]?.better;
  const row = TABLE_ROWS.find((r) => r.key === metricKey);

  const available = useMemo(() => TABLE_ROWS.filter((r) => levels?.medium?.table?.fcfs?.[r.key]), [levels]);

  const max = useMemo(() => {
    let m = 0;
    for (const l of LOADS) {
      for (const meth of METHODS) {
        const c = levels?.[l.id]?.table?.[meth.id]?.[metricKey];
        if (c) m = Math.max(m, c.mean + (c.ci95 || 0));
      }
    }
    return m || 1;
  }, [levels, metricKey]);

  return (
    <figure className="m-0">
      <div role="group" aria-label="Choose a metric to chart" className="mb-4 flex flex-wrap gap-1.5">
        {available.map((r) => (
          <button
            key={r.key}
            type="button"
            aria-pressed={r.key === metricKey}
            onClick={() => onMetricChange(r.key)}
            className={cn(
              "min-h-9 rounded-full border px-3 text-sm font-semibold transition-colors pointer-coarse:min-h-11",
              r.key === metricKey ? "border-primary bg-primary text-primary-foreground" : "border-line-strong bg-card text-ink-2 hover:border-primary hover:text-primary",
            )}
          >
            {r.chart}
          </button>
        ))}
      </div>

      <figcaption id={`${uid}-cap`} className="mb-3">
        <span className="font-display text-lg font-bold">{row?.label}</span>
        <span className="ml-2 text-sm text-muted-foreground">
          {better === "lower" ? "Lower is better" : better === "higher" ? "Higher is better" : "No good or bad direction"}
          {" · "}bars show the mean, whiskers the 95% interval
        </span>
      </figcaption>

      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-hidden="true">
        {METHODS.map((m) => (
          <span key={m.id} className="inline-flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-[3px]" style={{ background: m.css }} />
            {m.label}
          </span>
        ))}
      </div>

      <div role="group" aria-labelledby={`${uid}-cap`} className="grid gap-2">
        {LOADS.map((l) => {
          const t = levels?.[l.id]?.table;
          if (!t) return null;
          const selected = l.id === load;
          return (
            <button
              key={l.id}
              type="button"
              onClick={() => onLoadChange(l.id)}
              aria-pressed={selected}
              aria-label={`${l.label}, ${levels[l.id].num_requests} requests per week. ${METHODS.map((m) => `${m.short} ${fmtValue(t[m.id]?.[metricKey]?.mean, unit)}`).join(", ")}. Select to show this load in the table`}
              className={cn(
                "grid gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors",
                selected ? "border-primary bg-primary-soft/50" : "border-transparent hover:border-line-strong hover:bg-surface-2",
              )}
            >
              <span className="flex flex-wrap items-baseline gap-x-2 text-sm font-semibold">
                {l.label}
                <span className="num text-xs font-normal text-muted-foreground">{levels[l.id].num_requests} requests per week</span>
                {selected ? <span className="text-xs font-semibold text-primary-ink">Shown in the table</span> : null}
              </span>
              {METHODS.map((m) => {
                const c = t[m.id]?.[metricKey];
                if (!c) return null;
                const w = (c.mean / max) * 100;
                const lo = Math.max(0, ((c.mean - (c.ci95 || 0)) / max) * 100);
                const hi = Math.min(100, ((c.mean + (c.ci95 || 0)) / max) * 100);
                return (
                  <span key={m.id} className="grid grid-cols-[5.25rem_minmax(0,1fr)_auto] items-center gap-2 sm:grid-cols-[6.5rem_minmax(0,1fr)_9.5rem]" title={`${m.label}: ${fmtValue(c.mean, unit)}${c.ci95 != null ? ` ± ${fmtCi(c.ci95, unit)}` : ""} (mean of ${c.n} seeds)`}>
                    <span className="truncate text-[0.8125rem] text-ink-2">{m.short}</span>
                    <span className="relative block h-4 border-l border-line-strong">
                      <span className="rs-bar absolute top-0.5 left-0 block h-3 rounded-r-[4px]" style={{ width: `${Math.max(w, 0.6)}%`, background: m.css }} />
                      {c.ci95 ? (
                        <span className="absolute top-1/2 block h-[2px] -translate-y-1/2 bg-ink/80" style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0)}%` }}>
                          <span className="absolute top-1/2 left-0 block h-2 w-[2px] -translate-y-1/2 bg-ink/80" />
                          <span className="absolute top-1/2 right-0 block h-2 w-[2px] -translate-y-1/2 bg-ink/80" />
                        </span>
                      ) : null}
                    </span>
                    <span className="num text-right text-[0.8125rem] font-semibold whitespace-nowrap">
                      {fmtValue(c.mean, unit)}
                      {c.ci95 != null ? <span className="font-normal text-muted-foreground max-sm:hidden"> &plusmn; {fmtCi(c.ci95, unit)}</span> : null}
                    </span>
                  </span>
                );
              })}
            </button>
          );
        })}
      </div>
    </figure>
  );
}
