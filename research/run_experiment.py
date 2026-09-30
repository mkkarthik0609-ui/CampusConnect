"""Entry point for the scheduling research experiment.

Generates (or reuses) one synthetic dataset and runs all three scheduling methods
against the *same* input data, then writes a comparison table and charts to
research/results/. Run from the project root:

    venv\\Scripts\\python.exe research\\run_experiment.py
"""
import os
import sys
import json
import csv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.scheduling import simulator, fcfs, rule_based, intelligent, metrics

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "requests.csv")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

METHODS = {
    "FCFS": fcfs.schedule,
    "Rule-Based": rule_based.schedule,
    "Intelligent": intelligent.schedule,
}


def run(num_requests=300, seed=42, regenerate=False):
    if regenerate or not os.path.exists(DATA_PATH):
        rows = simulator.generate_dataset(num_requests=num_requests, seed=seed)
        simulator.save_dataset(rows, DATA_PATH)
    else:
        rows = simulator.load_dataset(DATA_PATH)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    comparison = {}
    for name, fn in METHODS.items():
        result_rows = fn(rows)
        method_metrics = metrics.compute_metrics(result_rows, rows)
        comparison[name] = method_metrics
        with open(os.path.join(RESULTS_DIR, f"{name.lower().replace('-', '_')}_assignments.csv"), "w",
                  newline="", encoding="utf-8") as f:
            fieldnames = sorted({k for row in result_rows for k in row.keys()})
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result_rows)

    with open(os.path.join(RESULTS_DIR, "comparison.json"), "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    _write_markdown_table(comparison)
    _write_charts(comparison)
    return comparison


def _write_markdown_table(comparison):
    metric_keys = list(next(iter(comparison.values())).keys())
    lines = ["| Metric | " + " | ".join(comparison.keys()) + " |",
             "|---" * (len(comparison) + 1) + "|"]
    for key in metric_keys:
        row = [str(comparison[m][key]) for m in comparison]
        lines.append(f"| {key} | " + " | ".join(row) + " |")
    with open(os.path.join(RESULTS_DIR, "comparison.md"), "w", encoding="utf-8") as f:
        f.write("# Scheduling Method Comparison\n\n")
        f.write("\n".join(lines))
        f.write("\n")


def _write_charts(comparison):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    methods = list(comparison.keys())
    colors = ["#1a7f37", "#2f2f2f", "#6b6b6b"]

    def bar_chart(metric_key, title, filename, ylabel):
        values = [comparison[m][metric_key] or 0 for m in methods]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(methods, values, color=colors)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        fig.tight_layout()
        fig.savefig(os.path.join(RESULTS_DIR, filename))
        plt.close(fig)

    bar_chart("avg_waiting_time_min", "Average Waiting Time", "chart_avg_waiting_time.png", "minutes")
    bar_chart("success_rate", "Scheduling Success Rate", "chart_success_rate.png", "fraction")
    bar_chart("faculty_idle_time_min", "Faculty Idle Time", "chart_faculty_idle_time.png", "minutes")
    bar_chart("schedule_conflicts", "Schedule Conflicts", "chart_conflicts.png", "count")
    bar_chart(
        "fairness_stdev_of_student_avg_wait", "Fairness (lower = more equal waiting)",
        "chart_fairness.png", "stdev of per-student avg wait (min)",
    )


if __name__ == "__main__":
    result = run(regenerate=True)
    for method, m in result.items():
        print(f"\n=== {method} ===")
        for k, v in m.items():
            print(f"  {k}: {v}")
    print(f"\nResults written to {RESULTS_DIR}")
