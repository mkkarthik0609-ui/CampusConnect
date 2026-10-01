"""Method 2 - rule-based scheduling (fixed, hand-written rules; no scoring, no learning).

Every 15 minutes (``batch_interval_min``) the scheduler handles the requests that arrived since the
last run, applying these rules in order:

1. Sort the batch by priority (urgent, then priority, then normal); ties by arrival time.
2. For each request take the EARLIEST slot that is inside one of the faculty's availability
   windows, does NOT overlap a class (the class timetable is respected), does not overlap another
   meeting, and lies inside the student's preferred window (earliest-fit).
3. If nothing fits the request is declined. There is no waiting list: slots freed by a cancellation or
   a no-show stay empty unless a later request happens to pick them.
"""
from services.scheduling import core


class RuleBasedPolicy:
    name = "rule_based"
    immediate = False
    respects_classes = True

    def order(self, eng, batch, now):
        return sorted(batch, key=lambda r: (-r["priority"], r["arrival_min"], r["request_id"]))

    def choose(self, eng, req, now, use_classes=True, exact_start=None):
        return core.earliest_fit(eng, req, now, True, exact_start)

    def occupied_minutes(self, eng, req):
        return req["duration_min"]

    def on_reject(self, eng, req, now):
        eng.reject(req)

    def on_freed(self, eng, fid, now, kind, block):
        return None


def schedule(world):
    return core.run(world, RuleBasedPolicy())
