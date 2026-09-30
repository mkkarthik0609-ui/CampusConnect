"""Synthetic dataset generator for the scheduling research experiment.

This data is entirely separate from live Campus Connect accounts (PRD/ESD rule #19).
It never touches the `users`/`students`/`faculty` tables — it is written to
research/data/*.csv and consumed only by the FCFS / rule-based / intelligent
scheduling comparison in this package.
"""
import random
import csv
import os

FIELDS = [
    "request_id", "experiment_student_id", "faculty_id", "request_timestamp_min",
    "faculty_available_from_min", "faculty_available_to_min", "class_conflict",
    "meeting_duration_min", "peak_period", "cancellation", "no_show", "priority",
]


def generate_dataset(num_requests=300, num_faculty=8, num_students=120, seed=42, day_length_min=600):
    """day_length_min = length of the simulated working day in minutes (e.g. 600 = 10 hours).
    Returns a list of dict rows using FIELDS."""
    rng = random.Random(seed)
    rows = []
    peak_windows = [(60, 150), (300, 390)]  # two synthetic "rush" windows within the day

    for i in range(1, num_requests + 1):
        request_time = rng.randint(0, day_length_min - 30)
        in_peak = any(start <= request_time <= end for start, end in peak_windows)
        faculty_id = rng.randint(1, num_faculty)

        avail_start = rng.randint(0, day_length_min - 120)
        avail_end = min(day_length_min, avail_start + rng.randint(60, 180))

        duration = rng.choice([10, 15, 20, 30])
        class_conflict = rng.random() < 0.15
        cancellation = rng.random() < 0.08
        no_show = (not cancellation) and rng.random() < 0.05
        priority = rng.choices([1, 2, 3], weights=[70, 20, 10])[0]  # 1=normal,2=priority,3=urgent

        rows.append({
            "request_id": i,
            "experiment_student_id": rng.randint(1, num_students),
            "faculty_id": faculty_id,
            "request_timestamp_min": request_time,
            "faculty_available_from_min": avail_start,
            "faculty_available_to_min": avail_end,
            "class_conflict": int(class_conflict),
            "meeting_duration_min": duration,
            "peak_period": int(in_peak),
            "cancellation": int(cancellation),
            "no_show": int(no_show),
            "priority": priority,
        })
    return rows


def save_dataset(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def load_dataset(path):
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({
                "request_id": int(row["request_id"]),
                "experiment_student_id": int(row["experiment_student_id"]),
                "faculty_id": int(row["faculty_id"]),
                "request_timestamp_min": int(row["request_timestamp_min"]),
                "faculty_available_from_min": int(row["faculty_available_from_min"]),
                "faculty_available_to_min": int(row["faculty_available_to_min"]),
                "class_conflict": int(row["class_conflict"]),
                "meeting_duration_min": int(row["meeting_duration_min"]),
                "peak_period": int(row["peak_period"]),
                "cancellation": int(row["cancellation"]),
                "no_show": int(row["no_show"]),
                "priority": int(row["priority"]),
            })
        return rows
