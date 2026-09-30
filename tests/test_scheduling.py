from services.scheduling import simulator, fcfs, rule_based, intelligent, metrics


def test_all_methods_use_same_dataset():
    rows = simulator.generate_dataset(num_requests=40, seed=1)
    for schedule_fn in (fcfs.schedule, rule_based.schedule, intelligent.schedule):
        results = schedule_fn(rows)
        assert len(results) == len(rows)
        assert {r["request_id"] for r in results} == {r["request_id"] for r in rows}


def test_metrics_are_consistent_shape():
    rows = simulator.generate_dataset(num_requests=40, seed=2)
    for schedule_fn in (fcfs.schedule, rule_based.schedule, intelligent.schedule):
        results = schedule_fn(rows)
        m = metrics.compute_metrics(results, rows)
        assert m["total_requests"] == 40
        assert 0 <= m["success_rate"] <= 1
        assert m["successful_meetings"] <= 40


def test_fcfs_processes_in_arrival_order():
    rows = simulator.generate_dataset(num_requests=20, seed=3)
    results = fcfs.schedule(rows)
    assigned = [r for r in results if r["assigned"]]
    # every assigned meeting must start no earlier than its own request time
    for r in assigned:
        original = next(x for x in rows if x["request_id"] == r["request_id"])
        assert r["start_min"] >= original["request_timestamp_min"]


def test_rule_based_avoids_more_conflicts_than_fcfs():
    rows = simulator.generate_dataset(num_requests=150, seed=4)
    fcfs_results = fcfs.schedule(rows)
    rb_results = rule_based.schedule(rows)
    fcfs_conflicts = sum(1 for r in fcfs_results if r["conflict"])
    rb_conflicts = sum(1 for r in rb_results if r["conflict"])
    assert rb_conflicts <= fcfs_conflicts


def test_intelligent_never_double_books_a_faculty():
    rows = simulator.generate_dataset(num_requests=80, seed=5)
    results = intelligent.schedule(rows)
    by_faculty = {}
    for r in results:
        if not r["assigned"]:
            continue
        by_faculty.setdefault(r["faculty_id"], []).append((r["start_min"], r["end_min"]))
    for fid, intervals in by_faculty.items():
        intervals.sort()
        for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]):
            assert e1 <= s2, f"overlap for faculty {fid}: {(s1, e1)} vs {(s2, e2)}"
