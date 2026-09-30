"""Method 3: Transparent data-driven scoring scheduler (no deep learning).

For each faculty member, at every step we look at all not-yet-placed, feasible requests
and pick the highest-scoring one next (instead of pure arrival order). A request is
"feasible" only if its earliest possible start (respecting the faculty's availability
window and whatever is already booked) still ends before the window closes.

Score = weighted sum of four transparent, explainable factors, each normalized to 0..1:
  - waiting_so_far : requests that have already waited longer get boosted (prevents starvation)
  - priority       : the request's own priority flag (1/2/3 -> normal/priority/urgent)
  - peak_penalty   : slightly deprioritizes peak-period requests relative to off-peak,
                      since peak requests already contend for the same busy window
  - fairness       : boosts a request from a student who has received fewer meetings
                      so far in this run, so one student cannot dominate a faculty's day

WEIGHTS below are the tunable part of the formula — the ESD explicitly requires the
scoring approach to be documented (section 26) and re-evaluatable, so they are kept as
one clearly-named constant rather than buried in the loop.
"""

WEIGHTS = {
    "waiting_so_far": 0.35,
    "priority": 0.30,
    "peak_penalty": 0.15,
    "fairness": 0.20,
}

MAX_DURATION = 30  # matches simulator's max meeting_duration_min, used for normalization


def _score(r, now_min, served_count_by_student):
    waiting_so_far = max(0, now_min - r["request_timestamp_min"])
    waiting_norm = min(waiting_so_far / 120.0, 1.0)  # cap influence at 2 hours of waiting

    priority_norm = (r["priority"] - 1) / 2.0  # 1->0, 2->0.5, 3->1

    peak_norm = 1.0 - r["peak_period"]  # off-peak requests score higher (less contention)

    served = served_count_by_student.get(r["experiment_student_id"], 0)
    fairness_norm = 1.0 / (1.0 + served)  # first meeting for a student scores highest

    return (
        WEIGHTS["waiting_so_far"] * waiting_norm
        + WEIGHTS["priority"] * priority_norm
        + WEIGHTS["peak_penalty"] * peak_norm
        + WEIGHTS["fairness"] * fairness_norm
    )


def schedule(requests):
    by_faculty = {}
    for r in requests:
        by_faculty.setdefault(r["faculty_id"], []).append(r)

    results = []
    for fid, faculty_requests in by_faculty.items():
        results.extend(_schedule_faculty(faculty_requests))
    return results


def _schedule_faculty(faculty_requests):
    pending = []
    unassignable = []
    for r in faculty_requests:
        if r["cancellation"] or r["no_show"]:
            unassignable.append(_terminal_row(r))
        else:
            pending.append(r)

    served_count_by_student = {}
    busy_until = 0
    results = []

    while pending:
        now_min = max((r["request_timestamp_min"] for r in pending), default=0)
        best = None
        best_score = -1
        best_start = None
        best_end = None

        for r in pending:
            earliest_start = max(r["request_timestamp_min"], r["faculty_available_from_min"], busy_until)
            end_time = earliest_start + r["meeting_duration_min"]
            if end_time > r["faculty_available_to_min"]:
                continue  # infeasible right now; may still be scored on a later pass
            score = _score(r, now_min, served_count_by_student)
            if score > best_score:
                best, best_score, best_start, best_end = r, score, earliest_start, end_time

        if best is None:
            # nothing left is feasible against the current busy_until pointer
            for r in pending:
                results.append(_unassigned_row(r))
            break

        pending.remove(best)
        busy_until = best_end
        served_count_by_student[best["experiment_student_id"]] = (
            served_count_by_student.get(best["experiment_student_id"], 0) + 1
        )
        results.append({
            "request_id": best["request_id"],
            "faculty_id": best["faculty_id"],
            "assigned": True,
            "start_min": best_start,
            "end_min": best_end,
            "waiting_time_min": best_start - best["request_timestamp_min"],
            "conflict": False,
            "score": round(best_score, 4),
            "cancellation": False,
            "no_show": False,
            "experiment_student_id": best["experiment_student_id"],
        })

    return results + unassignable


def _unassigned_row(r):
    return {
        "request_id": r["request_id"], "faculty_id": r["faculty_id"], "assigned": False,
        "start_min": None, "end_min": None, "waiting_time_min": None,
        "conflict": bool(r["class_conflict"]), "cancellation": False, "no_show": False,
        "experiment_student_id": r["experiment_student_id"],
    }


def _terminal_row(r):
    return {
        "request_id": r["request_id"], "faculty_id": r["faculty_id"], "assigned": False,
        "start_min": None, "end_min": None, "waiting_time_min": None,
        "conflict": False, "cancellation": bool(r["cancellation"]), "no_show": bool(r["no_show"]),
        "experiment_student_id": r["experiment_student_id"],
    }
