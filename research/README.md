# Scheduling research: data-driven vs manual meeting scheduling

> **Research question.** Can data-driven scheduling reduce student waiting time and improve faculty-student
> meeting efficiency compared with the current/manual scheduling approach?

One experiment, three methods, one simulated college week, 30 random weeks per load level. The research is
**fully separate from the live app**: nothing here reads or writes `users`, `students`, `faculty` or
`meeting_requests`. Live meetings are still accepted/rejected by faculty exactly as before. The admin API
(`/api/research/*`, see `docs/api/research.md`) only runs this simulation.

## Short answer (medium load, 360 requests/week, mean of 30 seeds)

| Metric | FCFS / manual | Rule-based | Intelligent | Intelligent vs FCFS | Intelligent vs rule-based |
|---|---|---|---|---|---|
| Average wait (min) | 299.2 | 270.3 | 275.2 | 8.0% lower | 1.8% **higher** |
| 90th percentile wait (min) | 604.0 | 555.7 | 565.7 | 6.3% lower | 1.8% **higher** |
| Meetings held / week | 204.7 | 230.7 | 234.1 | +14.4% | +1.5% |
| Faculty idle time (min / week) | 3598 | 3159 | 3107 | 13.7% lower | 1.7% lower |
| Wasted booked minutes | 369 | 375 | 332 | 10.1% lower | 11.6% lower |
| Schedule conflicts | 134.8 | 0 | 0 | eliminated | equal |
| Fairness (Jain, per-student served rate) | 0.697 | 0.753 | 0.762 | +9.4% | +1.2% |
| Urgent requests held | 31.4% | 41.4% | 46.3% | +14.9 pts | +4.9 pts |

All differences in the table are outside the 95% CI of the paired per-seed difference (full tables with
confidence intervals: `results/comparison.md`).

What this does and does not show, honestly:

* **Yes**: scheduling that knows the class timetable and uses flexible meeting lengths serves about 14% more
  meetings, removes class clashes, cuts waiting by about 8% and cuts faculty idle time, versus the manual
  baseline. The gain grows with load (high load: +19% meetings, 23% less idle time).
* **Most of that gain is not "intelligence"**. The rule-based method already captures nearly all of it. The
  scoring layer adds a further ~1.5% more meetings, ~12% fewer wasted slots, better fairness and clearly better
  handling of urgent requests.
* **Weakest metric for the intelligent method: average waiting time.** It is about 2% higher than rule-based
  (it recovers freed slots for students who had been waiting a long time and sometimes moves a normal booking
  for an urgent one, both of which add waiting among those served).
* The sensitivity table shows that the FCFS baseline's disadvantage depends on how "manual" is modelled: if the
  manual approach could book flexible 5-minute slots instead of fixed 15-minute slots, plain FCFS would have the
  *lowest* average wait (264 min) and 62.8% success, close to the rule-based/intelligent methods, while still
  producing ~135 class clashes a week. Read the result as "timetable awareness and flexible slots matter a
  lot; the smart scoring on top is a modest, explainable extra", not as "AI halves waiting times".

## Assumptions (all are in `DEFAULT_CONFIG` in `services/scheduling/simulator.py`)

* One week = 5 working days of 480 min (09:00-17:00); time is minutes from Monday 09:00 (nights not modelled).
* 12 faculty, 150 students. Each faculty member has 2-3 posted availability windows per day (45-120 min,
  no lunch hour) and 2-3 one-hour classes per day that BLOCK time; on average ~36% of posted time is taken by
  classes. Some faculty are far more in demand than others (rank^-0.6).
* Request volume per week: low 240, medium 360, high 480 (offered load 0.59 / 0.88 / 1.17 of usable faculty time).
  Arrivals: 60% of requests inside two daily rush windows (10:45-11:45 before lunch and 15:45-16:45), the rest
  uniform. A few students ask far more often than others (log-normal activity).
* Meeting length 10/15/20/30 min (25/35/25/15%). Priority normal/priority/urgent (75/18/7%).
* Each request has the student's preferred window (a hard constraint for every method: the student can only
  attend inside it; normal 6-24 h, priority 4-16 h, urgent 2-8 h of working time).
* Cancellation (before the meeting, 30-960 min notice) and no-show (slot wasted) depend on a hidden student type:
  85% reliable (6% cancel / 3% no-show), 15% flaky (14% / 20%). Half of the students accept an on-call
  "walk-in" slot when one frees up.
* The manual baseline posts fixed 15-minute slots (`manual_slot_min`) and notices a class clash only when the
  student turns up (`manual_collision_discovery`); both are tested in the sensitivity table.
* Everything is generated from `random.Random(f"campus-connect-scheduling/{seed}")`, so each seed is
  reproducible, and every method receives exactly the same request stream.
* The weights of the intelligent method were hand-tuned on seeds 1001-1020 (medium load). The reported seeds
  1-30 were never used for tuning.

## Data fields

`data/requests.csv` (sample week: seed 1, medium load) and `data/faculty_schedule.csv`.

| Field | Meaning |
|---|---|
| `request_id` | unique id, in arrival order |
| `student_id` / `faculty_id` | synthetic ids (not real accounts) |
| `arrival_min`, `day`, `arrival_clock` | when the request arrives (minutes from Monday 09:00) |
| `duration_min` | 10 / 15 / 20 / 30 |
| `priority`, `priority_label` | 1 normal, 2 priority, 3 urgent |
| `pref_from_min`, `pref_to_min` | the student's acceptable window for the meeting |
| `peak_period` | 1 if the request arrived in a rush window |
| `will_cancel`, `cancel_notice_min` | student cancels this long before the meeting (only if booked) |
| `will_no_show` | student does not turn up (only if booked; exclusive with `will_cancel`) |
| `accepts_standby` | student accepts an on-call walk-in slot |
| faculty_schedule: `kind` = `availability` / `class`, `day`, `start_min`, `end_min`, clock strings | posted windows and the class timetable |

## The three methods (all run on the same engine, `services/scheduling/core.py`)

**1. FCFS / manual (`fcfs.py`).** Faculty post fixed 15-minute slots; a meeting takes whole slots. Requests are
handled on arrival, in arrival order, and get the first free posted slot inside the student's window. The class
timetable is not consulted: a booking that overlaps a class is discovered when the student turns up, counted as a
schedule conflict, and the student is moved to the next free slot without a clash (or ends up unserved). No
priority, no fairness, no waiting list; freed slots stay empty unless a later arrival picks them.

**2. Rule-based (`rule_based.py`).** Every 15 minutes it handles the new requests: sort by priority (then
arrival), give each the earliest slot that is inside a posted window, does not overlap a class or another meeting
and lies in the student's window. Otherwise decline. No waiting list.

**3. Intelligent (`intelligent.py`) - transparent scoring, no machine learning.** Same feasibility rules and batch
rhythm as rule-based. Weights are in one dict, `CONFIG["weights"]`:
*Who first* = priority + fairness aging (few past meetings, long accumulated wait) + window slack (tight windows
first) + elapsed share of the window - estimated no-show risk (the student's own cancel/no-show history, smoothed).
*Where* = the earliest and latest fitting position in each gap, scored by `-wait + packing (flush against a
class/window/meeting, no unusable sliver under 10 min) - peak-hour spreading (avoid hours that are already
busy)`. *Recovery*: requests that did not fit go to a waiting list; a cancellation offers the freed slot to the
best-scoring waiting student, a no-show (declared 5 min after the start) seats an on-call student immediately;
an urgent/priority request that finds no slot may move one lower-priority booking (at least 2 h away) to another
slot if that delays the moved student by at most 2 h.

The ablation table in `results/comparison.md` shows which parts matter at default load: back-fill (+0.9 points
success, fewer wasted minutes) and urgent displacement (urgent requests held) have a measurable effect;
fairness aging improves the Jain index slightly; **packing, peak spreading, slack and the risk term have no
measurable effect in this setting** and are kept as documented, low-weight tie-breakers.

## Metric definitions (`metrics.py`, identical for all methods)

* **Waiting time** = start of the meeting that took place minus request arrival; average, median and p90 over
  served requests. `avg_wait_incl_unserved_min` charges unserved requests their full window so that refusing hard
  requests cannot look like short waits.
* **Meetings held / success rate** = meetings that took place / requests. `scheduled_meetings` = requests that got a
  conflict-free booking (held + cancelled + no-show).
* **Faculty idle time** = usable availability (posted windows minus classes) minus minutes spent in meetings that
  took place (empty gaps plus wasted slots). `utilization` = held minutes / usable minutes.
* **Wasted minutes** = booked minutes that hosted no meeting (cancelled or no-show slots nobody refilled).
* **Schedule conflicts** = bookings that overlap a class of that faculty member, plus bookings of one faculty
  member that were active at the same time and overlap (double booking).
* **Cancellations / no-shows** = counted over booked requests (so they differ slightly between methods that book
  different numbers of requests); reported, not scored as better/worse.
* **Fairness** = Jain's index (sum x)^2 / (n * sum x^2) of the per-student served rate (served / requests made) over
  all students who asked; 1 = equal. `fairness_wait_jain` is the same index over each served student's mean wait.
  `students_served` = students with at least one meeting held.

## How to run

```
venv\Scripts\python.exe research\run_experiment.py            # full study, about 20-40 s
venv\Scripts\python.exe research\run_experiment.py --seeds 5 --no-ablation   # quick look
venv\Scripts\python.exe -m pytest tests\test_scheduling.py tests\test_research_api.py -q
```

Outputs: `results/results.json` (everything, machine readable, includes the config), `results/comparison.md`
(tables with mean +/- 95% CI, `% vs FCFS`, `% vs Rule`, five-line conclusion, ablation, sensitivity),
`results/{fcfs,rule_based,intelligent}_assignments.csv` (one sample run each), `data/requests.csv`,
`data/faculty_schedule.csv`, and (if matplotlib is installed: `pip install -r requirements-research.txt`)
`results/chart_*.png` for waiting time, success rate, idle time, conflicts and fairness. The generated files are
small and committed. The reusable logic is `services/scheduling/experiment.py`.

## Limitations

* **Synthetic data.** Every distribution above is an assumption, not a measurement of this college. The
  conclusions hold for this model; real data (request logs, class timetables, real no-show rates) is needed
  before claiming a real-world effect size.
* **Single-college scale** (12 faculty, 150 students, one week, students fixed to one faculty member each).
  Students never switch faculty or relax their window; requests cannot be re-submitted.
* **The manual baseline is a modelling choice** (fixed 15-minute slots, clash found at meeting time). The
  sensitivity table shows how much the headline gain depends on it.
* **No behavioural feedback**: waiting longer does not make students cancel more; offering a worse slot is not
  modelled; the intelligent method never changes a confirmed slot except for the urgent displacement rule.
* The intelligent method's weights were tuned on the same synthetic generator, which favours it somewhat; the
  rule-based method is the fairer yardstick for "what does the scoring add".
* Fairness is measured per student served-rate; it does not account for need or priority.
