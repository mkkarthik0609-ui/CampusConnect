"""Admin-only scheduling-research endpoints (see docs/api/research.md).

Entirely separate from live data: it only runs the synthetic simulation in services/scheduling and reads
research/results/results.json. It never touches users/students/faculty/meeting tables.
"""
import json
import os
import threading
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import Field

from api.deps import ApiModel, CurrentUser, require_role
from api.errors import ApiError
from services.scheduling import experiment

router = APIRouter(prefix="/api/research", tags=["research"])

RESULTS_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "research", "results", "results.json"))

MAX_REQUESTS = 600
TIME_BUDGET_S = 2.0
FALLBACK_SEEDS = 5

_run_slots = threading.BoundedSemaphore(2)      # at most two simulations at once (CPU-bound)
_fallback_cache = {}


class RunIn(ApiModel):
    seeds: int = Field(5, ge=1, le=30)
    load: Literal["low", "medium", "high"] = "medium"
    num_requests: Optional[int] = Field(None, ge=20, le=MAX_REQUESTS)


def _load_results():
    try:
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _generate_fallback():
    """results.json is missing: compute a small version on the fly (5 seeds, no ablation)."""
    if "results" not in _fallback_cache:
        results, _ = experiment.run_experiment(
            seeds=experiment.EVAL_SEEDS[:FALLBACK_SEEDS], ablation=False, sample=False)
        results["generated_on_the_fly"] = True
        _fallback_cache["results"] = results
    return _fallback_cache["results"]


@router.get("/results")
def get_results(user: CurrentUser = Depends(require_role("ADMIN"))):
    """The committed results.json (30 seeds x 3 loads); generated on the fly (5 seeds) if the file is missing."""
    results = _load_results()
    if results is None:
        results = _generate_fallback()
    return results


@router.post("/run")
def run_simulation(body: RunIn, user: CurrentUser = Depends(require_role("ADMIN"))):
    """Quick synchronous simulation of FCFS / rule-based / intelligent on identical synthetic weeks."""
    if not _run_slots.acquire(blocking=False):
        raise ApiError(429, "rate_limited", "Another simulation is running. Please try again in a moment.")
    try:
        return experiment.run_custom(body.seeds, body.load, body.num_requests, time_budget_s=TIME_BUDGET_S)
    finally:
        _run_slots.release()
