"""Synthetic world generator for the scheduling research experiment.

This data is entirely separate from live Campus Connect accounts (PRD/ESD rule #19): it never
touches the users/students/faculty tables. A "world" is one simulated working week:

* time is an integer number of minutes from the start of the week. Day ``d`` covers
  ``[d * day_minutes, (d + 1) * day_minutes)``; with the defaults minute 0 is Monday 09:00 and
  nights/week-ends are simply not on the axis;
* every faculty member has several posted availability windows per day and a class timetable
  that BLOCKS time (a meeting may never overlap a class);
* students send requests whose arrival times follow a two-rush-window pattern (just before lunch
  and at the end of the day); each request has a duration (10/15/20/30), a priority
  (1 normal / 2 priority / 3 urgent), the student's preferred time window, and hidden
  outcomes (cancels before the meeting / does not show up);
* everything is drawn from one ``random.Random(seed)``, so a (seed, load) pair is fully
  deterministic and every scheduling method receives exactly the same world.

Pure Python: no numpy/pandas.
"""
import copy
import csv
import os
import random

DEFAULT_CONFIG = {
    "days": 5,
    "day_minutes": 480,              # 09:00-17:00
    "day_start_clock": "09:00",
    "grid_min": 5,                   # meetings start on a 5-minute grid
    "num_faculty": 12,
    "num_students": 150,
    "loads": {"low": 240, "medium": 360, "high": 480},   # requests per week
    "durations": [10, 15, 20, 30],
    "duration_weights": [0.25, 0.35, 0.25, 0.15],
    "priority_weights": [0.75, 0.18, 0.07],              # normal, priority, urgent
    "rush_windows": [[105, 165], [375, 435]],            # minute-of-day: before lunch, end of day
    "rush_share": 0.60,              # share of requests that arrive inside a rush window
    "last_arrival_min_of_day": 450,
    "lunch": [180, 240],             # nobody is available or teaching at lunch
    "faculty_popularity_exponent": 0.6,   # some faculty are much more in demand than others
    "student_activity_sigma": 0.9,        # some students request far more often than others
    "flaky_student_share": 0.15,
    "cancel_prob": {"reliable": 0.06, "flaky": 0.14},
    "no_show_prob": {"reliable": 0.03, "flaky": 0.20},
    "cancel_notice_choices": [30, 60, 120, 240, 480, 960],   # how long before the meeting a cancel happens
    "standby_share": 0.5,            # share of students who accept an on-call "walk-in" slot
    "window_lead_choices": [0, 0, 15, 30, 60],          # earliest acceptable start after arrival
    "window_width": {"1": [360, 1440], "2": [240, 960], "3": [120, 480]},   # per priority
    "batch_interval_min": 15,        # rule-based / intelligent schedulers run every 15 min
    "no_show_grace_min": 5,          # faculty waits this long before declaring a no-show
    # how the MANUAL (FCFS) baseline works - these two only affect the FCFS method
    "manual_slot_min": 15,           # faculty post fixed 15-minute slots; a meeting takes whole slots
    "manual_collision_discovery": "meeting_start",   # or "day_start": when a class clash is noticed
}

PRIORITY_LABELS = {1: "normal", 2: "priority", 3: "urgent"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

REQUEST_FIELDS = [
    "request_id", "student_id", "faculty_id", "arrival_min", "day", "arrival_clock",
    "duration_min", "priority", "priority_label", "pref_from_min", "pref_to_min", "peak_period",
    "will_cancel", "cancel_notice_min", "will_no_show", "accepts_standby",
]
SCHEDULE_FIELDS = ["faculty_id", "kind", "day", "start_min", "end_min", "start_clock", "end_clock"]


def get_config(overrides=None):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    for key, value in (overrides or {}).items():
        cfg[key] = copy.deepcopy(value)
    return cfg


def horizon(cfg):
    return cfg["days"] * cfg["day_minutes"]


def clock(minute, cfg=None):
    """Human readable 'Mon 09:15' for an absolute minute (defaults: 480-min days from 09:00)."""
    day_minutes = (cfg or DEFAULT_CONFIG)["day_minutes"]
    start_clock = (cfg or DEFAULT_CONFIG)["day_start_clock"]
    sh, sm = (int(x) for x in start_clock.split(":"))
    day, rem = divmod(int(minute), day_minutes)
    total = sh * 60 + sm + rem
    return f"{WEEKDAYS[day % 7]} {total // 60:02d}:{total % 60:02d}"


# --------------------------------------------------------------------------------------
# faculty timetables
# --------------------------------------------------------------------------------------

def _make_faculty_day(rng, cfg, day):
    base = day * cfg["day_minutes"]
    lunch_s, lunch_e = cfg["lunch"]
    # class periods: 2-3 one-hour periods on the hourly grid, never over lunch
    starts = [h for h in range(0, cfg["day_minutes"], 60) if h + 60 <= lunch_s or h >= lunch_e]
    classes = sorted(rng.sample(starts, rng.choice([2, 3])))
    classes = [[base + s, base + s + 60] for s in classes]

    # availability: 2-3 posted office-hour windows (45-120 min), not over lunch, not overlapping
    segments = [(0, lunch_s), (lunch_e, cfg["day_minutes"])]
    windows = []
    for _ in range(rng.choice([2, 3])):
        for _try in range(25):
            seg_s, seg_e = rng.choice(segments)
            length = rng.choice([45, 60, 90, 120])
            if seg_e - seg_s < length:
                continue
            start = seg_s + 5 * rng.randint(0, (seg_e - seg_s - length) // 5)
            cand = [base + start, base + start + length]
            if all(cand[1] + 15 <= w[0] or cand[0] >= w[1] + 15 for w in windows):
                windows.append(cand)
                break
    windows.sort()
    return windows, classes


def _make_faculty(rng, cfg):
    faculty = []
    for fid in range(1, cfg["num_faculty"] + 1):
        windows, classes = [], []
        for day in range(cfg["days"]):
            w, c = _make_faculty_day(rng, cfg, day)
            windows.extend(w)
            classes.extend(c)
        faculty.append({"faculty_id": fid, "name": f"Faculty {fid}", "windows": windows, "classes": classes})
    return faculty


# --------------------------------------------------------------------------------------
# requests
# --------------------------------------------------------------------------------------

def _in_rush(minute_of_day, cfg):
    return any(a <= minute_of_day < b for a, b in cfg["rush_windows"])


def generate_world(seed=1, load="medium", num_requests=None, config=None):
    """Return a fully deterministic world dict for (seed, load).

    ``num_requests`` overrides the per-load volume (used by the API for quick runs)."""
    cfg = get_config(config)
    rng = random.Random(f"campus-connect-scheduling/{seed}")
    if num_requests is None:
        if load not in cfg["loads"]:
            raise ValueError(f"unknown load level: {load!r}")
        num_requests = cfg["loads"][load]
    num_requests = int(num_requests)

    faculty = _make_faculty(rng, cfg)
    fids = [f["faculty_id"] for f in faculty]

    # popularity: rank r gets weight r^-exponent; ranks are shuffled so it is not always faculty 1
    ranks = list(range(1, len(fids) + 1))
    rng.shuffle(ranks)
    fac_weights = [r ** -cfg["faculty_popularity_exponent"] for r in ranks]

    # students: lognormal activity (a few very active students), 15% are "flaky"
    sids = list(range(1, cfg["num_students"] + 1))
    stu_weights = [rng.lognormvariate(0.0, cfg["student_activity_sigma"]) for _ in sids]
    flaky = {s: rng.random() < cfg["flaky_student_share"] for s in sids}
    standby = {s: rng.random() < cfg["standby_share"] for s in sids}

    total_h = horizon(cfg)
    rows = []
    for _ in range(num_requests):
        day = rng.randrange(cfg["days"])
        if rng.random() < cfg["rush_share"]:
            a, b = rng.choice(cfg["rush_windows"])
            mod = rng.randrange(a, b)
        else:
            mod = rng.randrange(0, cfg["last_arrival_min_of_day"])
        arrival = day * cfg["day_minutes"] + mod
        priority = rng.choices([1, 2, 3], weights=cfg["priority_weights"])[0]
        duration = rng.choices(cfg["durations"], weights=cfg["duration_weights"])[0]
        sid = rng.choices(sids, weights=stu_weights)[0]
        fid = rng.choices(fids, weights=fac_weights)[0]
        lead = rng.choice(cfg["window_lead_choices"])
        lo_w, hi_w = cfg["window_width"][str(priority)]
        width = 5 * rng.randint(lo_w // 5, hi_w // 5)
        pref_from = min(total_h, arrival + lead)
        pref_to = min(total_h, pref_from + width)
        kind = "flaky" if flaky[sid] else "reliable"
        u = rng.random()
        will_cancel = u < cfg["cancel_prob"][kind]
        will_no_show = (not will_cancel) and rng.random() < cfg["no_show_prob"][kind]
        rows.append({
            "student_id": sid, "faculty_id": fid, "arrival_min": arrival,
            "duration_min": duration, "priority": priority,
            "pref_from_min": pref_from, "pref_to_min": pref_to,
            "peak_period": int(_in_rush(mod, cfg)),
            "will_cancel": int(will_cancel),
            "cancel_notice_min": rng.choice(cfg["cancel_notice_choices"]),
            "will_no_show": int(will_no_show),
            "accepts_standby": int(standby[sid]),
        })

    rows.sort(key=lambda r: (r["arrival_min"], r["student_id"], r["faculty_id"]))
    requests = []
    for i, r in enumerate(rows, start=1):
        r["request_id"] = i
        r["day"] = r["arrival_min"] // cfg["day_minutes"]
        r["arrival_clock"] = clock(r["arrival_min"], cfg)
        r["priority_label"] = PRIORITY_LABELS[r["priority"]]
        requests.append({k: r[k] for k in REQUEST_FIELDS})
    return {"config": cfg, "seed": seed, "load": load, "faculty": faculty, "requests": requests}


# --------------------------------------------------------------------------------------
# dataset statistics and CSV export
# --------------------------------------------------------------------------------------

def effective_windows(faculty):
    """Posted windows minus the class timetable (what a faculty member can really use)."""
    classes = sorted(tuple(c[:2]) for c in faculty["classes"])
    out = []
    for ws, we in sorted(tuple(w[:2]) for w in faculty["windows"]):
        cur = ws
        for cs, ce in classes:
            if ce <= cur or cs >= we:
                continue
            if cs > cur:
                out.append((cur, cs))
            cur = max(cur, ce)
        if cur < we:
            out.append((cur, we))
    return out


def dataset_stats(world):
    reqs = world["requests"]
    n = len(reqs) or 1
    eff = sum(e - s for f in world["faculty"] for s, e in effective_windows(f))
    posted = sum(w[1] - w[0] for f in world["faculty"] for w in f["windows"])
    demand = sum(r["duration_min"] for r in reqs)
    return {
        "requests": len(reqs),
        "students_requesting": len({r["student_id"] for r in reqs}),
        "rush_share": round(sum(r["peak_period"] for r in reqs) / n, 4),
        "urgent_share": round(sum(1 for r in reqs if r["priority"] == 3) / n, 4),
        "priority_share": round(sum(1 for r in reqs if r["priority"] == 2) / n, 4),
        "cancel_share": round(sum(r["will_cancel"] for r in reqs) / n, 4),
        "no_show_share": round(sum(r["will_no_show"] for r in reqs) / n, 4),
        "mean_duration_min": round(demand / n, 2),
        "posted_availability_min": posted,
        "effective_availability_min": eff,
        "offered_load": round(demand / eff, 4) if eff else None,
    }


def save_requests_csv(world, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REQUEST_FIELDS)
        writer.writeheader()
        writer.writerows(world["requests"])


def save_schedule_csv(world, path):
    """Faculty availability windows and class blocks, one row each."""
    cfg = world["config"]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCHEDULE_FIELDS)
        writer.writeheader()
        for fac in world["faculty"]:
            for kind, blocks in (("availability", fac["windows"]), ("class", fac["classes"])):
                for s, e in sorted(blocks):
                    writer.writerow({
                        "faculty_id": fac["faculty_id"], "kind": kind, "day": s // cfg["day_minutes"],
                        "start_min": s, "end_min": e, "start_clock": clock(s, cfg), "end_clock": clock(e, cfg),
                    })


_INT_FIELDS = ("request_id", "student_id", "faculty_id", "arrival_min", "day", "duration_min", "priority",
               "pref_from_min", "pref_to_min", "peak_period", "will_cancel", "cancel_notice_min",
               "will_no_show", "accepts_standby")


def load_requests_csv(path):
    with open(path, "r", encoding="utf-8") as f:
        rows = []
        for row in csv.DictReader(f):
            rec = dict(row)
            for key in _INT_FIELDS:
                rec[key] = int(row[key])
            rows.append(rec)
    return rows
