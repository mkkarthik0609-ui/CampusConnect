/** Shared constants and formatters for the scheduling-research page. */

export const METHODS = [
  { id: "fcfs", short: "FCFS", label: "FCFS / manual", css: "var(--rs-fcfs)" },
  { id: "rule_based", short: "Rule-based", label: "Rule-based", css: "var(--rs-rule)" },
  { id: "intelligent", short: "Intelligent", label: "Intelligent (proposed)", css: "var(--rs-int)" },
];

export const LOADS = [
  { id: "low", label: "Low load" },
  { id: "medium", label: "Medium load" },
  { id: "high", label: "High load" },
];

/** Rows of the comparison table, in reading order. `hint` is shown under the metric name. */
export const TABLE_ROWS = [
  { key: "avg_wait_min", label: "Average waiting time", chart: "Average wait" },
  { key: "p90_wait_min", label: "Waiting time, slowest 10% (p90)", chart: "p90 wait" },
  { key: "served_meetings", label: "Meetings held per week", chart: "Meetings held" },
  { key: "success_rate", label: "Success rate (held / requested)", chart: "Success rate" },
  { key: "faculty_idle_min", label: "Faculty idle time per week", chart: "Idle time" },
  { key: "wasted_min", label: "Wasted booked minutes", chart: "Wasted minutes" },
  { key: "schedule_conflicts", label: "Schedule conflicts (class clashes)", chart: "Conflicts" },
  { key: "cancellations", label: "Cancellations (of booked)", chart: "Cancellations" },
  { key: "no_shows", label: "No-shows (of booked)", chart: "No-shows" },
  { key: "fairness_jain", label: "Fairness (Jain index)", chart: "Fairness" },
  { key: "urgent_success_rate", label: "Urgent requests held", chart: "Urgent held" },
];

const nf = (digits) => new Intl.NumberFormat(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
const NF0 = nf(0);
const NF1 = nf(1);
const NF3 = nf(3);

export function unitOf(metrics, key) {
  return metrics?.[key]?.unit || "count";
}

/** Mean as text: "275 min", "65.0%", "234", "0.762". */
export function fmtValue(v, unit) {
  if (v == null || Number.isNaN(v)) return "n/a";
  if (unit === "fraction") return `${NF1.format(v * 100)}%`;
  if (unit === "index") return NF3.format(v);
  if (unit === "min") return `${Math.abs(v) >= 10 ? NF0.format(v) : NF1.format(v)} min`;
  return Math.abs(v) >= 10 ? NF0.format(v) : NF1.format(v);
}

/** 95% CI half-width as text ("9", "1.0 pts", "0.009"). */
export function fmtCi(ci, unit) {
  if (ci == null) return "";
  if (unit === "fraction") return `${NF1.format(ci * 100)} pts`;
  if (unit === "index") return NF3.format(ci);
  return Math.abs(ci) >= 10 ? NF0.format(ci) : NF1.format(ci);
}

export function fmtPct(v) {
  return `${NF1.format(Math.abs(v))}%`;
}

/** Index of the best method for a metric given its direction, or -1 when there is no direction. */
export function bestMethod(rowCells, better) {
  if (!better) return -1;
  let best = -1;
  let bestVal = null;
  rowCells.forEach((c, i) => {
    if (c?.mean == null) return;
    if (bestVal == null || (better === "lower" ? c.mean < bestVal : c.mean > bestVal)) {
      best = i;
      bestVal = c.mean;
    }
  });
  // ties (e.g. 0 conflicts for two methods) are not highlighted
  const ties = rowCells.filter((c) => c?.mean === bestVal).length;
  return ties > 1 ? -1 : best;
}

/** Minutes from Monday 09:00 -> "Mon 14:30". */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
export const DAY_NAMES = DAYS;
export function clock(minOfDay, startHour = 9) {
  const t = startHour * 60 + minOfDay;
  const h = Math.floor(t / 60);
  const m = t % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
