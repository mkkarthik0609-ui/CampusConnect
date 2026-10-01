"""GET /api/academic/tree - public, active-only Branch > Department > Year > Section options."""
from fastapi import APIRouter

from services import academic_service

router = APIRouter(prefix="/api/academic")


def _public(nodes, child_key):
    out = []
    for n in nodes:
        item = {"id": n["id"], "name": n["name"]}
        if child_key:
            item[child_key] = _public(n[child_key], _NEXT[child_key])
        out.append(item)
    return out


_NEXT = {"departments": "years", "years": "sections", "sections": None}


@router.get("/tree")
def academic_tree():
    return {"branches": _public(academic_service.get_tree(active_only=True), "departments")}
