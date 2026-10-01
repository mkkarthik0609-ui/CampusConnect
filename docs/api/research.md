# Research API - scheduling experiment (`/api/research`)

Admin-only, read-only with respect to live data: it runs a **synthetic** simulation (`services/scheduling`) and
never touches users, students, faculty or meetings. Conventions: `docs/api/CONVENTIONS.md`.
Router: `api/routers/research.py` (auto-registered).

Research question: *can data-driven scheduling reduce student waiting time and improve faculty-student meeting
efficiency compared with the current/manual scheduling approach?* Method ids used everywhere:
`fcfs` (FCFS / manual), `rule_based` (Rule-based), `intelligent` (Intelligent, proposed).

Auth: signed-in `ADMIN` only. Not signed in -> 401 `unauthenticated`; any other role -> 403 `forbidden`.
`POST` needs the usual `X-CSRFToken` header.

All times are integer **minutes from the start of the simulated week**: day `d` covers
`[d*480, (d+1)*480)` and minute 0 is Monday 09:00 (`time_axis` in responses says so). A "table cell" is
`{"mean": 0.65, "sd": 0.04, "ci95": 0.009, "n": 30}` (`ci95` = half-width of the 95% Student-t interval; `sd`/`ci95`
are `null` when `n` is 1).

---

## GET /api/research/results

Returns the committed full study (`research/results/results.json`: 30 seeds x low/medium/high load). If that file is
missing it is computed on the fly with 5 seeds and no ablation, and `"generated_on_the_fly": true` is added.

Response 200 (abbreviated; the real file also contains every metric in `metrics`, all three load levels, the
`ablation`, `sensitivity` and `sample_run` blocks):

```json
{
  "question": "Can data-driven scheduling reduce student waiting time ...?",
  "config": {
    "world": {"days": 5, "day_minutes": 480, "num_faculty": 12, "num_students": 150,
              "loads": {"low": 240, "medium": 360, "high": 480}, "...": "..."},
    "intelligent": {"weights": {"priority": 3.0, "fairness": 2.0, "slack": 1.0, "wait": 1.0, "risk": 1.0,
                                "slot_wait": 6.0, "pack": 1.0, "spread": 0.25},
                    "backfill": true, "displace": true, "...": "..."},
    "eval_seeds": [1, 2, "...", 30],
    "tuning_seeds": [1001, 1020]
  },
  "methods": {
    "fcfs": {"label": "FCFS / manual", "description": "..."},
    "rule_based": {"label": "Rule-based", "description": "..."},
    "intelligent": {"label": "Intelligent (proposed)", "description": "..."}
  },
  "metrics": {
    "avg_wait_min": {"label": "Average waiting time", "unit": "min", "better": "lower", "headline": true},
    "success_rate": {"label": "Success rate (held / requested)", "unit": "fraction", "better": "higher", "headline": true}
  },
  "levels": {
    "medium": {
      "num_requests": 360,
      "dataset": {"requests": 360, "students_requesting": 112.2, "rush_share": 0.7, "offered_load": 0.88, "...": "..."},
      "table": {
        "fcfs":        {"avg_wait_min": {"mean": 299.165, "sd": 25.1, "ci95": 9.4, "n": 30}, "success_rate": {"mean": 0.5685, "sd": 0.0266, "ci95": 0.0099, "n": 30}},
        "rule_based":  {"avg_wait_min": {"mean": 270.286, "sd": 24.0, "ci95": 9.0, "n": 30}, "success_rate": {"mean": 0.641, "sd": 0.027, "ci95": 0.01, "n": 30}},
        "intelligent": {"avg_wait_min": {"mean": 275.215, "sd": 23.1, "ci95": 8.6, "n": 30}, "success_rate": {"mean": 0.6504, "sd": 0.025, "ci95": 0.009, "n": 30}}
      },
      "improvement": {
        "intelligent_vs_fcfs": {
          "success_rate": {"candidate_mean": 0.6504, "baseline_mean": 0.5685, "pct_improvement": 14.4,
                           "paired_diff_mean": 0.0819, "paired_diff_ci95": 0.0066, "verdict": "better"}
        },
        "intelligent_vs_rule_based": {"...": "..."},
        "rule_based_vs_fcfs": {"...": "..."}
      },
      "conclusions": ["Waiting time: ...", "Meetings held: ...", "Faculty time: ...", "Fairness (Jain): ...", "Weakest metric ..."],
      "weakest_metric": {"metric": "avg_wait_min", "pct_improvement": -1.8, "verdict": "worse"}
    },
    "low": {"...": "..."},
    "high": {"...": "..."}
  },
  "ablation": {"load": "medium", "seeds": [1, "..."], "variants": {"full": {"avg_wait_min": {"mean": 275.2, "sd": 0, "ci95": 0, "n": 30}}, "no_backfill": {"...": "..."}}},
  "sensitivity": {"load": "medium", "variants": {"fcfs_default (15-min slots, clash found at meeting)": {"...": "..."}}},
  "conclusions": ["... the medium-load conclusions, 5 lines ..."],
  "sample_run": {"seed": 1, "load": "medium", "metrics": {"fcfs": {"...": "..."}}}
}
```

`pct_improvement` is positive when the intelligent method is better (direction-aware: lower is better for waits,
idle time, conflicts; higher is better for success, fairness). `verdict` is `better` / `worse` when the paired 95%
CI of the per-seed difference excludes zero, `no_clear_difference` otherwise, `informational` for metrics with no
good/bad direction (cancellations, no-shows). `pct_improvement` can be `null` (baseline 0).

---

## POST /api/research/run

Runs the three methods on identical synthetic weeks, synchronously, and returns the metrics table plus a sample
timeline for a Gantt chart. Deterministic: seeds are `1..seeds`.

Request body (unknown fields rejected):

```json
{"seeds": 5, "load": "medium", "num_requests": 360}
```

| field | type | rules |
|---|---|---|
| `seeds` | int | 1..30, default 5 |
| `load` | string | `low` \| `medium` \| `high`, default `medium` (240 / 360 / 480 requests per week) |
| `num_requests` | int, optional | 20..600; overrides the volume of `load` |

Runtime budget: the loop stops after 2 s of simulation, so large inputs never block the server; the response then has
`"truncated": true` and `seeds_run < seeds_requested`. At most 2 simulations run at once (a third gets 429).

Response 200 (abbreviated):

```json
{
  "ok": true,
  "load": "medium",
  "num_requests": 120,
  "seeds_requested": 2,
  "seeds_run": 2,
  "truncated": false,
  "elapsed_ms": 56,
  "methods": {"fcfs": {"label": "FCFS / manual"}, "rule_based": {"label": "Rule-based"},
              "intelligent": {"label": "Intelligent (proposed)"}},
  "metrics": {"avg_wait_min": {"label": "Average waiting time", "unit": "min", "better": "lower", "headline": true}},
  "table": {
    "fcfs":        {"avg_wait_min": {"mean": 175.03, "sd": 12.2471, "ci95": 110.034, "n": 2},
                    "success_rate": {"mean": 0.7792, "sd": 0.0059, "ci95": 0.0527, "n": 2}},
    "rule_based":  {"avg_wait_min": {"mean": 154.565, "sd": 17.0059, "ci95": 152.7897, "n": 2}},
    "intelligent": {"avg_wait_min": {"mean": 155.26, "sd": 16.2493, "ci95": 145.9919, "n": 2}}
  },
  "improvement": {
    "intelligent_vs_fcfs": {"avg_wait_min": {"candidate_mean": 155.26, "baseline_mean": 175.03, "pct_improvement": 11.3,
                                             "paired_diff_mean": 19.77, "paired_diff_ci95": 35.958,
                                             "verdict": "no_clear_difference"}},
    "intelligent_vs_rule_based": {"...": "..."},
    "rule_based_vs_fcfs": {"...": "..."}
  },
  "dataset": {"requests": 120, "students_requesting": 67, "rush_share": 0.6375, "urgent_share": 0.0459,
              "cancel_share": 0.0375, "no_show_share": 0.0625, "mean_duration_min": 16.935,
              "effective_availability_min": 7082.5, "offered_load": 0.2871, "...": "..."},
  "timeline": {
    "seed": 1,
    "load": "medium",
    "time_axis": {"days": 5, "day_minutes": 480, "day_start_clock": "09:00", "unit": "minutes from Monday start of day"},
    "faculty": [
      {"faculty_id": 1, "name": "Faculty 1",
       "availability": [[275, 365], [420, 480]],
       "classes": [[60, 120], [120, 180]]}
    ],
    "methods": {
      "fcfs": [
        {"faculty_id": 1, "request_id": 19, "student_id": 102, "start_min": 450, "end_min": 480, "meeting_min": 15,
         "day": 0, "start_clock": "Mon 16:30", "kind": "served", "backfill": 0, "priority": 1}
      ],
      "rule_based": ["..."],
      "intelligent": ["..."]
    }
  }
}
```

* `table` / `improvement` contain the headline metrics only (`metrics` lists them): `avg_wait_min`,
  `median_wait_min`, `p90_wait_min`, `served_meetings`, `success_rate`, `faculty_idle_min`, `wasted_min`,
  `schedule_conflicts`, `cancellations`, `no_shows`, `fairness_jain`, `students_served`. Every cell is a mean over
  `seeds_run` seeds.
* `timeline` is the first seed's week for the **first 4 faculty**: `availability` = posted windows, `classes` = class
  timetable (blocked), and per method the list of booked blocks. `kind` is `served` (meeting held), `cancelled`
  (student cancelled; slot freed), `no_show` (student did not come), or `conflict` (FCFS booking found to overlap a
  class). `end_min - start_min` is the time the calendar was blocked (FCFS blocks whole 15-minute posted slots);
  `meeting_min` is the real meeting length. `backfill: 1` marks a meeting that filled a freed slot; `priority`
  is 1 normal / 2 priority / 3 urgent. Blocks moved to another slot by a displacement are omitted.

Errors

| status | code | when |
|---|---|---|
| 400 | `validation_error` | bad `seeds` / `load` / `num_requests` or unknown field; `fields` names them |
| 401 | `unauthenticated` | not signed in |
| 403 | `forbidden` | signed in but not `ADMIN` |
| 429 | `rate_limited` | two simulations are already running |

```json
{"error": {"code": "validation_error", "message": "Input should be less than or equal to 30",
           "fields": {"seeds": "Input should be less than or equal to 30"}}}
```
