"""Run the scheduling research experiment and write everything to research/.

    venv\\Scripts\\python.exe research\\run_experiment.py            (about 30-40 s)
    venv\\Scripts\\python.exe research\\run_experiment.py --seeds 5 --no-ablation   (quick look)

Outputs
  research/data/requests.csv, faculty_schedule.csv   sample synthetic dataset (seed 1, medium load)
  research/results/results.json                      full machine-readable results
  research/results/comparison.md                     human-readable tables and conclusions
  research/results/{fcfs,rule_based,intelligent}_assignments.csv   one sample run per method
  research/results/chart_*.png                       (only if matplotlib is installed)
"""
import argparse
import csv
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from services.scheduling import experiment, simulator  # noqa: E402

DATA_DIR = os.path.join(ROOT, "research", "data")
RESULTS_DIR = os.path.join(ROOT, "research", "results")

TABLE_ROWS = ["avg_wait_min", "median_wait_min", "p90_wait_min", "served_meetings", "success_rate",
              "faculty_idle_min", "wasted_min", "schedule_conflicts", "cancellations", "no_shows",
              "fairness_jain", "students_served"]
EXTRA_ROWS = ["avg_wait_incl_unserved_min", "utilization", "urgent_success_rate", "urgent_avg_wait_min",
              "peak_success_rate", "fairness_wait_jain", "backfilled_meetings"]


def _fmt(cell, key):
    if cell is None or cell["mean"] is None:
        return "-"
    frac = experiment.METRICS[key]["unit"] in ("fraction", "index")
    nd = 3 if frac else 1
    ci = "" if cell["ci95"] is None else f" ± {cell['ci95']:.{nd}f}"
    return f"{cell['mean']:.{nd}f}{ci}"


def _pct(entry):
    if entry is None or entry.get("pct_improvement") is None:
        return "n/a"
    mark = {"better": " *", "worse": " !", "no_clear_difference": "", "informational": ""}[entry["verdict"]]
    return f"{entry['pct_improvement']:+.1f}%{mark}"


def write_comparison_md(results, path):
    seeds = results["config"]["eval_seeds"]
    out = ["# Scheduling method comparison", "",
           f"> {results['question']}", "",
           f"Synthetic data, {len(seeds)} seeds per load level (seeds {seeds[0]}-{seeds[-1]}), mean ± 95% CI "
           "(Student t). `% vs FCFS` / `% vs Rule` = improvement of the Intelligent method "
           "(positive = better, direction accounts for lower-is-better metrics); `*` = paired 95% CI excludes "
           "zero and Intelligent is better, `!` = paired 95% CI excludes zero and Intelligent is WORSE.", ""]
    for load, level in results["levels"].items():
        ds = level["dataset"]
        out += [f"## {load.capitalize()} load ({level['num_requests']} requests / week)", "",
                f"Offered load = requested minutes / usable faculty minutes = {ds['offered_load']:.2f}; "
                f"{ds['students_requesting']:.0f} students ask on average; {ds['rush_share']:.0%} of requests "
                f"arrive in the two rush windows.", "",
                "| Metric | FCFS / manual | Rule-based | Intelligent | % vs FCFS | % vs Rule |",
                "|---|---|---|---|---|---|"]
        for key in TABLE_ROWS:
            info = experiment.METRICS[key]
            unit = "" if info["unit"] in ("count", "fraction", "index") else f" ({info['unit']})"
            out.append("| {} | {} | {} | {} | {} | {} |".format(
                info["label"] + unit,
                *[_fmt(level["table"][m][key], key) for m in experiment.METHOD_IDS],
                _pct(level["improvement"]["intelligent_vs_fcfs"].get(key)),
                _pct(level["improvement"]["intelligent_vs_rule_based"].get(key))))
        out += ["", "<details><summary>More metrics</summary>", "",
                "| Metric | FCFS / manual | Rule-based | Intelligent |", "|---|---|---|---|"]
        for key in EXTRA_ROWS:
            out.append("| {} | {} | {} | {} |".format(
                experiment.METRICS[key]["label"], *[_fmt(level["table"][m][key], key) for m in experiment.METHOD_IDS]))
        out += ["", "</details>", ""]
    out += ["## Conclusion (medium load)", ""]
    out += [f"{i}. {line}" for i, line in enumerate(results.get("conclusions", []), 1)]
    if "ablation" in results:
        out += ["", "## Which parts of the intelligent method matter? (medium load, ablation)", "",
                "| Variant | Avg wait (min) | Success rate | Idle (min) | Wasted (min) | Fairness | Urgent held |",
                "|---|---|---|---|---|---|---|"]
        for name, row in results["ablation"]["variants"].items():
            out.append(f"| {name} | " + " | ".join(_fmt(row[k], k) for k in (
                "avg_wait_min", "success_rate", "faculty_idle_min", "wasted_min", "fairness_jain",
                "urgent_success_rate")) + " |")
    if "sensitivity" in results:
        out += ["", "## How much of FCFS's gap is an assumption about manual scheduling? (medium load)", "",
                "| Variant | Avg wait (min) | Success rate | Idle (min) | Conflicts | Fairness |",
                "|---|---|---|---|---|---|"]
        for name, row in results["sensitivity"]["variants"].items():
            out.append(f"| {name} | " + " | ".join(_fmt(row[k], k) for k in (
                "avg_wait_min", "success_rate", "faculty_idle_min", "schedule_conflicts", "fairness_jain")) + " |")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def write_assignments_csv(result, path):
    rows = result["assignments"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------------------
# charts (optional)
# ---------------------------------------------------------------------------------------

CHARTS = [
    ("avg_wait_min", "Average waiting time (lower is better)", "minutes", "chart_avg_waiting_time.png"),
    ("success_rate", "Success rate: meetings held / requested (higher is better)", "share of requests",
     "chart_success_rate.png"),
    ("faculty_idle_min", "Faculty idle time per week (lower is better)", "minutes, all faculty",
     "chart_faculty_idle_time.png"),
    ("schedule_conflicts", "Schedule conflicts per week (lower is better)", "bookings",
     "chart_conflicts.png"),
    ("fairness_jain", "Fairness among students, Jain index (higher is better)", "index (1 = perfectly equal)",
     "chart_fairness.png"),
]
COLORS = {"fcfs": "#2a78d6", "rule_based": "#eb6834", "intelligent": "#1baf7a"}
HATCH = {"fcfs": "", "rule_based": "//", "intelligent": "\\\\"}


def write_charts(results):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed - skipping charts (pip install -r requirements-research.txt)")
        return []
    loads = list(results["levels"])
    written = []
    width = 0.26
    for key, title, ylabel, fname in CHARTS:
        fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=120)
        frac = experiment.METRICS[key]["unit"] in ("fraction", "index")
        for j, mid in enumerate(experiment.METHOD_IDS):
            xs, ys, errs = [], [], []
            for i, load in enumerate(loads):
                cell = results["levels"][load]["table"][mid][key]
                xs.append(i + (j - 1) * width)
                ys.append(cell["mean"] or 0)
                errs.append(cell["ci95"] or 0)
            bars = ax.bar(xs, ys, width * 0.92, yerr=errs, capsize=3, color=COLORS[mid], hatch=HATCH[mid],
                          edgecolor="white", linewidth=0.8, error_kw={"elinewidth": 1, "ecolor": "#3a3a38"},
                          label=experiment.METHODS[mid]["label"])
            for x, y, e in zip(xs, ys, errs):
                ax.text(x, y + e + max(ys) * 0.01, f"{y:.2f}" if frac else f"{y:.0f}", ha="center", va="bottom",
                        fontsize=7, color="#3a3a38")
        ax.set_xticks(range(len(loads)))
        ax.set_xticklabels([f"{l} load\n({results['levels'][l]['num_requests']} requests)" for l in loads])
        ax.set_ylabel(ylabel, color="#3a3a38")
        ax.set_title(title, fontsize=11, loc="left", color="#1a1a19")
        ax.spines[["top", "right"]].set_visible(False)
        ax.yaxis.grid(True, color="#e6e6e3", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3)
        ax.text(1.0, 1.02, f"mean ± 95% CI, {len(results['config']['eval_seeds'])} seeds", transform=ax.transAxes,
                ha="right", fontsize=7, color="#6b6b68")
        fig.tight_layout()
        fig.savefig(os.path.join(RESULTS_DIR, fname))
        plt.close(fig)
        written.append(fname)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=30, help="number of evaluation seeds (default 30)")
    ap.add_argument("--no-ablation", action="store_true", help="skip the ablation and sensitivity tables")
    ap.add_argument("--no-charts", action="store_true")
    args = ap.parse_args(argv)

    started = time.time()
    seeds = experiment.EVAL_SEEDS[:args.seeds] if args.seeds <= 30 else tuple(range(1, args.seeds + 1))
    results, samples = experiment.run_experiment(seeds=seeds, ablation=not args.no_ablation)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    world, runs = samples["medium"]
    simulator.save_requests_csv(world, os.path.join(DATA_DIR, "requests.csv"))
    simulator.save_schedule_csv(world, os.path.join(DATA_DIR, "faculty_schedule.csv"))
    for mid, (result, _) in runs.items():
        write_assignments_csv(result, os.path.join(RESULTS_DIR, f"{mid}_assignments.csv"))
    results["sample_run"] = {"seed": world["seed"], "load": "medium",
                             "metrics": {mid: m for mid, (_, m) in runs.items()}}

    with open(os.path.join(RESULTS_DIR, "results.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(results, f, indent=1)
        f.write("\n")
    write_comparison_md(results, os.path.join(RESULTS_DIR, "comparison.md"))
    charts = [] if args.no_charts else write_charts(results)

    med = results["levels"]["medium"]["table"]
    print(f"{'metric (medium load, mean)':34s}" + "".join(f"{experiment.METHODS[m]['label'][:16]:>18s}"
                                                          for m in experiment.METHOD_IDS))
    for key in TABLE_ROWS:
        print(f"{key:34s}" + "".join(f"{(med[m][key]['mean'] or 0):18.3f}" for m in experiment.METHOD_IDS))
    print("\n" + "\n".join(results["conclusions"]))
    print(f"\nWrote {RESULTS_DIR} ({len(charts)} charts) in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
