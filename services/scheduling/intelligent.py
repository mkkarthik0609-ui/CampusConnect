"""Method 3 - the proposed intelligent scheduler: transparent scoring, no machine learning.

Same engine, same feasibility rules and same 15-minute batch rhythm as the rule-based method
(class timetable respected, no double booking, inside the student's window). What differs is HOW it
decides, in two small scoring steps plus one recovery step. All weights live in ``CONFIG`` below.

Step 1 - who goes first (request score, higher = earlier in the batch)::

    priority   urgent 1.0 / priority 0.5 / normal 0
  + fairness   aging: students with few past meetings and a long cumulative wait get a boost
               (0.6 / (1 + meetings_so_far) + 0.4 * min(1, cumulative_wait / 960 min))
  + slack      requests whose student window is tight (little room to move) go first
  + wait       how much of the student's window has already elapsed (used for the waiting list)
  - risk       estimated no-show / cancellation risk of this student (their history, smoothed)

Step 2 - where it goes (slot score, higher = better). For each gap in the faculty calendar the
earliest-fitting and the latest-fitting position inside the student's window are scored::

    - wait     later start = worse (the student waits longer)
  + pack       placing the meeting flush against a class, window edge or another meeting is good,
               and leaving an unusable sliver (< 10 min) is bad (idle-gap minimisation)
  - spread     hours of the day that are already heavily booked are avoided (peak-hour spreading)

Step 3 - recovery (back-fill). Requests that did not fit are kept on a waiting list while their window
is still open. When a cancellation frees a slot they are offered it (best request score first).
When a no-show is declared (5 min after the start) students who accepted "on-call" meetings are
seated in the freed time immediately.
"""
from services.scheduling import core

CONFIG = {
    "weights": {
        # step 1: request ordering
        "priority": 3.0,
        "fairness": 2.0,
        "slack": 1.0,
        "wait": 1.0,
        "risk": 1.0,
        # step 2: slot choice
        "slot_wait": 6.0,
        "pack": 1.0,
        "spread": 0.25,
    },
    "backfill": True,               # step 3: waiting list, cancellation and no-show back-fill
    "displace": True,               # urgent/priority requests may move a lower-priority booking
    "displace_min_notice_min": 120, # ...but only if that meeting is at least this far away
    "displace_max_delay_min": 120,  # ...and only if the moved student is delayed by at most this much
    "min_useful_fragment_min": 10,  # shorter leftovers cannot host any meeting
    "fairness_wait_cap_min": 960,
    "slack_scale_min": 720,
    "risk_prior": 0.12,             # prior failure rate and prior strength for the risk estimate
    "risk_prior_strength": 3,
}

PRIORITY_SCORE = {1: 0.0, 2: 0.5, 3: 1.0}


class IntelligentPolicy:
    name = "intelligent"
    immediate = False
    respects_classes = True

    def __init__(self, config=None):
        cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in CONFIG.items()}
        for k, v in (config or {}).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        self.cfg = cfg
        self.w = cfg["weights"]
        self.waitlist = {}          # faculty_id -> [request, ...]

    # -- step 1 ----------------------------------------------------------------------
    def request_score(self, eng, req, now):
        c, w = self.cfg, self.w
        st = eng.student(req["student_id"])
        fair = (0.6 / (1 + st.scheduled)
                + 0.4 * min(1.0, st.cum_wait / c["fairness_wait_cap_min"]))
        width = req["pref_to_min"] - req["pref_from_min"]
        slack = 1.0 - min(1.0, max(0, width - req["duration_min"]) / c["slack_scale_min"])
        span = max(1, req["pref_to_min"] - req["arrival_min"])
        aged = min(1.0, max(0, now - req["arrival_min"]) / span)
        risk = ((st.fails + c["risk_prior"] * c["risk_prior_strength"])
                / (st.booked + c["risk_prior_strength"]))
        return (w["priority"] * PRIORITY_SCORE[req["priority"]] + w["fairness"] * fair
                + w["slack"] * slack + w["wait"] * aged - w["risk"] * risk)

    def order(self, eng, batch, now):
        return sorted(batch, key=lambda r: (-self.request_score(eng, r, now), r["arrival_min"], r["request_id"]))

    # -- step 2 ----------------------------------------------------------------------
    def choose(self, eng, req, now, use_classes=True, exact_start=None):
        if exact_start is not None:
            return core.earliest_fit(eng, req, now, True, exact_start)
        c, w, g = self.cfg, self.w, eng.grid
        d = req["duration_min"]
        lo, hi = max(now, req["pref_from_min"]), req["pref_to_min"]
        cal = eng.cals[req["faculty_id"]]
        min_frag = c["min_useful_fragment_min"]
        best, best_key = None, None
        for gs, ge in cal.gaps(max(now, 0), eng.horizon, True):
            if ge <= lo or gs >= hi:
                continue
            first = core.ceil_grid(max(gs, lo), g)
            last = core.floor_grid(min(ge, hi) - d, g)
            if first > last:
                continue
            for s in {first, last}:
                left, right = s - gs, ge - (s + d)
                touching = (left == 0) + (right == 0)
                sliver = sum(f for f in (left, right) if 0 < f < min_frag)
                pack = touching / 2.0 - sliver / 20.0
                bucket = (s // 60) * 60
                load = cal.hour_load(bucket, bucket + 60)
                wait = min(2.0, (s - req["arrival_min"]) / eng.day_minutes)
                score = -w["slot_wait"] * wait + w["pack"] * pack - w["spread"] * load
                key = (-score, s)
                if best_key is None or key < best_key:
                    best, best_key = s, key
        return best

    # -- step 3 ----------------------------------------------------------------------
    def occupied_minutes(self, eng, req):
        return req["duration_min"]

    def displace(self, eng, req, now):
        """Re-optimisation: move ONE lower-priority booking to another slot so this request fits.
        Among the candidates the one whose move delays its student the least is chosen, and a move
        that would delay a student by more than ``displace_max_delay_min`` is never made."""
        cal = eng.cals[req["faculty_id"]]
        victims = [b for b in eng.blocks
                   if b["faculty_id"] == req["faculty_id"] and b["kind"] == "served"
                   and b["start_min"] >= now + self.cfg["displace_min_notice_min"]
                   and eng.reqs[b["request_id"]]["priority"] < req["priority"]
                   and b["start_min"] < req["pref_to_min"] and b["end_min"] > req["pref_from_min"]]
        best = None
        for blk in victims:
            vreq = eng.reqs[blk["request_id"]]
            cal.remove(blk["booking_id"])
            s = self.choose(eng, req, now)
            moved_to = None
            if s is not None:
                cal.add(-1, s, s + req["duration_min"])
                moved_to = self.choose(eng, vreq, now)
                cal.remove(-1)
            cal.add(blk["booking_id"], blk["start_min"], blk["end_min"])
            if s is None or moved_to is None:
                continue
            delay = moved_to - blk["start_min"]
            if delay > self.cfg["displace_max_delay_min"]:
                continue
            key = (delay, blk["request_id"])
            if best is None or key < best[0]:
                best = (key, blk, vreq, s, moved_to)
        if best is None:
            return False
        _, blk, vreq, s, moved_to = best
        eng.unbook(blk["booking_id"], now)
        eng.book(req, s, now)
        eng.book(vreq, moved_to, now, rebook=True)
        return True

    def on_reject(self, eng, req, now):
        if self.cfg["displace"] and req["priority"] >= 2 and self.displace(eng, req, now):
            return
        eng.reject(req)
        if self.cfg["backfill"] and req["pref_to_min"] - req["duration_min"] >= now:
            self.waitlist.setdefault(req["faculty_id"], []).append(req)

    def on_freed(self, eng, fid, now, kind, block):
        if not self.cfg["backfill"]:
            return
        wl = self.waitlist.get(fid)
        if not wl:
            return
        wl[:] = [r for r in wl if r["pref_to_min"] - r["duration_min"] >= now
                 and eng.assignments[r["request_id"]]["status"] == "unserved"]
        for req in sorted(wl, key=lambda r: (-self.request_score(eng, r, now), r["arrival_min"], r["request_id"])):
            if kind == "no_show":
                if not req["accepts_standby"]:
                    continue
                start = self.choose(eng, req, now, exact_start=core.ceil_grid(now, eng.grid))
            else:
                start = self.choose(eng, req, now)
            if start is not None:
                wl.remove(req)
                eng.book(req, start, now, backfill=True)


def schedule(world, config=None):
    return core.run(world, IntelligentPolicy(config))
