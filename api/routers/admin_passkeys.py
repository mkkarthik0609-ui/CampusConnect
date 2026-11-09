"""/api/admin/passkeys - a signed-in admin registers, lists and removes their own passkeys (WebAuthn).
ADMIN-only via the router dependency; CSRF is enforced globally. Passkey sign-in itself is
``/api/auth/admin-passkey/*`` (api/routers/auth.py)."""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from api.deps import ApiModel, CurrentUser, Stripped, items, ok, require_role, service_errors
from api.errors import ApiError
from models import security_queries as sq
from services import passkey_service

router = APIRouter(prefix="/api/admin/passkeys", dependencies=[Depends(require_role("ADMIN"))], tags=["admin"])


class PasskeyRegisterIn(ApiModel):
    credential: dict
    label: Optional[Stripped] = Field(default=None, max_length=60)


def passkey_item(row):
    return {
        "id": row["id"], "label": row["label"] or "Passkey",
        "transports": [t for t in (row["transports"] or "").split(",") if t],
        "created_at": row["created_at"], "last_used_at": row["last_used_at"],
    }


@router.get("")
def list_passkeys(user: CurrentUser = Depends(require_role("ADMIN"))):
    out = [passkey_item(r) for r in sq.list_passkeys(user["id"])]
    return items(out, total=len(out))


@router.post("/options")
def registration_options(request: Request, user: CurrentUser = Depends(require_role("ADMIN"))):
    with service_errors():
        options = passkey_service.registration_options(request.session, request.headers.get("origin"), user)
    return JSONResponse({"options": options}, headers={"Cache-Control": "no-store"})


@router.post("/verify", status_code=201)
def register_passkey(body: PasskeyRegisterIn, request: Request, user: CurrentUser = Depends(require_role("ADMIN"))):
    with service_errors():
        new_id = passkey_service.register_passkey(request.session, user, body.credential, body.label)
    return ok("Passkey added.", id=new_id)


@router.delete("/{passkey_id}")
def delete_passkey(passkey_id: int, user: CurrentUser = Depends(require_role("ADMIN"))):
    if not sq.delete_passkey(passkey_id, user["id"]):
        raise ApiError(404, "not_found", "Passkey not found.")
    return ok("Passkey removed.")
