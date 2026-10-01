"""Reusable experiment logic: run the three methods on many seeds, summarise, compare.

Used by ``research/run_experiment.py`` (full 30-seed study, writes files) and by the admin API
(``api/routers/research.py``: small, time-boxed runs). Pure Python; no numpy/pandas.
"""
import copy
import math
import statistics
import time

from services.scheduling import fcfs, intelligent, metrics, rule_based, simulator

LOADS = ("low", "medium", "high")
EVAL_SEEDS = tuple(range(1, 31))          # reported results
TUNING_SEEDS = tuple(range(1001, 1021))   # used (only) to hand-tune the intelligent weights

RESEARCH_QUESTION = ("Can data-driven scheduling reduce student waiting time and improve faculty-student "
                     "meeting efficiency compared with the current/manual scheduling approach?")

METHODS = {
    "fcfs": {
        "label": "FCFS / manual",
        "description": "Fixed 15-minute posted slots, first come first served, class timetable ignored "
                      "until a clash is found (counted as a conflict), no waiting list.",
        "fn": fcfs.schedule,
    },
    "rule_based": {
        "label": "Rule-based",
        "description": "Every 30 min: sort by priority, then earliest-fit slot that respects the class "
                      "timetable and the student's window. No waiting list.",
        "fn": rule_based.schedule,
    },
    "intelligent": {
        "label": "Intelligent (proposed)",
        "description": "Explainable scoring: priority + fairness aging + window slack + no-show risk decide "
                      "who goes first; wait + packing + peak spreading decide where; waiting-list back-fill "
                      "and urgent displacement recover lost capacity.",
        "fn": intelligent.schedule,
    },
}
METHOD_IDS = tuple(METHODS)

# better: "higher" / "lower" = which direction is an improvement; None = informational only.
METRICS = {
    "avg_wait_min": {"label": "Average waiting time", "unit": "min", "better": "lower", "headline": True},
    "median_wait_min": {"label": "Median waiting time", "unit": "min", "better": "lower", "headline": True},
    "p90_wait_min": {"label": "90th percentile waiting time", "unit": "min", "better": "lower", "headline": True},
    "avg_wait_incl_unserved_min": {"label": "Avg wait incl. unserved (charged full window)", "unit": "min",
                                   "better": "lower", "headline": False},
    "served_meetings": {"label": "Meetings held", "unit": "count", "better": "higher", "headline": True},
    "success_rate": {"label": "Success rate (held / requested)", "unit": "fraction", "better": "higher",
                     "headline": True},
    "faculty_idle_min": {"label": "Faculty idle time", "unit": "min", "better": "lower", "headline": True},
    "utilization": {"label": "Faculty time utilisation", "unit": "fraction", "better": "higher",
                    "headline": False},
    "wasted_min": {"label": "Wasted booked minutes", "unit": "min", "better": "lower", "headline": True},
    "schedule_conflicts": {"label": "Schedule conflicts", "unit": "count", "better": "lower", "headline": True},
    "cancellations": {"label": "Cancellations (of booked)", "unit": "count", "better": None, "headline": True},
    "no_shows": {"label": "No-shows (of booked)", "unit": "count", "better": None, "headline": True},
    "fairness_jain": {"label": "Fairness (Jain index, per-student served rate)", "unit": "index",
                      "better": "higher", "headline": True},
    "fairness_wait_jain": {"label": "Fairness of waiting (Jain index)", "unit": "index", "better": "higher",
                           "headline": False},
    "students_served": {"label": "Students served", "unit": "count", "better": "higher", "headline": True},
    "urgent_success_rate": {"label": "Urgent requests held", "unit": "fraction", "better": "higher",
                            "headline": False},
    "urgent_avg_wait_min": {"label": "Urgent avg waiting time", "unit": "min", "better": "lower",
                            "headline": False},
    "peak_success_rate": {"label": "Rush-window requests held", "unit": "fraction", "better": "higher",
                          "headline": False},
    "backfilled_meetings": {"label": "Meetings recovered by back-fill", "unit": "count", "better": None,
                            "headline": False},
}

# two-sided 95% Student t critical values for df = 1..30
_T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145,
         2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048,
         2.045, 2.042]


def t_crit(df):
    if df < 1:
        return None
    return _T975[df - 1] if df <= 30 else 1.96


def mean_ci(values):
    """mean, sample sd, 95% CI half-width (Student t) of a list; None entries are ignored."""
    xs = [float(v) for v in values if v is not None]
    n = len(xs)
    if n == 0:
        return {"mean": None, "sd": None, "ci95": None, "n": 0}
    m = statistics.mean(xs)
    if n == 1:
        return {"mean": round(m, 4), "sd": None, "ci95": None, "n": 1}
    sd = statistics.stdev(xs)
    return {"mean": round(m, 4), "sd": round(sd, 4), "ci95": round(t_crit(n - 1) * sd / math.sqrt(n), 4), "n": n}


# --------------------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------------------

def run_methods(world, methods=METHOD_IDS):
    """Run the methods on one world. Returns {method_id: (result, metrics)}."""
    out = {}
    for mid in methods:
        result = METHODS[mid]["fn"](world)
        out[mid] = (result, metrics.compute_metrics(world, result))
    return out


def run_level(load, seeds, num_requests=None, config=None, time_budget_s=None, keep_first=False):
    """Run all methods for each seed at one load. Returns (per_seed, stats, first_run, seeds_run)
    where per_seed = {method: [metrics per seed]}."""
    per_seed = {mid: [] for mid in METHOD_IDS}
    dstats = []
    first = None
    started = time.perf_counter()
    done = 0
    for seed in seeds:
        if time_budget_s is not None and done > 0 and time.perf_counter() - started > time_budget_s:
            break
        world = simulator.generate_world(seed, load, num_requests=num_requests, config=config)
        runs = run_methods(world)
        for mid, (_, m) in runs.items():
            per_seed[mid].append(m)
        dstats.append(simulator.dataset_stats(world))
        if keep_first and first is None:
            first = (world, runs)
        done += 1
    return per_seed, dstats, first, done


def summarize(per_seed, keys=None):
    """{method: {metric: {mean, sd, ci95, n}}}"""
    keys = keys or list(METRICS)
    return {mid: {k: mean_ci([m.get(k) for m in rows]) for k in keys} for mid, rows in per_seed.items()}


def summarize_dataset(dstats):
    keys = dstats[0].keys() if dstats else []
    return {k: round(statistics.mean(d[k] for d in dstats), 4) for k in keys}


def compare(per_seed, candidate="intelligent", baseline="fcfs"):
    """Per metric: mean change, % improvement (positive = candidate better) and a paired 95% CI."""
    out = {}
    for k, info in METRICS.items():
        a = [m.get(k) for m in per_seed[candidate]]
        b = [m.get(k) for m in per_seed[baseline]]
        pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
        if not pairs:
            continue
        ma = statistics.mean(x for x, _ in pairs)
        mb = statistics.mean(y for _, y in pairs)
        entry = {"candidate_mean": round(ma, 4), "baseline_mean": round(mb, 4)}
        if info["better"] is None:
            entry.update(pct_improvement=None, verdict="informational")
            out[k] = entry
            continue
        sign = 1.0 if info["better"] == "higher" else -1.0
        diffs = [sign * (x - y) for x, y in pairs]
        ci = mean_ci(diffs)
        entry["pct_improvement"] = round(100.0 * sign * (ma - mb) / abs(mb), 2) if mb else None
        entry["paired_diff_mean"] = ci["mean"]
        entry["paired_diff_ci95"] = ci["ci95"]
        if ci["ci95"] is None or ci["mean"] is None or abs(ci["mean"]) <= ci["ci95"]:
            entry["verdict"] = "no_clear_difference"
        else:
            entry["verdict"] = "better" if ci["mean"] > 0 else "worse"
        out[k] = entry
    return out


def _improvements(per_seed):
    return {"intelligent_vs_fcfs": compare(per_seed, "intelligent", "fcfs"),
            "intelligent_vs_rule_based": compare(per_seed, "intelligent", "rule_based"),
            "rule_based_vs_fcfs": compare(per_seed, "rule_based", "fcfs")}


# --------------------------------------------------------------------------------------
# sample timeline (for the admin Gantt view)
# --------------------------------------------------------------------------------------

def timeline(world, runs, n_faculty=4):
    cfg = world["config"]
    fac = world["faculty"][:n_faculty]
    ids = {f["faculty_id"] for f in fac}
    reqs = {r["request_id"]: r for r in world["requests"]}
    out = {
        "seed": world["seed"], "load": world["load"],
        "time_axis": {"days": cfg["days"], "day_minutes": cfg["day_minutes"],
                      "day_start_clock": cfg["day_start_clock"], "unit": "minutes from Monday start of day"},
        "faculty": [{"faculty_id": f["faculty_id"], "name": f["name"],
                     "availability": [list(w) for w in sorted(f["windows"])],
                     "classes": [list(c) for c in sorted(f["classes"])]} for f in fac],
        "methods": {},
    }
    for mid, (result, _) in runs.items():
        blocks = []
        for b in result["blocks"]:
            if b["faculty_id"] not in ids or b["kind"] == "moved":
                continue
            r = reqs[b["request_id"]]
            blocks.append({
                "faculty_id": b["faculty_id"], "request_id": b["request_id"], "student_id": b["student_id"],
                "start_min": b["start_min"], "end_min": b["end_min"], "meeting_min": b["meeting_min"], "day": b["start_min"] // cfg["day_minutes"],
                "start_clock": simulator.clock(b["start_min"], cfg), "kind": b["kind"],
                "backfill": b["backfill"], "priority": r["priority"],
            })
        out["methods"][mid] = blocks
    return out


# --------------------------------------------------------------------------------------
# sensitivity / ablation (medium load)
# --------------------------------------------------------------------------------------

ABLATIONS = {
    "full": {},
    "no_fairness": {"weights": {"fairness": 0.0}},
    "no_slack": {"weights": {"slack": 0.0}},
    "no_risk": {"weights": {"risk": 0.0}},
    "no_packing": {"weights": {"pack": 0.0}},
    "no_peak_spreading": {"weights": {"spread": 0.0}},
    "no_backfill": {"backfill": False},
    "no_displacement": {"displace": False},
}


def run_ablation(seeds, load="medium"):
    worlds = [simulator.generate_world(s, load) for s in seeds]
    rows = {}
    for name, cfg in ABLATIONS.items():
        rows[name] = [metrics.compute_metrics(w, intelligent.schedule(w, cfg)) for w in worlds]
    keys = ["avg_wait_min", "success_rate", "faculty_idle_min", "wasted_min", "fairness_jain", "students_served",
            "urgent_success_rate"]
    return {"load": load, "seeds": list(seeds),
            "variants": {n: {k: mean_ci([m.get(k) for m in r]) for k in keys} for n, r in rows.items()}}


def run_sensitivity(seeds, load="medium"):
    """How much of FCFS's disadvantage comes from its two manual-process assumptions?"""
    variants = {
        "fcfs_default (15-min slots, clash found at meeting)": ({}, None),
        "fcfs_clash_found_at_day_start": ({"manual_collision_discovery": "day_start"}, None),
        "fcfs_flexible_5min_slots": ({}, 5),
        "fcfs_both_relaxed": ({"manual_collision_discovery": "day_start"}, 5),
    }
    keys = ["avg_wait_min", "success_rate", "faculty_idle_min", "schedule_conflicts", "fairness_jain"]
    rows = {n: [] for n in variants}
    ref = {"rule_based": [], "intelligent": []}
    for s in seeds:
        world = simulator.generate_world(s, load)
        for name, (over, slot) in variants.items():
            w = dict(world, config=dict(world["config"], **over))
            rows[name].append(metrics.compute_metrics(w, fcfs.schedule(w, slot_min=slot)))
        for mid in ref:
            ref[mid].append(metrics.compute_metrics(world, METHODS[mid]["fn"](world)))
    out = {n: {k: mean_ci([m.get(k) for m in r]) for k in keys} for n, r in rows.items()}
    for mid, r in ref.items():
        out[f"{mid} (reference)"] = {k: mean_ci([m.get(k) for m in r]) for k in keys}
    return {"load": load, "seeds": list(seeds), "variants": out}


# --------------------------------------------------------------------------------------
# conclusions (generated from the numbers, so they cannot drift from the results)
# --------------------------------------------------------------------------------------

def _pct(entry):
    p = entry.get("pct_improvement")
    return None if p is None else abs(round(p, 1))


def _dir(entry, better_word, worse_word):
    p = entry.get("pct_improvement")
    if p is None:
        return "unchanged"
    return better_word if p > 0 else worse_word


def conclusions(level):
    tab, imp = level["table"], level["improvement"]
    f, r = imp["intelligent_vs_fcfs"], imp["intelligent_vs_rule_based"]

    def m(method, key):
        return tab[method][key]["mean"]

    lines = []
    lines.append(
        f"Waiting time: intelligent {m('intelligent', 'avg_wait_min'):.0f} min vs FCFS {m('fcfs', 'avg_wait_min'):.0f} "
        f"min ({_pct(f['avg_wait_min'])}% {_dir(f['avg_wait_min'], 'lower', 'higher')}, {f['avg_wait_min']['verdict'].replace('_', ' ')}) "
        f"and vs rule-based {m('rule_based', 'avg_wait_min'):.0f} min ({_pct(r['avg_wait_min'])}% "
        f"{_dir(r['avg_wait_min'], 'lower', 'higher')}, {r['avg_wait_min']['verdict'].replace('_', ' ')}).")
    lines.append(
        f"Meetings held: {m('intelligent', 'served_meetings'):.0f} vs {m('fcfs', 'served_meetings'):.0f} (FCFS) and "
        f"{m('rule_based', 'served_meetings'):.0f} (rule-based); success rate {m('intelligent', 'success_rate'):.1%} vs "
        f"{m('fcfs', 'success_rate'):.1%} and {m('rule_based', 'success_rate'):.1%}.")
    lines.append(
        f"Faculty time: idle time {m('intelligent', 'faculty_idle_min'):.0f} min vs {m('fcfs', 'faculty_idle_min'):.0f} "
        f"(FCFS) / {m('rule_based', 'faculty_idle_min'):.0f} (rule-based); schedule conflicts "
        f"{m('intelligent', 'schedule_conflicts'):.0f} vs {m('fcfs', 'schedule_conflicts'):.0f} (FCFS) and "
        f"{m('rule_based', 'schedule_conflicts'):.0f} (rule-based).")
    lines.append(
        f"Fairness (Jain): {m('intelligent', 'fairness_jain'):.3f} vs {m('fcfs', 'fairness_jain'):.3f} (FCFS) and "
        f"{m('rule_based', 'fairness_jain'):.3f} (rule-based); urgent requests held "
        f"{m('intelligent', 'urgent_success_rate'):.1%} vs {m('fcfs', 'urgent_success_rate'):.1%} and "
        f"{m('rule_based', 'urgent_success_rate'):.1%}.")
    weak = weakest_metric(level)
    if weak:
        lines.append(
            f"Weakest metric for the intelligent method: {METRICS[weak['metric']]['label']} "
            f"({weak['pct_improvement']:+.1f}% vs rule-based, {weak['verdict'].replace('_', ' ')}). "
            "Most of the gain over FCFS comes from respecting the class timetable and flexible meeting "
            "lengths (already present in rule-based); the scoring layer adds smaller gains. Data are synthetic.")
    return lines


def weakest_metric(level):
    """The headline metric where the intelligent method does worst relative to rule-based."""
    worst = None
    for k, e in level["improvement"]["intelligent_vs_rule_based"].items():
        if not METRICS[k]["headline"] or e.get("pct_improvement") is None:
            continue
        if worst is None or e["pct_improvement"] < worst["pct_improvement"]:
            worst = {"metric": k, "pct_improvement": e["pct_improvement"], "verdict": e["verdict"]}
    return worst


# --------------------------------------------------------------------------------------
# full study
# --------------------------------------------------------------------------------------

def run_experiment(seeds=EVAL_SEEDS, loads=LOADS, ablation=True, sample=True):
    """The complete study. Returns (results_dict, samples) where samples = {(load): (world, runs)}."""
    cfg = simulator.get_config()
    results = {
        "question": RESEARCH_QUESTION,
        "config": {
            "world": cfg,
            "intelligent": intelligent.CONFIG,
            "eval_seeds": list(seeds),
            "tuning_seeds": [TUNING_SEEDS[0], TUNING_SEEDS[-1]],
            "tuning_note": "Intelligent weights were hand-tuned on the tuning seeds (medium load) only; "
                           "evaluation seeds were never used for tuning.",
        },
        "methods": {k: {"label": v["label"], "description": v["description"]} for k, v in METHODS.items()},
        "metrics": METRICS,
        "levels": {},
    }
    samples = {}
    for load in loads:
        per_seed, dstats, first, _ = run_level(load, seeds, keep_first=sample)
        level = {
            "num_requests": cfg["loads"][load],
            "dataset": summarize_dataset(dstats),
            "table": summarize(per_seed),
            "improvement": _improvements(per_seed),
        }
        level["conclusions"] = conclusions(level)
        level["weakest_metric"] = weakest_metric(level)
        results["levels"][load] = level
        if first:
            samples[load] = first
    if ablation:
        results["ablation"] = run_ablation(seeds)
        results["sensitivity"] = run_sensitivity(seeds)
    if "medium" in results["levels"]:
        results["conclusions"] = results["levels"]["medium"]["conclusions"]
    return results, samples


def run_custom(seeds, load, num_requests=None, time_budget_s=2.0):
    """Small time-boxed run for the admin API. Returns a JSON-ready dict."""
    started = time.perf_counter()
    seed_list = list(range(1, int(seeds) + 1))
    per_seed, dstats, first, done = run_level(load, seed_list, num_requests=num_requests,
                                              time_budget_s=time_budget_s, keep_first=True)
    world, runs = first
    level_table = summarize(per_seed)
    return {
        "ok": True,
        "load": load,
        "num_requests": len(world["requests"]),
        "seeds_requested": len(seed_list),
        "seeds_run": done,
        "truncated": done < len(seed_list),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "methods": {k: {"label": v["label"]} for k, v in METHODS.items()},
        "metrics": {k: METRICS[k] for k in METRICS if METRICS[k]["headline"]},
        "table": {mid: {k: row[k] for k in METRICS if METRICS[k]["headline"]} for mid, row in level_table.items()},
        "improvement": {name: {k: v for k, v in comp.items() if METRICS[k]["headline"]}
                        for name, comp in _improvements(per_seed).items()},
        "dataset": summarize_dataset(dstats),
        "timeline": timeline(world, runs),
    }


def deep_copy_world(world):
    return copy.deepcopy(world)
