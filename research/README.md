# Scheduling Research — Documentation

Research question (PRD section 13):

> Can data-driven scheduling reduce student waiting time and improve faculty-student
> meeting efficiency compared with current/manual scheduling?

This experiment is **fully separate** from the live application: it never reads or
writes the `users`/`students`/`faculty`/`meeting_requests` tables. It generates its own
synthetic dataset and compares three scheduling *methods* against it. Live Campus
Connect meetings continue to be manually accepted/rejected/timed by faculty regardless
of anything in this folder.

## Dataset (`services/scheduling/simulator.py`)

Each synthetic request row has:

| Field | Meaning |
|---|---|
| `request_id` | unique id |
| `experiment_student_id` | synthetic student id (1..num_students), not a real account |
| `faculty_id` | synthetic faculty id (1..num_faculty) |
| `request_timestamp_min` | arrival time, minutes into the simulated day |
| `faculty_available_from_min` / `_to_min` | that faculty's simulated availability window for this request |
| `class_conflict` | 1 if this request collides with a simulated class period |
| `meeting_duration_min` | 10 / 15 / 20 / 30 |
| `peak_period` | 1 if the request arrived in one of two simulated rush windows |
| `cancellation` | 1 if this request is later cancelled |
| `no_show` | 1 if the student doesn't show (mutually exclusive with cancellation) |
| `priority` | 1 = normal, 2 = priority, 3 = urgent (weighted random, mostly normal) |

`generate_dataset(seed=...)` is deterministic for a given seed, so results are
reproducible. `run_experiment.py` persists the dataset to
`research/data/requests.csv` so the exact same input can be reused across runs.

## The Three Methods

### 1. FCFS (`fcfs.py`) — manual/current baseline
Processes requests strictly by arrival timestamp; assigns the earliest slot inside the
faculty's availability window and the faculty's already-booked time; **does not check
class conflicts** (mirrors how ad-hoc/manual scheduling actually behaves).

### 2. Rule-Based (`rule_based.py`)
Documented, deterministic rules applied in order: sort by priority then arrival time;
actively push a request's start past a known class conflict by
`CLASS_CONFLICT_BUFFER_MIN` (15 min) instead of ignoring it; respect availability and
existing bookings; otherwise leave unassigned.

### 3. Intelligent (`intelligent.py`) — transparent scoring, not deep learning
At each step, scores every still-feasible request for a faculty member and picks the
highest scorer next. Score is a weighted sum of four normalized (0..1) factors defined
in the module docstring and the `WEIGHTS` constant:

```
score = 0.35 * waiting_so_far + 0.30 * priority + 0.15 * (1 - peak_period) + 0.20 * fairness
```

- **waiting_so_far** — prevents starvation of a request that has waited a long time.
- **priority** — the request's own priority flag.
- **peak_penalty** — off-peak requests score slightly higher (less contention already).
- **fairness** — `1 / (1 + meetings already served to this student in this run)`, so a
  student who hasn't been served yet is preferred over one who has already had several
  meetings with that faculty.

The weights are a documented, tunable starting point (ESD section 26 requires the
formula be documented and re-evaluatable) — changing `WEIGHTS` in `intelligent.py` and
re-running `run_experiment.py` is the intended way to explore alternative weightings.

## Metrics (`metrics.py`) — identical definitions for all three methods

- `avg/min/max_waiting_time_min` — `assigned_start - request_timestamp`, assigned
  requests only.
- `success_rate` — `successful_meetings / total_requests`.
- `faculty_idle_time_min` — per-faculty declared availability window minus time
  actually booked, summed across faculty.
- `schedule_conflicts` — requests whose `class_conflict` flag was not avoided.
- `cancellations` / `no_shows` — carried through from the dataset unchanged.
- `fairness_stdev_of_student_avg_wait` — population stdev, across students, of each
  student's own average waiting time. Lower = more evenly distributed waiting.

## Running It

```bash
python research/run_experiment.py
```

Writes to `research/results/`: `comparison.md`, `comparison.json`,
`{fcfs,rule_based,intelligent}_assignments.csv`, and five PNG bar charts (waiting time,
success rate, faculty idle time, conflicts, fairness).

## Interpreting Results

With the default synthetic parameters (300 requests, 8 faculty, narrow availability
windows), demand exceeds supply, so success rates are intentionally low across all
three methods — this is realistic congestion, not a bug, and is exactly the regime
where scheduling method should matter most. Expect the rule-based and intelligent
methods to show far fewer schedule conflicts than FCFS (conflict avoidance), and the
intelligent method to generally serve more distinct students and reduce faculty idle
time, at some cost to raw average waiting time versus rule-based — a genuine tradeoff
worth discussing in a written report rather than a single "winner."
