"""Metric definitions, applied identically to all three scheduling methods.

``compute_metrics(world, result)`` scores one run. ``result`` is what ``core.run`` returns:
``assignments`` (one record per request) and ``blocks`` (every booking ever made, including bookings
that were later cancelled, never attended, or found to collide with a class).

Definitions (all times in minutes, one simulated week, all faculty together):

* waiting time        start of the meeting that actually took place minus the request's arrival;
                      avg / median / p90 over SERVED requests only (``avg_wait_incl_unserved_min``
                      charges a request nobody served its whole window, so a method cannot look good
                      on waiting time just by refusing the hard requests).
* served_meetings     meetings that took place (status "served"); success_rate = served / requests.
* scheduled_meetings  requests that got a conflict-free booking (served + cancelled + no-show).
* faculty_idle_min    usable availability (posted windows minus class blocks) minus minutes spent in
                      meetings that took place; it contains empty gaps and wasted slots.
* wasted_min          booked minutes that hosted no meeting: cancelled slots nobody refilled plus
                      no-show slots nobody refilled (a subset of the idle time).
* schedule_conflicts  bookings that overlap a class block of that faculty member, plus pairs of
                      bookings of one faculty member that were active at the same time and overlap.
* cancellations / no_shows   counted over booked requests (a request nobody booked cannot cancel).
* fairness_jain       Jain's index, (sum x)^2 / (n * sum x^2), of the per-student served-rate
                      (served requests / requests made) over all students who asked for a meeting.
                      1.0 = everyone got the same share, 1/n = one student got everything.
* fairness_wait_jain  the same index over each served student's mean waiting time.
* students_served     distinct students with at least one meeting that took place.
"""
import statistics

from services.scheduling import simulator


def jain_index(values):
    vals = [float(v) for v in values]
    if not vals:
        return None
    sq = sum(v * v for v in vals)
    if sq == 0:
        return 1.0        # everybody got exactly the same (nothing)
    return round(sum(vals) ** 2 / (len(vals) * sq), 4)


def percentile(values, q):
    """Linear-interpolation percentile (q in 0..100), same as numpy's default."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _r(x, nd=2):
    return None if x is None else round(x, nd)


def _overlap(a_s, a_e, b_s, b_e):
    return max(0, min(a_e, b_e) - max(a_s, b_s))


def count_conflicts(world, blocks):
    classes = {f["faculty_id"]: [tuple(c[:2]) for c in f["classes"]] for f in world["faculty"]}
    by_fac = {}
    n = 0
    for b in blocks:
        if any(_overlap(b["start_min"], b["end_min"], cs, ce) > 0 for cs, ce in classes[b["faculty_id"]]):
            n += 1
        by_fac.setdefault(b["faculty_id"], []).append(b)
    for items in by_fac.values():
        items.sort(key=lambda b: b["start_min"])
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if b["start_min"] >= a["end_min"]:
                    break
                # same space; only a double booking if both bookings were active at the same time
                if max(a["booked_at_min"], b["booked_at_min"]) < min(a["released_at_min"], b["released_at_min"]):
                    n += 1
    return n


def compute_metrics(world, result):
    reqs = {r["request_id"]: r for r in world["requests"]}
    recs = result["assignments"]
    blocks = result["blocks"]
    total = len(recs)

    served = [r for r in recs if r["status"] == "served"]
    waits = [r["wait_min"] for r in served]
    unserved = [r for r in recs if r["status"] == "unserved"]
    cancelled = [r for r in recs if r["status"] == "cancelled"]
    no_shows = [r for r in recs if r["status"] == "no_show"]

    censored = waits + [reqs[r["request_id"]]["pref_to_min"] - r["arrival_min"] for r in unserved]

    # faculty time
    usable = 0
    for f in world["faculty"]:
        usable += sum(e - s for s, e in simulator.effective_windows(f))
    served_min = sum(r["duration_min"] for r in served)
    served_blocks = {}
    for b in blocks:
        if b["kind"] == "served":
            served_blocks.setdefault(b["faculty_id"], []).append(b)
    wasted = {"cancelled": 0, "no_show": 0}
    for b in blocks:
        if b["kind"] in wasted:
            covered = sum(_overlap(b["start_min"], b["end_min"], s["start_min"], s["end_min"])
                          for s in served_blocks.get(b["faculty_id"], []))
            wasted[b["kind"]] += (b["end_min"] - b["start_min"]) - covered

    # fairness
    per_student = {}
    for r in recs:
        d = per_student.setdefault(r["student_id"], {"n": 0, "served": 0, "waits": []})
        d["n"] += 1
        if r["status"] == "served":
            d["served"] += 1
            d["waits"].append(r["wait_min"])
    rates = [d["served"] / d["n"] for d in per_student.values()]
    mean_waits = [statistics.mean(d["waits"]) for d in per_student.values() if d["waits"]]

    def subset(pred):
        sub = [r for r in recs if pred(r)]
        ok = [r for r in sub if r["status"] == "served"]
        return (len(ok) / len(sub) if sub else None,
                statistics.mean(r["wait_min"] for r in ok) if ok else None)

    urgent_rate, urgent_wait = subset(lambda r: r["priority"] == 3)
    peak_rate, peak_wait = subset(lambda r: r["peak_period"] == 1)

    return {
        "total_requests": total,
        "served_meetings": len(served),
        "scheduled_meetings": total - len(unserved),
        "success_rate": _r(len(served) / total, 4) if total else 0.0,
        "avg_wait_min": _r(statistics.mean(waits)) if waits else None,
        "median_wait_min": _r(statistics.median(waits)) if waits else None,
        "p90_wait_min": _r(percentile(waits, 90)) if waits else None,
        "avg_wait_incl_unserved_min": _r(statistics.mean(censored)) if censored else None,
        "faculty_idle_min": usable - served_min,
        "utilization": _r(served_min / usable, 4) if usable else None,
        "wasted_min": wasted["cancelled"] + wasted["no_show"],
        "schedule_conflicts": count_conflicts(world, blocks),
        "cancellations": len(cancelled),
        "cancel_wasted_min": wasted["cancelled"],
        "no_shows": len(no_shows),
        "no_show_wasted_min": wasted["no_show"],
        "fairness_jain": jain_index(rates),
        "fairness_wait_jain": jain_index(mean_waits),
        "students_served": sum(1 for d in per_student.values() if d["served"] > 0),
        "students_requesting": len(per_student),
        "urgent_success_rate": _r(urgent_rate, 4),
        "urgent_avg_wait_min": _r(urgent_wait),
        "peak_success_rate": _r(peak_rate, 4),
        "peak_avg_wait_min": _r(peak_wait),
        "backfilled_meetings": sum(1 for r in served if r["backfilled"]),
        "collisions_rebooked": sum(r["collisions"] for r in recs),
    }
