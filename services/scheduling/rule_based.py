"""Method 2: Rule-based scheduling.

Documented rules, applied in order for every request:
  1. Sort requests by priority (urgent first), then by arrival timestamp.
  2. Skip/reschedule around a known class conflict by pushing the start time forward
     by a fixed avoidance buffer (CLASS_CONFLICT_BUFFER_MIN) instead of ignoring it.
  3. Respect the faculty's declared availability window.
  4. Respect existing meetings already placed for that faculty (no overlap).
  5. Reject (leave unassigned) a request that cannot find a conflict-free slot inside
     the availability window.
Cancelled/no-show requests are recorded but never consume a slot.
"""

CLASS_CONFLICT_BUFFER_MIN = 15


def schedule(requests):
    ordered = sorted(requests, key=lambda r: (-r["priority"], r["request_timestamp_min"]))
    faculty_busy_until = {}
    results = []

    for r in ordered:
        fid = r["faculty_id"]
        if r["cancellation"] or r["no_show"]:
            results.append(_unassigned_row(r, conflict_avoided=False))
            continue

        earliest_start = max(
            r["request_timestamp_min"],
            r["faculty_available_from_min"],
            faculty_busy_until.get(fid, 0),
        )
        conflict_avoided = False
        if r["class_conflict"]:
            earliest_start += CLASS_CONFLICT_BUFFER_MIN
            conflict_avoided = True

        end_time = earliest_start + r["meeting_duration_min"]

        if end_time <= r["faculty_available_to_min"]:
            faculty_busy_until[fid] = end_time
            results.append({
                "request_id": r["request_id"],
                "faculty_id": fid,
                "assigned": True,
                "start_min": earliest_start,
                "end_min": end_time,
                "waiting_time_min": earliest_start - r["request_timestamp_min"],
                "conflict": False,  # rule-based actively avoided it
                "conflict_avoided": conflict_avoided,
                "cancellation": False,
                "no_show": False,
                "experiment_student_id": r["experiment_student_id"],
            })
        else:
            results.append(_unassigned_row(r, conflict_avoided))

    return results


def _unassigned_row(r, conflict_avoided):
    return {
        "request_id": r["request_id"],
        "faculty_id": r["faculty_id"],
        "assigned": False,
        "start_min": None,
        "end_min": None,
        "waiting_time_min": None,
        "conflict": bool(r["class_conflict"]) and not conflict_avoided,
        "conflict_avoided": conflict_avoided,
        "cancellation": bool(r["cancellation"]),
        "no_show": bool(r["no_show"]),
        "experiment_student_id": r["experiment_student_id"],
    }
