"""Tests for the scheduling research package (framework-agnostic; no web framework involved)."""
import copy

import pytest

from services.scheduling import core, experiment, fcfs, intelligent, metrics, rule_based, simulator

METHOD_FUNCS = {"fcfs": fcfs.schedule, "rule_based": rule_based.schedule, "intelligent": intelligent.schedule}


@pytest.fixture(scope="module")
def world():
    return simulator.generate_world(seed=7, load="medium")


@pytest.fixture(scope="module")
def runs(world):
    return {name: fn(world) for name, fn in METHOD_FUNCS.items()}


# ------------------------------------------------------------------ determinism / identical inputs

def test_world_is_deterministic_by_seed():
    a = simulator.generate_world(3, "low")
    b = simulator.generate_world(3, "low")
    c = simulator.generate_world(4, "low")
    assert a == b
    assert a["requests"] != c["requests"]


def test_runs_are_deterministic_by_seed():
    for fn in METHOD_FUNCS.values():
        assert fn(simulator.generate_world(5, "medium")) == fn(simulator.generate_world(5, "medium"))


def test_load_levels_scale_the_request_volume():
    sizes = [len(simulator.generate_world(1, load)["requests"]) for load in experiment.LOADS]
    assert sizes == sorted(sizes) and len(set(sizes)) == 3
    assert len(simulator.generate_world(1, "low", num_requests=77)["requests"]) == 77
    with pytest.raises(ValueError):
        simulator.generate_world(1, "extreme")


def test_all_methods_receive_identical_unmodified_input(world):
    before = copy.deepcopy(world)
    results = {name: fn(world) for name, fn in METHOD_FUNCS.items()}
    assert world == before                      # no method mutates the shared world
    id_sets = [{a["request_id"] for a in r["assignments"]} for r in results.values()]
    assert id_sets[0] == id_sets[1] == id_sets[2] == {r["request_id"] for r in world["requests"]}
    for key in ("student_id", "faculty_id", "priority", "arrival_min", "duration_min"):
        cols = [[a[key] for a in r["assignments"]] for r in results.values()]
        assert cols[0] == cols[1] == cols[2]


def test_world_has_the_required_structure(world):
    cfg = world["config"]
    assert len(world["faculty"]) == cfg["num_faculty"]
    assert all(len(f["windows"]) >= cfg["days"] * 2 and f["classes"] for f in world["faculty"])
    reqs = world["requests"]
    assert {r["duration_min"] for r in reqs} <= {10, 15, 20, 30}
    assert {r["priority"] for r in reqs} == {1, 2, 3}
    assert 0.5 < sum(r["peak_period"] for r in reqs) / len(reqs) < 0.85       # two rush windows dominate
    assert any(r["will_cancel"] for r in reqs) and any(r["will_no_show"] for r in reqs)
    assert not any(r["will_cancel"] and r["will_no_show"] for r in reqs)
    assert all(r["pref_from_min"] >= r["arrival_min"] and r["pref_to_min"] >= r["pref_from_min"] for r in reqs)
    assert [r["arrival_min"] for r in reqs] == sorted(r["arrival_min"] for r in reqs)


# ------------------------------------------------------------------ feasibility

def _intervals(world):
    wins = {f["faculty_id"]: [tuple(w) for w in f["windows"]] for f in world["faculty"]}
    classes = {f["faculty_id"]: [tuple(c) for c in f["classes"]] for f in world["faculty"]}
    return wins, classes


@pytest.mark.parametrize("name", ["rule_based", "intelligent"])
def test_no_double_booking_and_no_class_collision(world, runs, name):
    result = runs[name]
    assert metrics.count_conflicts(world, result["blocks"]) == 0
    by_fac = {}
    for b in result["blocks"]:
        if b["kind"] == "served":
            by_fac.setdefault(b["faculty_id"], []).append(b)
    for blocks in by_fac.values():
        blocks.sort(key=lambda b: b["start_min"])
        for a, b in zip(blocks, blocks[1:]):
            assert a["end_min"] <= b["start_min"]


@pytest.mark.parametrize("name", ["fcfs", "rule_based", "intelligent"])
def test_served_meetings_respect_windows_arrival_and_student_preference(world, runs, name):
    wins, classes = _intervals(world)
    reqs = {r["request_id"]: r for r in world["requests"]}
    for a in runs[name]["assignments"]:
        if a["status"] != "served":
            continue
        r = reqs[a["request_id"]]
        assert a["start_min"] >= max(r["arrival_min"], r["pref_from_min"])
        assert a["end_min"] <= r["pref_to_min"]
        assert a["end_min"] - a["start_min"] == r["duration_min"]
        assert a["wait_min"] == a["start_min"] - r["arrival_min"]
        assert any(ws <= a["start_min"] and a["end_min"] <= we for ws, we in wins[a["faculty_id"]])
        # a meeting that took place never sits on a class, whichever method booked it
        assert not any(cs < a["end_min"] and a["start_min"] < ce for cs, ce in classes[a["faculty_id"]])


def test_fcfs_ignores_classes_until_a_clash_is_found(world, runs):
    m_f = metrics.compute_metrics(world, runs["fcfs"])
    assert m_f["schedule_conflicts"] > 0
    assert m_f["collisions_rebooked"] > 0


def test_method_ordering_at_default_load(world, runs):
    m = {k: metrics.compute_metrics(world, r) for k, r in runs.items()}
    assert m["rule_based"]["schedule_conflicts"] == m["intelligent"]["schedule_conflicts"] == 0
    assert m["fcfs"]["success_rate"] < m["rule_based"]["success_rate"] <= m["intelligent"]["success_rate"] + 0.02
    assert m["intelligent"]["fairness_jain"] >= m["fcfs"]["fairness_jain"]
    assert 0.4 < m["fcfs"]["success_rate"] < 0.8      # capacity is tight but not absurd


def test_intelligent_without_scoring_or_recovery_equals_rule_based(world):
    plain = {"displace": False, "backfill": False,
             "weights": {"fairness": 0, "slack": 0, "wait": 0, "risk": 0, "pack": 0, "spread": 0}}
    a = intelligent.schedule(world, plain)
    b = rule_based.schedule(world)
    assert a["assignments"] == b["assignments"]       # same engine + earliest fit + priority order


# ------------------------------------------------------------------ hand-made scenarios

def mini_world(windows, classes, requests):
    cfg = simulator.get_config()
    reqs = []
    for i, r in enumerate(requests, start=1):
        base = {"request_id": i, "student_id": i, "faculty_id": 1, "arrival_min": 0, "day": 0,
                "arrival_clock": "Mon 09:00", "duration_min": 15, "priority": 1, "priority_label": "normal",
                "pref_from_min": 0, "pref_to_min": 500, "peak_period": 0, "will_cancel": 0,
                "cancel_notice_min": 60, "will_no_show": 0, "accepts_standby": 1}
        base.update(r)
        reqs.append(base)
    return {"config": cfg, "seed": 0, "load": "custom",
            "faculty": [{"faculty_id": 1, "name": "F1", "windows": windows, "classes": classes}],
            "requests": reqs}


def test_class_timetable_blocks_rule_based_but_not_fcfs_booking():
    w = mini_world([[0, 60]], [[0, 30]], [{}])
    rb = rule_based.schedule(w)["assignments"][0]
    assert rb["status"] == "served" and rb["start_min"] == 30 and rb["collisions"] == 0
    fc = fcfs.schedule(w)
    a = fc["assignments"][0]
    assert a["collisions"] == 1 and a["rebooked"] == 1 and a["start_min"] == 30     # clash found, moved
    assert metrics.compute_metrics(w, fc)["schedule_conflicts"] == 1


def test_priority_order_in_rule_based_batch():
    w = mini_world([[100, 115]], [], [{"priority": 1, "arrival_min": 1}, {"priority": 3, "arrival_min": 5}])   # same 15-min batch
    out = rule_based.schedule(w)["assignments"]
    assert out[0]["status"] == "unserved" and out[1]["status"] == "served"     # urgent got the only slot
    out = fcfs.schedule(w)["assignments"]
    assert out[0]["status"] == "served" and out[1]["status"] == "unserved"     # FCFS: first come first served


def test_cancelled_slot_is_backfilled_only_by_the_intelligent_method():
    w = mini_world([[100, 130]], [], [
        {"duration_min": 30, "arrival_min": 0, "will_cancel": 1, "cancel_notice_min": 60},
        {"duration_min": 30, "arrival_min": 10},
    ])
    ia = intelligent.schedule(w)["assignments"]
    assert ia[0]["status"] == "cancelled"
    assert ia[1]["status"] == "served" and ia[1]["backfilled"] == 1 and ia[1]["start_min"] == 100
    ra = rule_based.schedule(w)["assignments"]
    assert ra[0]["status"] == "cancelled" and ra[1]["status"] == "unserved"
    m = metrics.compute_metrics(w, intelligent.schedule(w))
    assert m["cancellations"] == 1 and m["wasted_min"] == 0 and m["backfilled_meetings"] == 1


def test_no_show_slot_is_refilled_by_standby_student():
    w = mini_world([[100, 130]], [], [
        {"duration_min": 30, "arrival_min": 0, "will_no_show": 1},
        {"duration_min": 15, "arrival_min": 10, "accepts_standby": 1},
        {"duration_min": 15, "arrival_min": 12, "accepts_standby": 0},
    ])
    ia = intelligent.schedule(w)["assignments"]
    assert ia[0]["status"] == "no_show"
    assert ia[1]["status"] == "served" and ia[1]["start_min"] == 105 and ia[1]["backfilled"] == 1
    assert ia[2]["status"] == "unserved"          # did not accept on-call meetings
    m = metrics.compute_metrics(w, intelligent.schedule(w))
    # the 30-min slot hosted a 15-min standby meeting; 5 min grace + 10 min nobody could use are wasted
    assert m["no_shows"] == 1 and m["no_show_wasted_min"] == 15


def test_urgent_request_displaces_a_movable_normal_booking():
    # the normal booking can move to the second window; the urgent request can only use the first
    w = mini_world([[200, 215], [300, 315]], [], [
        {"priority": 1, "arrival_min": 0, "pref_to_min": 500},
        {"priority": 3, "arrival_min": 20, "pref_from_min": 20, "pref_to_min": 250},
    ])
    ia = intelligent.schedule(w)["assignments"]
    assert ia[1]["status"] == "served" and ia[1]["start_min"] == 200
    assert ia[0]["status"] == "served" and ia[0]["start_min"] == 300 and ia[0]["rebooked"] == 1
    assert rule_based.schedule(w)["assignments"][1]["status"] == "unserved"


# ------------------------------------------------------------------ metric definitions

def test_metric_definitions_on_a_hand_made_case():
    w = mini_world([[0, 60]], [[30, 40]], [
        {"student_id": 1, "duration_min": 15, "priority": 1},
        {"student_id": 1, "duration_min": 10, "priority": 3},
        {"student_id": 2, "duration_min": 10, "will_cancel": 1},
        {"student_id": 3, "duration_min": 10, "pref_to_min": 100, "peak_period": 1},
    ])

    def rec(rid, sid, status, start=None, end=None, wait=None):
        q = w["requests"][rid - 1]
        return {"request_id": rid, "student_id": sid, "faculty_id": 1, "priority": q["priority"],
                "peak_period": q["peak_period"], "arrival_min": 0, "duration_min": q["duration_min"],
                "status": status, "start_min": start, "end_min": end, "wait_min": wait, "booked_at_min": 0,
                "collisions": 0, "rebooked": 0, "backfilled": 0}

    def blk(rid, sid, s, e, kind, booked=0, released=None):
        return {"request_id": rid, "student_id": sid, "faculty_id": 1, "start_min": s, "end_min": e,
                "meeting_min": e - s, "kind": kind, "booked_at_min": booked,
                "released_at_min": e if released is None else released, "backfill": 0, "rebooked": 0}

    result = {
        "assignments": [rec(1, 1, "served", 5, 20, 5), rec(2, 1, "served", 20, 30, 20),
                        rec(3, 2, "cancelled", 40, 50), rec(4, 3, "unserved")],
        "blocks": [blk(1, 1, 5, 20, "served"), blk(2, 1, 20, 30, "served"),
                   blk(3, 2, 40, 50, "cancelled", released=10), blk(4, 3, 35, 45, "conflict", released=0)],
    }
    m = metrics.compute_metrics(w, result)
    assert m["total_requests"] == 4 and m["served_meetings"] == 2 and m["scheduled_meetings"] == 3
    assert m["success_rate"] == 0.5
    assert m["avg_wait_min"] == 12.5 and m["median_wait_min"] == 12.5 and m["p90_wait_min"] == 18.5
    assert m["avg_wait_incl_unserved_min"] == pytest.approx((5 + 20 + 100) / 3, abs=0.01)   # unserved charged window
    assert m["faculty_idle_min"] == 50 - 25         # 60 posted - 10 class = 50 usable, 25 min held
    assert m["wasted_min"] == 10 and m["cancel_wasted_min"] == 10 and m["no_show_wasted_min"] == 0
    assert m["schedule_conflicts"] == 1             # the booking that overlaps the class (35-45 vs 30-40)
    assert m["cancellations"] == 1 and m["no_shows"] == 0
    assert m["fairness_jain"] == pytest.approx(1 / 3, abs=1e-4)    # served rates 1, 0, 0
    assert m["students_served"] == 1 and m["students_requesting"] == 3
    assert m["fairness_wait_jain"] == 1.0
    assert m["urgent_success_rate"] == 1.0 and m["peak_success_rate"] == 0.0


def test_double_booking_is_counted_only_when_active_at_the_same_time():
    w = mini_world([[0, 60]], [], [{}])

    def blk(s, e, booked, released):
        return {"request_id": 1, "student_id": 1, "faculty_id": 1, "start_min": s, "end_min": e,
                "booked_at_min": booked, "released_at_min": released, "kind": "served"}

    assert metrics.count_conflicts(w, [blk(0, 20, 0, 20), blk(10, 30, 5, 30)]) == 1       # true double booking
    assert metrics.count_conflicts(w, [blk(0, 20, 0, 3), blk(10, 30, 5, 30)]) == 0        # first one released


def test_jain_percentile_and_confidence_interval():
    assert metrics.jain_index([1, 1, 1, 1]) == 1.0
    assert metrics.jain_index([1, 0, 0, 0]) == 0.25
    assert metrics.jain_index([0, 0]) == 1.0
    assert metrics.jain_index([]) is None
    assert metrics.percentile([1, 2, 3, 4, 5], 90) == pytest.approx(4.6)
    assert metrics.percentile([], 50) is None
    ci = experiment.mean_ci([10, 12, 14])
    assert ci["mean"] == 12 and ci["n"] == 3 and ci["ci95"] == pytest.approx(4.303 * 2 / 3 ** 0.5, abs=1e-3)
    assert experiment.mean_ci([None, 5])["n"] == 1


# ------------------------------------------------------------------ experiment helpers

def test_compare_reports_direction_and_significance():
    per_seed = {"fcfs": [{"avg_wait_min": 100.0, "success_rate": 0.5} for _ in range(5)],
                "rule_based": [], "intelligent": [{"avg_wait_min": 90.0 + i, "success_rate": 0.6} for i in range(5)]}
    c = experiment.compare(per_seed, "intelligent", "fcfs")
    assert c["avg_wait_min"]["pct_improvement"] == pytest.approx(8.0)      # lower is better
    assert c["avg_wait_min"]["verdict"] == "better"
    assert c["success_rate"]["pct_improvement"] == pytest.approx(20.0)     # higher is better


def test_run_custom_is_fast_deterministic_and_complete():
    out = experiment.run_custom(2, "low", num_requests=60)
    out2 = experiment.run_custom(2, "low", num_requests=60)
    out.pop("elapsed_ms"), out2.pop("elapsed_ms")
    assert out == out2
    assert set(out["table"]) == set(experiment.METHOD_IDS) and out["seeds_run"] == 2 and not out["truncated"]
    assert len(out["timeline"]["faculty"]) == 4
    assert all(out["timeline"]["methods"][m] for m in experiment.METHOD_IDS)
    t = experiment.run_custom(30, "high", num_requests=600, time_budget_s=0.0)
    assert t["seeds_run"] == 1 and t["truncated"]


def test_csv_round_trip(tmp_path, world):
    p = tmp_path / "requests.csv"
    simulator.save_requests_csv(world, str(p))
    simulator.save_schedule_csv(world, str(tmp_path / "sched.csv"))
    loaded = simulator.load_requests_csv(str(p))
    keys = ("request_id", "student_id", "duration_min", "pref_to_min")
    assert [{k: r[k] for k in keys} for r in loaded] == [{k: r[k] for k in keys} for r in world["requests"]]
    assert core.ceil_grid(12, 5) == 15 and core.floor_grid(12, 5) == 10
