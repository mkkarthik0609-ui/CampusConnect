"""Method 1 - FCFS / manual scheduling (the baseline that represents today's practice).

How it behaves (and why it stands for the "manual" approach):

* faculty post FIXED slots (``manual_slot_min``, default 15 min) inside their availability windows,
  counted from the start of each window; a meeting occupies whole slots (a 10-minute chat uses one
  15-minute slot, a 30-minute meeting two);
* requests are handled the moment they arrive, strictly in arrival order, and the student gets the
  FIRST free posted slot that also lies inside the student's preferred window;
* nobody looks at the class timetable when booking. If the booked slot overlaps a class the clash is
  only found out later (``manual_collision_discovery``: when the student turns up, or when the
  faculty reviews the day); it is counted as a schedule conflict and the student is moved to the next
  free slot that does not clash (or ends up unserved if their window has closed);
* no priorities, no fairness, no waiting list: a slot freed by a cancellation or a no-show stays empty
  unless a later arrival happens to pick it.

It runs on the same engine and the same feasibility rules as the other two methods.
"""
import bisect
import math

from services.scheduling import core


class FCFSPolicy:
    name = "fcfs"
    immediate = True            # books on arrival, no batching
    respects_classes = False    # manual booking ignores the class timetable

    def __init__(self, slot_min=None):
        self._slot_override = slot_min
        self._starts = {}

    def slot(self, eng):
        return self._slot_override or eng.cfg.get("manual_slot_min", 15)

    def occupied_minutes(self, eng, req):
        slot = self.slot(eng)
        return math.ceil(req["duration_min"] / slot) * slot

    def order(self, eng, batch, now):
        return sorted(batch, key=lambda r: (r["arrival_min"], r["request_id"]))

    def choose(self, eng, req, now, use_classes=False, exact_start=None):
        """First free posted slot (aligned to the faculty's window start)."""
        fid = req["faculty_id"]
        cal = eng.cals[fid]
        slot = self.slot(eng)
        d, occ = req["duration_min"], self.occupied_minutes(eng, req)
        lo, hi = max(now, req["pref_from_min"]), req["pref_to_min"]
        starts = self._starts.get(fid)
        if starts is None:
            starts = self._starts[fid] = [w[0] for w in cal.raw]
        for gs, ge in cal.gaps(lo, eng.horizon, use_classes):
            if gs + d > hi:
                break
            ws = cal.raw[bisect.bisect_right(starts, gs) - 1][0]
            s = ws + math.ceil((gs - ws) / slot) * slot
            if s + occ <= ge and s + d <= hi:
                return s
        return None

    def on_reject(self, eng, req, now):
        eng.reject(req)

    def on_freed(self, eng, fid, now, kind, block):
        return None


def schedule(world, slot_min=None):
    return core.run(world, FCFSPolicy(slot_min))
