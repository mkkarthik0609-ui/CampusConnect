import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Play } from "lucide-react";
import { FormField } from "@/components/app/FormField";
import { Notice } from "@/components/app/Notice";
import { SubmitButton } from "@/components/app/SubmitButton";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, errorMessage } from "@/lib/api";
import { researchApi } from "@/lib/endpoints";
import { ComparisonTable } from "./ComparisonTable";
import { Timeline } from "./Timeline";
import { LOADS } from "./model";

/** "Run a live simulation": POST /api/research/run, then the metrics table and the per-faculty timeline. */
export function LiveSimulation({ defaultLoad = "medium" }) {
  const [seeds, setSeeds] = useState("5");
  const [load, setLoad] = useState(defaultLoad);
  const [errors, setErrors] = useState({});

  const run = useMutation({
    mutationFn: (body) => researchApi.run(body),
    onSuccess: (res) => {
      setErrors({});
      toast.success(res.truncated ? `Stopped early: ${res.seeds_run} of ${res.seeds_requested} weeks simulated.` : `Simulated ${res.seeds_run} ${res.seeds_run === 1 ? "week" : "weeks"} in ${res.elapsed_ms} ms.`);
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields || {}).length) setErrors(err.fields);
      toast.error(errorMessage(err));
    },
  });

  function submit(e) {
    e.preventDefault();
    const n = Number(seeds);
    if (!Number.isInteger(n) || n < 1 || n > 30) {
      setErrors({ seeds: "Enter a whole number from 1 to 30." });
      return;
    }
    setErrors({});
    run.mutate({ seeds: n, load });
  }

  const res = run.data;

  return (
    <div>
      <form onSubmit={submit} noValidate className="flex flex-wrap items-end gap-4">
        <FormField label="Weeks to simulate" hint="1 to 30. Each is a fresh random week." error={errors.seeds} className="w-40">
          <Input type="number" inputMode="numeric" min={1} max={30} value={seeds} onChange={(e) => setSeeds(e.target.value)} />
        </FormField>
        <FormField label="Load" error={errors.load} className="w-52">
          {({ id }) => (
            <Select value={load} onValueChange={setLoad}>
              <SelectTrigger id={id}><SelectValue /></SelectTrigger>
              <SelectContent position="popper">
                {LOADS.map((l) => <SelectItem key={l.id} value={l.id}>{l.label}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        </FormField>
        <div className="pb-[1.6rem] max-sm:w-full">
          <SubmitButton loading={run.isPending} loadingText="Simulating..." className="max-sm:w-full"><Play aria-hidden="true" />Run simulation</SubmitButton>
        </div>
      </form>
      <p className="mt-0 mb-5 max-w-[62ch] text-sm text-muted-foreground">
        Synthetic data only. This never reads or changes real students, faculty or meetings. Results are deterministic: the same number of weeks always gives the same numbers.
      </p>

      <div aria-live="polite">
        {run.isError && !Object.keys(errors).length ? <Notice tone="danger" title="The simulation did not run">{run.error?.message}</Notice> : null}
      </div>

      {res ? (
        <div className="grid gap-8">
          {res.truncated ? (
            <Notice tone="warning" title="Stopped early to keep the server responsive">
              {res.seeds_run} of {res.seeds_requested} weeks were simulated, so the intervals are wider.
            </Notice>
          ) : null}
          <section aria-label="Live simulation results">
            <h3 className="mb-1 text-lg font-bold">Results ({res.seeds_run} {res.seeds_run === 1 ? "week" : "weeks"}, {res.load} load, {res.num_requests} requests per week)</h3>
            <p className="mt-0 mb-3 text-sm text-muted-foreground">
              Few weeks means wide intervals: with only a handful of seeds many differences are not distinguishable from noise.
            </p>
            <ComparisonTable caption="Live simulation: mean and 95% interval for each method" table={res.table} improvement={res.improvement} metrics={res.metrics} />
          </section>
          {res.timeline ? (
            <section aria-label="Week timeline">
              <h3 className="mb-1 text-lg font-bold">One simulated week, per faculty member</h3>
              <p className="mt-0 mb-3 max-w-[70ch] text-sm text-muted-foreground">
                The same requests, scheduled three ways. FCFS blocks whole 15 minute slots and does not look at the class timetable, so it wastes minutes and double-books classes.
              </p>
              <Timeline timeline={res.timeline} />
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
