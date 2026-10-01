"""Shared event-driven scheduling engine.

All three methods (FCFS / rule-based / intelligent) run on THIS engine, against the same world, with
the same feasibility checks. A method is only a small *policy* object that answers:

* ``order(batch)``      in which order to handle the requests collected since the last run
* ``choose(req, now)``  which start time to give one request (or None = no slot)
* ``on_reject``/``on_freed``  what to do when nothing fits / when a cancellation or no-show frees time

The engine itself owns the facts: faculty calendars, cancellations, no-shows, collisions with the
class timetable, and the records that ``metrics.compute_metrics`` later scores. Metrics are therefore
identical for every method by construction.

Result of ``run(world, policy)``::

    {"method": str,
     "assignments": [one record per request: status served|cancelled|no_show|unserved, start/end/wait ...],
     "blocks": [every booking ever made: kind served|cancelled|no_show|conflict, booked/released times]}
"""
import bisect
import heapq

from services.scheduling import simulator

EV_FREE, EV_REBOOK, EV_ARRIVE, EV_EPOCH = 0, 1, 2, 3


def ceil_grid(x, g):
    return -(-int(x) // g) * g


def floor_grid(x, g):
    return (int(x) // g) * g


class Calendar:
    """One faculty member's posted windows, class blocks and current bookings."""

    def __init__(self, faculty):
        self.fid = faculty["faculty_id"]
        self.raw = sorted(tuple(w[:2]) for w in faculty["windows"])
        self.classes = sorted(tuple(c[:2]) for c in faculty["classes"])
        self.eff = simulator.effective_windows(faculty)
        self._starts = []
        self._ends = []
        self._ids = []

    # bookings never overlap each other, so the three parallel lists stay sorted together
    def add(self, bid, s, e):
        i = bisect.bisect_left(self._starts, s)
        self._starts.insert(i, s)
        self._ends.insert(i, e)
        self._ids.insert(i, bid)

    def remove(self, bid):
        i = self._ids.index(bid)
        del self._starts[i], self._ends[i], self._ids[i]

    def collides_with_class(self, s, e):
        return any(cs < e and s < ce for cs, ce in self.classes)

    def gaps(self, lo, hi, use_classes):
        """Free intervals in [lo, hi) inside the posted windows (minus classes if ``use_classes``)."""
        out = []
        base = self.eff if use_classes else self.raw
        n = len(self._ids)
        for ws, we in base:
            if we <= lo or ws >= hi:
                continue
            cur, end = max(ws, lo), min(we, hi)
            i = bisect.bisect_right(self._ends, cur)
            while i < n and self._starts[i] < end:
                if self._starts[i] > cur:
                    out.append((cur, self._starts[i]))
                cur = max(cur, self._ends[i])
                i += 1
            if cur < end:
                out.append((cur, end))
        return out

    def is_free(self, s, e, use_classes):
        g = self.gaps(s, e, use_classes)
        return len(g) == 1 and g[0] == (s, e)

    def hour_load(self, bucket_start, bucket_end):
        """Booked share of this faculty's usable time in [bucket_start, bucket_end)."""
        usable = sum(max(0, min(e, bucket_end) - max(s, bucket_start)) for s, e in self.eff)
        if usable <= 0:
            return 1.0
        booked = sum(max(0, min(e, bucket_end) - max(s, bucket_start))
                     for s, e in zip(self._starts, self._ends))
        return min(1.0, booked / usable)


def earliest_fit(eng, req, now, use_classes, exact_start=None):
    """First start (on the grid) inside the student's window where the meeting fits, or None."""
    d, g = req["duration_min"], eng.grid
    lo, hi = max(now, req["pref_from_min"]), req["pref_to_min"]
    cal = eng.cals[req["faculty_id"]]
    if exact_start is not None:
        s = exact_start
        return s if lo <= s and s + d <= hi and cal.is_free(s, s + d, use_classes) else None
    for gs, ge in cal.gaps(lo, hi, use_classes):
        s = ceil_grid(gs, g)
        if s + d <= ge:
            return s
    return None


class _Student:
    __slots__ = ("scheduled", "rejected", "cum_wait", "fails", "booked")

    def __init__(self):
        self.scheduled = 0     # requests the scheduler has found a slot for
        self.rejected = 0      # requests it could not place
        self.cum_wait = 0      # minutes waited (served) or given up (rejected)
        self.fails = 0         # cancellations + no-shows observed so far
        self.booked = 0        # bookings made (denominator for the risk estimate)


class Engine:
    def __init__(self, world, policy):
        cfg = world["config"]
        self.world, self.policy, self.cfg = world, policy, cfg
        self.grid = cfg["grid_min"]
        self.epoch = cfg["batch_interval_min"]
        self.grace = cfg["no_show_grace_min"]
        self.day_minutes = cfg["day_minutes"]
        self.horizon = simulator.horizon(cfg)
        self.cals = {f["faculty_id"]: Calendar(f) for f in world["faculty"]}
        self.reqs = {r["request_id"]: r for r in world["requests"]}
        self.students = {}
        self.assignments = {
            r["request_id"]: {
                "request_id": r["request_id"], "student_id": r["student_id"], "faculty_id": r["faculty_id"],
                "priority": r["priority"], "peak_period": r["peak_period"], "arrival_min": r["arrival_min"],
                "duration_min": r["duration_min"], "pref_to_min": r["pref_to_min"], "status": "unserved",
                "start_min": None, "end_min": None, "wait_min": None, "booked_at_min": None,
                "collisions": 0, "rebooked": 0, "backfilled": 0, "_rejected_counted": False,
            } for r in world["requests"]
        }
        self.bookings = {}
        self.blocks = []
        self._heap = []
        self._seq = 0
        self._pending = []
        self._epochs = set()

    # -- helpers ---------------------------------------------------------------------
    def student(self, sid):
        st = self.students.get(sid)
        if st is None:
            st = self.students[sid] = _Student()
        return st

    def push(self, t, prio, payload):
        self._seq += 1
        heapq.heappush(self._heap, (t, prio, self._seq, payload))

    def day_start(self, minute):
        return (minute // self.day_minutes) * self.day_minutes

    # -- booking ---------------------------------------------------------------------
    def book(self, req, start, now, backfill=False, rebook=False):
        d, fid = req["duration_min"], req["faculty_id"]
        end = start + self.policy.occupied_minutes(self, req)   # time the calendar is blocked
        cal = self.cals[fid]
        bid = len(self.bookings) + 1
        cal.add(bid, start, end)
        block = {"booking_id": bid, "request_id": req["request_id"], "student_id": req["student_id"],
                 "faculty_id": fid, "start_min": start, "end_min": end, "meeting_min": d, "kind": "served",
                 "booked_at_min": now, "released_at_min": end, "backfill": int(backfill),
                 "rebooked": int(rebook)}
        self.bookings[bid] = block
        self.blocks.append(block)

        rec = self.assignments[req["request_id"]]
        st = self.student(req["student_id"])
        st.booked += 1
        if rec["_rejected_counted"]:          # it had been counted as rejected while on the waiting list
            st.rejected -= 1
            st.cum_wait -= req["pref_to_min"] - req["arrival_min"]
            rec["_rejected_counted"] = False

        if not self.policy.respects_classes and cal.collides_with_class(start, end):
            # Manual booking ignored the class timetable; the clash is found out later (see config).
            block["kind"] = "conflict"
            if self.cfg.get("manual_collision_discovery", "meeting_start") == "day_start":
                disc = max(now, self.day_start(start))
            else:
                disc = start          # found out when the student turns up and the faculty is teaching
            block["released_at_min"] = disc
            rec.update(status="unserved", start_min=None, end_min=None, wait_min=None)
            self.push(disc, EV_REBOOK, bid)
            return

        wait = start - req["arrival_min"]
        rec.update(status="served", start_min=start, end_min=start + d, wait_min=wait, booked_at_min=now,
                   rebooked=int(rebook or rec["rebooked"]), backfilled=int(backfill))
        st.scheduled += 1
        st.cum_wait += wait
        if req["will_cancel"]:
            t = max(now, min(start - req["cancel_notice_min"], start - 1))
            self.push(t, EV_FREE, ("cancelled", bid))
        elif req["will_no_show"]:
            self.push(start + self.grace, EV_FREE, ("no_show", bid))

    def unbook(self, bid, now):
        """Take a confirmed booking back (used when a more urgent request displaces it)."""
        blk = self.bookings[bid]
        blk["kind"] = "moved"
        blk["released_at_min"] = now
        self.cals[blk["faculty_id"]].remove(bid)
        rec = self.assignments[blk["request_id"]]
        st = self.student(blk["student_id"])
        st.scheduled -= 1
        st.booked -= 1
        st.cum_wait -= rec["wait_min"]
        rec.update(status="unserved", start_min=None, end_min=None, wait_min=None)

    def reject(self, req):
        """Count a request the scheduler could not place (fairness bookkeeping)."""
        rec = self.assignments[req["request_id"]]
        if not rec["_rejected_counted"]:
            rec["_rejected_counted"] = True
            st = self.student(req["student_id"])
            st.rejected += 1
            st.cum_wait += req["pref_to_min"] - req["arrival_min"]

    # -- event handlers --------------------------------------------------------------
    def _place(self, req, now):
        start = self.policy.choose(self, req, now, use_classes=self.policy.respects_classes)
        if start is None:
            self.policy.on_reject(self, req, now)
        else:
            self.book(req, start, now)

    def _release(self, bid, now, kind):
        blk = self.bookings[bid]
        if blk["kind"] != "served":       # stale event
            return None
        blk["kind"] = kind
        blk["released_at_min"] = now
        self.cals[blk["faculty_id"]].remove(bid)
        rec = self.assignments[blk["request_id"]]
        rec.update(status=kind, wait_min=None)
        st = self.student(blk["student_id"])
        st.fails += 1
        st.scheduled -= 1
        return blk

    def _rebook(self, bid, now):
        blk = self.bookings[bid]
        if blk["kind"] != "conflict":
            return
        self.cals[blk["faculty_id"]].remove(bid)
        req = self.reqs[blk["request_id"]]
        self.assignments[req["request_id"]]["collisions"] += 1
        start = self.policy.choose(self, req, now, use_classes=True)
        if start is None:
            self.reject(req)
        else:
            self.book(req, start, now, rebook=True)

    def run(self):
        for r in self.world["requests"]:
            self.push(r["arrival_min"], EV_ARRIVE, r["request_id"])
        while self._heap:
            t, prio, _, payload = heapq.heappop(self._heap)
            if prio == EV_FREE:
                kind, bid = payload
                blk = self._release(bid, t, kind)
                if blk is not None:
                    self.policy.on_freed(self, blk["faculty_id"], t, kind, blk)
            elif prio == EV_REBOOK:
                self._rebook(payload, t)
            elif prio == EV_ARRIVE:
                req = self.reqs[payload]
                if self.policy.immediate:
                    self._place(req, t)
                else:
                    self._pending.append(req)
                    te = ceil_grid(t, self.epoch)
                    if te not in self._epochs:
                        self._epochs.add(te)
                        self.push(te, EV_EPOCH, te)
            else:  # EV_EPOCH
                batch, self._pending = self._pending, []
                for req in self.policy.order(self, batch, t):
                    self._place(req, t)
        return self._result()

    def _result(self):
        assignments = []
        for rid in sorted(self.assignments):
            rec = {k: v for k, v in self.assignments[rid].items() if not k.startswith("_")}
            assignments.append(rec)
        blocks = [{k: v for k, v in b.items() if k != "booking_id"}
                  for b in sorted(self.blocks, key=lambda b: (b["faculty_id"], b["start_min"], b["booked_at_min"]))]
        return {"method": self.policy.name, "assignments": assignments, "blocks": blocks}


def run(world, policy):
    """Run one policy over a world. The world is never modified."""
    return Engine(world, policy).run()
