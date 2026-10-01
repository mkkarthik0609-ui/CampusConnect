import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader, SectionHeading } from "@/components/app/PageHeader";
import { Notice } from "@/components/app/Notice";
import { Skeleton } from "@/components/ui/skeleton";
import { researchApi, adminKeys } from "@/lib/endpoints";
import { QueryError } from "@/features/admin/common";
import { ComparisonTable } from "@/features/admin/research/ComparisonTable";
import { MetricChart } from "@/features/admin/research/MetricChart";
import { LiveSimulation } from "@/features/admin/research/LiveSimulation";
import { Findings } from "@/features/admin/research/Findings";
import { LOADS, fmtPct } from "@/features/admin/research/model";
import { cn } from "@/lib/utils";
import "@/features/admin/research/research.css";

function LoadTabs({ value, onChange, levels }) {
  return (
    <div role="group" aria-label="Load level" className="inline-flex max-w-full flex-wrap gap-1 rounded-xl bg-muted p-1">
      {LOADS.map((l) => (
        <button
          key={l.id}
          type="button"
          aria-pressed={l.id === value}
          onClick={() => onChange(l.id)}
          className={cn("min-h-9 rounded-lg px-3.5 text-sm font-semibold transition-colors pointer-coarse:min-h-11", l.id === value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
        >
          {l.label}
          {levels?.[l.id] ? <span className="num ml-1.5 text-xs font-normal text-muted-foreground">{levels[l.id].num_requests}/wk</span> : null}
        </button>
      ))}
    </div>
  );
}

/** One plain-language sentence per comparison, built from the numbers on screen. */
function summary(level) {
  const vf = level?.improvement?.intelligent_vs_fcfs;
  const vr = level?.improvement?.intelligent_vs_rule_based;
  if (!vf || !vr) return null;
  const wait = vf.avg_wait_min;
  const held = vf.served_meetings;
  const clashes = level.table?.fcfs?.schedule_conflicts?.mean;
  const waitRule = vr.avg_wait_min;
  return {
    vsFcfs: `Against FCFS, intelligent scheduling ${wait?.pct_improvement >= 0 ? "cut" : "raised"} average waiting by ${fmtPct(wait?.pct_improvement ?? 0)}, held ${fmtPct(held?.pct_improvement ?? 0)} ${held?.pct_improvement >= 0 ? "more" : "fewer"} meetings${clashes ? ` and removed about ${Math.round(clashes)} class clashes a week` : ""}.`,
    vsRule: `Against the simpler rule-based method, it waits ${fmtPct(waitRule?.pct_improvement ?? 0)} ${waitRule?.pct_improvement >= 0 ? "less" : "longer"} on average${waitRule?.verdict === "worse" ? ". This is its weakest result" : ""}.`,
    weakest: level.weakest_metric,
  };
}

export default function AdminResearch() {
  const q = useQuery({ queryKey: adminKeys.research, queryFn: researchApi.results, staleTime: 10 * 60_000 });
  const [load, setLoad] = useState("medium");
  const [metric, setMetric] = useState("avg_wait_min");

  const data = q.data;
  const level = data?.levels?.[load];
  const world = data?.config?.world;
  const sum = summary(level);
  const seedCount = data?.config?.eval_seeds?.length;

  return (
    <div className="rs-root">
      <PageHeader
        title="Scheduling research"
        description="Does data-driven scheduling cut waiting and make faculty time go further? A simulation compares three ways of booking meetings."
      />

      <section aria-label="Research question" className="mb-8 border-l-4 border-saffron pl-4">
        <p className="m-0 text-xs font-bold tracking-[0.08em] text-saffron-ink uppercase">Research question</p>
        <p className="mt-1 mb-0 max-w-[60ch] font-display text-[clamp(1.2rem,1.05rem+0.8vw,1.55rem)] leading-snug font-bold text-balance">
          {data?.question || "Can data-driven scheduling reduce student waiting time and improve faculty-student meeting efficiency vs manual/FCFS?"}
        </p>
        <p className="mt-2 mb-0 max-w-[68ch] text-sm text-muted-foreground">
          Three methods get exactly the same synthetic weeks: <strong>FCFS / manual</strong> (the status quo), <strong>rule-based</strong> (timetable-aware, priority first) and <strong>intelligent</strong> (a transparent scoring layer, no machine learning).
          {world ? ` Each week has ${world.num_faculty} faculty, ${world.num_students} students and ${world.loads?.low} to ${world.loads?.high} meeting requests.` : ""}
          {seedCount ? ` Results are the mean of ${seedCount} random weeks per load level.` : ""}
        </p>
      </section>

      {q.isPending ? (
        <div className="grid gap-4" role="status" aria-busy="true"><span className="sr-only">Loading results</span><Skeleton className="h-24" /><Skeleton className="h-80" /></div>
      ) : null}
      {q.isError ? <QueryError error={q.error} onRetry={q.refetch} title="Could not load the results" /> : null}

      {data ? (
        <>
          {data.generated_on_the_fly ? (
            <Notice tone="warning" className="mb-5" title="Quick results">
              The committed full study was not found, so these were computed on the fly from a few weeks and carry wide intervals.
            </Notice>
          ) : null}

          <section aria-label="Results" className="mb-10">
            <SectionHeading title="The result" as="h2" actions={<LoadTabs value={load} onChange={setLoad} levels={data.levels} />} />
            {sum ? (
              <div className="mb-5 grid max-w-[72ch] gap-1.5 text-[1.0625rem] leading-relaxed">
                <p className="m-0">{sum.vsFcfs}</p>
                <p className="m-0 text-ink-2">{sum.vsRule}</p>
              </div>
            ) : null}
            <ComparisonTable
              caption={`Scheduling methods compared at ${load} load: mean and 95% interval over ${seedCount ?? "several"} weeks`}
              table={level?.table}
              improvement={level?.improvement}
              metrics={data.metrics}
            />
            <p className="mt-2 mb-0 text-[0.8125rem] text-muted-foreground">
              Each cell is the mean plus or minus the 95% interval across weeks. A difference counts as clear only when the paired per-week interval excludes zero. Bold marks the best value in a row (ties are not marked).
            </p>
            {level?.conclusions?.length ? (
              <details className="mt-4 rounded-lg border bg-card">
                <summary className="cursor-pointer rounded-lg px-4 py-3 text-sm font-semibold text-primary hover:bg-primary-soft">Study conclusions for {load} load</summary>
                <ul className="m-0 grid gap-2 px-8 pb-4 text-sm">{level.conclusions.map((c) => <li key={c}>{c}</li>)}</ul>
              </details>
            ) : null}
          </section>

          <section aria-label="Charts" className="mb-10">
            <SectionHeading title="How the gap changes with load" as="h2" />
            <p className="mt-0 mb-4 max-w-[68ch] text-muted-foreground">Pick a metric to compare the methods at low, medium and high demand. Select a group to switch the table above to that load.</p>
            <div className="rounded-lg border bg-card p-4 shadow-sm sm:p-5">
              <MetricChart levels={data.levels} metrics={data.metrics} metricKey={metric} onMetricChange={setMetric} load={load} onLoadChange={setLoad} />
            </div>
          </section>

          <section aria-label="Live simulation" className="mb-10">
            <SectionHeading title="Run a live simulation" as="h2" />
            <div className="rounded-lg border bg-card p-4 shadow-sm sm:p-5">
              <LiveSimulation defaultLoad={load} />
            </div>
          </section>

          <Findings data={data} />
        </>
      ) : null}

    </div>
  );
}
