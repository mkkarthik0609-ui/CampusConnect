"""Method 1: First-Come-First-Served baseline (represents current/manual scheduling).

Rule: process requests strictly in arrival-timestamp order. Assign the earliest possible
start time within the faculty's declared availability window, without checking class
conflicts (FCFS does not look ahead) and without any priority/fairness logic.
"""


def schedule(requests):
    ordered = sorted(requests, key=lambda r: r["request_timestamp_min"])
    faculty_busy_until = {}
    results = []

    for r in ordered:
        fid = r["faculty_id"]
        earliest_start = max(
            r["request_timestamp_min"],
            r["faculty_available_from_min"],
            faculty_busy_until.get(fid, 0),
        )
        end_time = earliest_start + r["meeting_duration_min"]
        conflict = bool(r["class_conflict"])  # FCFS does not avoid it, only records it happened

        if end_time <= r["faculty_available_to_min"] and not r["cancellation"] and not r["no_show"]:
            assigned = True
            faculty_busy_until[fid] = end_time
            waiting_time = earliest_start - r["request_timestamp_min"]
        else:
            assigned = False
            waiting_time = None
            end_time = None

        results.append({
            "request_id": r["request_id"],
            "faculty_id": fid,
            "assigned": assigned,
            "start_min": earliest_start if assigned else None,
            "end_min": end_time,
            "waiting_time_min": waiting_time,
            "conflict": conflict,
            "cancellation": bool(r["cancellation"]),
            "no_show": bool(r["no_show"]),
            "experiment_student_id": r["experiment_student_id"],
        })
    return results
