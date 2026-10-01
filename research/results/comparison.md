# Scheduling method comparison

> Can data-driven scheduling reduce student waiting time and improve faculty-student meeting efficiency compared with the current/manual scheduling approach?

Synthetic data, 30 seeds per load level (seeds 1-30), mean ± 95% CI (Student t). `% vs FCFS` / `% vs Rule` = improvement of the Intelligent method (positive = better, direction accounts for lower-is-better metrics); `*` = paired 95% CI excludes zero and Intelligent is better, `!` = paired 95% CI excludes zero and Intelligent is WORSE.

## Low load (240 requests / week)

Offered load = requested minutes / usable faculty minutes = 0.59; 96 students ask on average; 70% of requests arrive in the two rush windows.

| Metric | FCFS / manual | Rule-based | Intelligent | % vs FCFS | % vs Rule |
|---|---|---|---|---|---|
| Average waiting time (min) | 245.7 ± 7.3 | 214.9 ± 7.7 | 219.1 ± 8.1 | +10.8% * | -1.9% ! |
| Median waiting time (min) | 202.2 ± 8.2 | 183.4 ± 6.4 | 185.8 ± 6.8 | +8.1% * | -1.3% ! |
| 90th percentile waiting time (min) | 484.2 ± 20.6 | 429.7 ± 19.6 | 436.0 ± 20.7 | +10.0% * | -1.4% ! |
| Meetings held | 160.5 ± 3.6 | 173.8 ± 3.4 | 175.2 ± 3.1 | +9.1% * | +0.8% * |
| Success rate (held / requested) | 0.669 ± 0.015 | 0.724 ± 0.014 | 0.730 ± 0.013 | +9.1% * | +0.8% * |
| Faculty idle time (min) | 4340.2 ± 108.3 | 4106.3 ± 115.0 | 4082.0 ± 112.8 | +6.0% * | +0.6% * |
| Wasted booked minutes (min) | 317.0 ± 28.9 | 303.5 ± 28.6 | 289.8 ± 30.0 | +8.6% * | +4.5% * |
| Schedule conflicts | 95.7 ± 2.9 | 0.0 ± 0.0 | 0.0 ± 0.0 | +100.0% * | n/a |
| Cancellations (of booked) | 11.8 ± 1.3 | 13.2 ± 1.5 | 13.4 ± 1.5 | n/a | n/a |
| No-shows (of booked) | 8.5 ± 1.0 | 9.4 ± 1.1 | 9.4 ± 1.1 | n/a | n/a |
| Fairness (Jain index, per-student served rate) | 0.754 ± 0.015 | 0.798 ± 0.013 | 0.805 ± 0.012 | +6.8% * | +0.9% * |
| Students served | 78.6 ± 1.5 | 81.9 ± 1.5 | 82.5 ± 1.4 | +5.0% * | +0.7% * |

<details><summary>More metrics</summary>

| Metric | FCFS / manual | Rule-based | Intelligent |
|---|---|---|---|
| Avg wait incl. unserved (charged full window) | 267.6 ± 8.9 | 223.9 ± 8.7 | 225.7 ± 8.4 |
| Faculty time utilisation | 0.384 ± 0.009 | 0.417 ± 0.010 | 0.420 ± 0.009 |
| Urgent requests held | 0.450 ± 0.041 | 0.544 ± 0.043 | 0.573 ± 0.043 |
| Urgent avg waiting time | 152.3 ± 13.0 | 151.8 ± 12.3 | 160.6 ± 13.0 |
| Rush-window requests held | 0.658 ± 0.018 | 0.716 ± 0.016 | 0.721 ± 0.015 |
| Fairness of waiting (Jain index) | 0.712 ± 0.019 | 0.739 ± 0.013 | 0.744 ± 0.014 |
| Meetings recovered by back-fill | 0.0 ± 0.0 | 0.0 ± 0.0 | 1.2 ± 0.5 |

</details>

## Medium load (360 requests / week)

Offered load = requested minutes / usable faculty minutes = 0.88; 112 students ask on average; 70% of requests arrive in the two rush windows.

| Metric | FCFS / manual | Rule-based | Intelligent | % vs FCFS | % vs Rule |
|---|---|---|---|---|---|
| Average waiting time (min) | 299.2 ± 9.1 | 270.3 ± 8.9 | 275.2 ± 8.6 | +8.0% * | -1.8% ! |
| Median waiting time (min) | 243.5 ± 10.3 | 218.6 ± 9.9 | 221.4 ± 9.7 | +9.1% * | -1.3% ! |
| 90th percentile waiting time (min) | 604.0 ± 19.1 | 555.7 ± 26.1 | 565.7 ± 23.9 | +6.3% * | -1.8% ! |
| Meetings held | 204.7 ± 3.6 | 230.7 ± 3.6 | 234.1 ± 3.4 | +14.4% * | +1.5% * |
| Success rate (held / requested) | 0.569 ± 0.010 | 0.641 ± 0.010 | 0.650 ± 0.009 | +14.4% * | +1.5% * |
| Faculty idle time (min) | 3598.0 ± 109.6 | 3159.2 ± 118.6 | 3106.8 ± 116.6 | +13.7% * | +1.7% * |
| Wasted booked minutes (min) | 369.0 ± 30.2 | 375.0 ± 28.7 | 331.7 ± 29.8 | +10.1% * | +11.6% * |
| Schedule conflicts | 134.8 ± 3.8 | 0.0 ± 0.0 | 0.0 ± 0.0 | +100.0% * | n/a |
| Cancellations (of booked) | 16.1 ± 1.2 | 18.2 ± 1.4 | 18.4 ± 1.4 | n/a | n/a |
| No-shows (of booked) | 10.1 ± 1.1 | 11.9 ± 1.2 | 12.0 ± 1.3 | n/a | n/a |
| Fairness (Jain index, per-student served rate) | 0.697 ± 0.011 | 0.753 ± 0.009 | 0.762 ± 0.009 | +9.4% * | +1.2% * |
| Students served | 87.8 ± 1.6 | 93.0 ± 1.6 | 93.8 ± 1.6 | +6.8% * | +0.9% * |

<details><summary>More metrics</summary>

| Metric | FCFS / manual | Rule-based | Intelligent |
|---|---|---|---|
| Avg wait incl. unserved (charged full window) | 339.1 ± 8.5 | 289.8 ± 8.3 | 291.6 ± 8.0 |
| Faculty time utilisation | 0.489 ± 0.010 | 0.552 ± 0.012 | 0.559 ± 0.011 |
| Urgent requests held | 0.315 ± 0.038 | 0.414 ± 0.041 | 0.463 ± 0.038 |
| Urgent avg waiting time | 158.6 ± 14.2 | 156.4 ± 11.7 | 170.0 ± 13.1 |
| Rush-window requests held | 0.561 ± 0.013 | 0.635 ± 0.012 | 0.643 ± 0.012 |
| Fairness of waiting (Jain index) | 0.734 ± 0.018 | 0.747 ± 0.016 | 0.749 ± 0.017 |
| Meetings recovered by back-fill | 0.0 ± 0.0 | 0.0 ± 0.0 | 4.3 ± 0.6 |

</details>

## High load (480 requests / week)

Offered load = requested minutes / usable faculty minutes = 1.17; 122 students ask on average; 70% of requests arrive in the two rush windows.

| Metric | FCFS / manual | Rule-based | Intelligent | % vs FCFS | % vs Rule |
|---|---|---|---|---|---|
| Average waiting time (min) | 351.5 ± 9.5 | 316.9 ± 10.2 | 322.3 ± 9.7 | +8.3% * | -1.7% ! |
| Median waiting time (min) | 303.5 ± 14.7 | 257.2 ± 12.7 | 262.1 ± 12.1 | +13.7% * | -1.9% ! |
| 90th percentile waiting time (min) | 695.2 ± 21.5 | 644.0 ± 22.2 | 651.3 ± 21.0 | +6.3% * | -1.1% ! |
| Meetings held | 233.2 ± 4.3 | 272.2 ± 4.3 | 278.3 ± 4.0 | +19.3% * | +2.2% * |
| Success rate (held / requested) | 0.486 ± 0.009 | 0.567 ± 0.009 | 0.580 ± 0.008 | +19.3% * | +2.2% * |
| Faculty idle time (min) | 3141.2 ± 105.8 | 2489.3 ± 116.6 | 2404.8 ± 113.8 | +23.4% * | +3.4% * |
| Wasted booked minutes (min) | 417.0 ± 36.0 | 440.7 ± 34.6 | 368.8 ± 35.9 | +11.6% * | +16.3% * |
| Schedule conflicts | 165.8 ± 4.3 | 0.0 ± 0.0 | 0.0 ± 0.0 | +100.0% * | n/a |
| Cancellations (of booked) | 18.3 ± 1.5 | 22.0 ± 1.7 | 22.3 ± 1.8 | n/a | n/a |
| No-shows (of booked) | 12.2 ± 1.3 | 14.3 ± 1.3 | 14.1 ± 1.5 | n/a | n/a |
| Fairness (Jain index, per-student served rate) | 0.658 ± 0.012 | 0.724 ± 0.010 | 0.736 ± 0.009 | +11.9% * | +1.6% * |
| Students served | 93.9 ± 1.9 | 100.3 ± 1.9 | 101.3 ± 1.9 | +7.8% * | +1.0% * |

<details><summary>More metrics</summary>

| Metric | FCFS / manual | Rule-based | Intelligent |
|---|---|---|---|
| Avg wait incl. unserved (charged full window) | 395.8 ± 8.5 | 342.6 ± 8.2 | 344.6 ± 7.8 |
| Faculty time utilisation | 0.554 ± 0.010 | 0.647 ± 0.012 | 0.659 ± 0.012 |
| Urgent requests held | 0.221 ± 0.029 | 0.318 ± 0.037 | 0.375 ± 0.036 |
| Urgent avg waiting time | 181.8 ± 13.1 | 171.3 ± 12.0 | 184.9 ± 11.0 |
| Rush-window requests held | 0.478 ± 0.011 | 0.559 ± 0.012 | 0.573 ± 0.011 |
| Fairness of waiting (Jain index) | 0.772 ± 0.012 | 0.766 ± 0.013 | 0.771 ± 0.014 |
| Meetings recovered by back-fill | 0.0 ± 0.0 | 0.0 ± 0.0 | 6.9 ± 0.8 |

</details>

## Conclusion (medium load)

1. Waiting time: intelligent 275 min vs FCFS 299 min (8.0% lower, better) and vs rule-based 270 min (1.8% higher, worse).
2. Meetings held: 234 vs 205 (FCFS) and 231 (rule-based); success rate 65.0% vs 56.9% and 64.1%.
3. Faculty time: idle time 3107 min vs 3598 (FCFS) / 3159 (rule-based); schedule conflicts 0 vs 135 (FCFS) and 0 (rule-based).
4. Fairness (Jain): 0.762 vs 0.697 (FCFS) and 0.753 (rule-based); urgent requests held 46.3% vs 31.4% and 41.4%.
5. Weakest metric for the intelligent method: Average waiting time (-1.8% vs rule-based, worse). Most of the gain over FCFS comes from respecting the class timetable and flexible meeting lengths (already present in rule-based); the scoring layer adds smaller gains. Data are synthetic.

## Which parts of the intelligent method matter? (medium load, ablation)

| Variant | Avg wait (min) | Success rate | Idle (min) | Wasted (min) | Fairness | Urgent held |
|---|---|---|---|---|---|---|
| full | 275.2 ± 8.6 | 0.650 ± 0.009 | 3106.8 ± 116.6 | 331.7 ± 29.8 | 0.762 ± 0.009 | 0.463 ± 0.038 |
| no_fairness | 275.5 ± 8.7 | 0.650 ± 0.010 | 3106.7 ± 116.0 | 331.3 ± 30.3 | 0.759 ± 0.009 | 0.465 ± 0.038 |
| no_slack | 274.7 ± 8.6 | 0.651 ± 0.009 | 3105.8 ± 115.8 | 330.3 ± 29.2 | 0.762 ± 0.009 | 0.459 ± 0.037 |
| no_risk | 275.2 ± 8.5 | 0.650 ± 0.009 | 3106.3 ± 115.8 | 330.8 ± 30.3 | 0.762 ± 0.009 | 0.462 ± 0.037 |
| no_packing | 274.3 ± 8.8 | 0.651 ± 0.009 | 3106.3 ± 116.3 | 330.8 ± 29.8 | 0.762 ± 0.009 | 0.465 ± 0.037 |
| no_peak_spreading | 275.2 ± 8.6 | 0.650 ± 0.009 | 3107.2 ± 115.9 | 331.0 ± 29.1 | 0.762 ± 0.009 | 0.465 ± 0.037 |
| no_backfill | 273.5 ± 8.9 | 0.641 ± 0.010 | 3158.0 ± 118.7 | 375.8 ± 31.2 | 0.754 ± 0.009 | 0.435 ± 0.039 |
| no_displacement | 274.0 ± 8.5 | 0.650 ± 0.009 | 3111.0 ± 118.3 | 332.5 ± 29.7 | 0.763 ± 0.009 | 0.449 ± 0.040 |

## How much of FCFS's gap is an assumption about manual scheduling? (medium load)

| Variant | Avg wait (min) | Success rate | Idle (min) | Conflicts | Fairness |
|---|---|---|---|---|---|
| fcfs_default (15-min slots, clash found at meeting) | 299.2 ± 9.1 | 0.569 ± 0.010 | 3598.0 ± 109.6 | 134.8 ± 3.8 | 0.697 ± 0.011 |
| fcfs_clash_found_at_day_start | 304.3 ± 9.7 | 0.580 ± 0.009 | 3546.7 ± 109.7 | 197.7 ± 5.6 | 0.703 ± 0.009 |
| fcfs_flexible_5min_slots | 264.5 ± 8.3 | 0.628 ± 0.009 | 3235.0 ± 108.5 | 134.5 ± 3.8 | 0.741 ± 0.009 |
| fcfs_both_relaxed | 265.8 ± 8.9 | 0.640 ± 0.010 | 3168.2 ± 112.7 | 182.6 ± 5.6 | 0.753 ± 0.009 |
| rule_based (reference) | 270.3 ± 8.9 | 0.641 ± 0.010 | 3159.2 ± 118.6 | 0.0 ± 0.0 | 0.753 ± 0.009 |
| intelligent (reference) | 275.2 ± 8.6 | 0.650 ± 0.009 | 3106.8 ± 116.6 | 0.0 ± 0.0 | 0.762 ± 0.009 |
