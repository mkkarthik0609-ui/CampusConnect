"""Shared metric definitions applied identically to all three scheduling methods,
so results are directly comparable (ESD sections 27-28)."""

import statistics


def compute_metrics(results, requests):
    total = len(requests)
    assigned = [r for r in results if r["assigned"]]
    waiting_times = [r["waiting_time_min"] for r in assigned]
    cancellations = sum(1 for r in results if r.get("cancellation"))
    no_shows = sum(1 for r in results if r.get("no_show"))
    conflicts = sum(1 for r in results if r.get("conflict"))

    per_student = {}
    for r in results:
        sid = r["experiment_student_id"]
        per_student.setdefault(sid, {"served": 0, "waiting": []})
        if r["assigned"]:
            per_student[sid]["served"] += 1
            per_student[sid]["waiting"].append(r["waiting_time_min"])

    avg_wait_per_student = [
        statistics.mean(v["waiting"]) for v in per_student.values() if v["waiting"]
    ]

    faculty_idle = _faculty_idle_time(results, requests)

    return {
        "total_requests": total,
        "successful_meetings": len(assigned),
        "success_rate": round(len(assigned) / total, 4) if total else 0,
        "avg_waiting_time_min": round(statistics.mean(waiting_times), 2) if waiting_times else None,
        "min_waiting_time_min": min(waiting_times) if waiting_times else None,
        "max_waiting_time_min": max(waiting_times) if waiting_times else None,
        "schedule_conflicts": conflicts,
        "cancellations": cancellations,
        "no_shows": no_shows,
        "faculty_idle_time_min": faculty_idle,
        "fairness_stdev_of_student_avg_wait": (
            round(statistics.pstdev(avg_wait_per_student), 2) if len(avg_wait_per_student) > 1 else 0.0
        ),
        "students_served": sum(1 for v in per_student.values() if v["served"] > 0),
    }


def _faculty_idle_time(results, requests):
    """Sum, per faculty, of (declared availability window) - (time actually booked)."""
    windows = {}
    for r in requests:
        fid = r["faculty_id"]
        span = r["faculty_available_to_min"] - r["faculty_available_from_min"]
        windows[fid] = max(windows.get(fid, 0), span)

    booked = {}
    for r in results:
        if r["assigned"]:
            fid = r["faculty_id"]
            booked[fid] = booked.get(fid, 0) + (r["end_min"] - r["start_min"])

    idle_total = 0
    for fid, window in windows.items():
        idle_total += max(0, window - booked.get(fid, 0))
    return idle_total
