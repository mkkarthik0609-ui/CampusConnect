import { CircleAlert, CircleCheck } from "lucide-react";
import { SectionHeading } from "@/components/app/PageHeader";
import { fmtPct, fmtValue } from "./model";

/** "What this shows / what it does not": text follows research/README.md; the numbers come from the study. */
export function Findings({ data }) {
  const med = data?.levels?.medium;
  const high = data?.levels?.high;
  const vf = med?.improvement?.intelligent_vs_fcfs;
  const vr = med?.improvement?.intelligent_vs_rule_based;
  const rb = med?.improvement?.rule_based_vs_fcfs;
  const sens = data?.sensitivity?.variants;
  const flex = sens ? Object.entries(sens).find(([k]) => k.includes("flexible_5min_slots") && !k.includes("both")) : null;

  const worseWait = vr?.avg_wait_min;
  const worseP90 = vr?.p90_wait_min;

  return (
    <section aria-label="What this shows and what it does not" className="mb-4">
      <SectionHeading title="What this shows, and what it does not" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-ok-line bg-card p-5">
          <h3 className="m-0 mb-3 flex items-center gap-2 text-base font-bold text-ok-ink">
            <CircleCheck aria-hidden="true" className="size-5" />What the data supports
          </h3>
          <ul className="m-0 grid gap-2.5 pl-5 text-[0.9375rem]">
            {vf?.served_meetings ? (
              <li>
                Timetable-aware scheduling with flexible meeting lengths holds about {fmtPct(vf.served_meetings.pct_improvement)} more meetings, ends class clashes and cuts
                average waiting by {fmtPct(vf.avg_wait_min?.pct_improvement ?? 0)} compared with the manual baseline (medium load).
              </li>
            ) : null}
            {high?.improvement?.intelligent_vs_fcfs?.served_meetings ? (
              <li>The gain grows with demand: at high load {fmtPct(high.improvement.intelligent_vs_fcfs.served_meetings.pct_improvement)} more meetings and {fmtPct(high.improvement.intelligent_vs_fcfs.faculty_idle_min?.pct_improvement ?? 0)} less idle faculty time.</li>
            ) : null}
            {vr ? (
              <li>
                The scoring layer adds a modest extra: about {fmtPct(vr.served_meetings?.pct_improvement ?? 0)} more meetings than rule-based,{" "}
                {fmtPct(vr.wasted_min?.pct_improvement ?? 0)} fewer wasted booked minutes, slightly better fairness and clearly better handling of urgent requests
                ({fmtValue(med.table.intelligent.urgent_success_rate?.mean, "fraction")} held vs {fmtValue(med.table.rule_based.urgent_success_rate?.mean, "fraction")}).
              </li>
            ) : null}
          </ul>
        </div>

        <div className="rounded-lg border border-warn-line bg-card p-5">
          <h3 className="m-0 mb-3 flex items-center gap-2 text-base font-bold text-warn-ink">
            <CircleAlert aria-hidden="true" className="size-5" />Honest limits
          </h3>
          <ul className="m-0 grid gap-2.5 pl-5 text-[0.9375rem]">
            {worseWait ? (
              <li>
                <strong>The weakest metric is waiting time.</strong> Intelligent is {fmtPct(worseWait.pct_improvement)} {worseWait.pct_improvement < 0 ? "worse" : "better"} than rule-based on average wait
                {worseP90 ? ` (and ${fmtPct(worseP90.pct_improvement)} ${worseP90.pct_improvement < 0 ? "worse" : "better"} at p90)` : ""}. It refills freed slots for students who have waited long and sometimes moves a normal booking for an urgent one, which adds waiting among those served.
              </li>
            ) : null}
            <li>
              <strong>Most of the gain is not &ldquo;intelligence&rdquo;.</strong> Rule-based already captures {rb?.served_meetings ? `${fmtPct(rb.served_meetings.pct_improvement)} more meetings` : "nearly all of it"}; it comes from respecting the class timetable and using flexible slots.
            </li>
            {flex ? (
              <li>
                The baseline is a modelling choice. If manual booking used flexible 5 minute slots, plain FCFS would have the lowest average wait ({fmtValue(flex[1].avg_wait_min?.mean, "min")}) and {fmtValue(flex[1].success_rate?.mean, "fraction")} success, though still with about {Math.round(flex[1].schedule_conflicts?.mean || 0)} class clashes a week.
              </li>
            ) : null}
            <li><strong>The data are synthetic.</strong> Every distribution is an assumption, not a measurement of this college. Real request logs are needed before claiming a real-world effect size.</li>
            <li>One college, one week, no behavioural feedback (waiting longer never changes who cancels), and the scoring weights were tuned on the same generator, which favours the intelligent method somewhat. Rule-based is the fairer yardstick for what the scoring adds.</li>
          </ul>
        </div>
      </div>
      <p className="mt-3 mb-0 max-w-[75ch] text-sm text-muted-foreground">
        Full method description, assumptions and metric definitions: <code className="rounded bg-sunken px-1 py-0.5 font-mono text-[0.8125rem]">research/README.md</code>. Live meetings are still accepted or rejected by faculty as before; this study never touches them.
      </p>
    </section>
  );
}
