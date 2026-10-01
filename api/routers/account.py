"""/api/account/* - the signed-in user's own account settings."""
from typing import Literal

from fastapi import APIRouter, Depends, Request

from api.deps import ApiModel, CurrentUser, client_ip, get_current_user, ok, service_errors
from models import queries
from services import auth_service

router = APIRouter(prefix="/api/account")


class ChangePasswordIn(ApiModel):
    current_password: str
    new_password: str
    confirm_password: str


class ThemeIn(ApiModel):
    theme: Literal["light", "dark"]


@router.post("/password")
def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser = Depends(get_current_user)):
    with service_errors():
        auth_service.change_password(
            user["id"], body.current_password, body.new_password, body.confirm_password, ip=client_ip(request),
        )
    return ok("Your password has been changed.")


@router.post("/theme")
def set_theme(body: ThemeIn, request: Request, user: CurrentUser = Depends(get_current_user)):
    queries.update_user_theme(user["id"], body.theme)
    request.session["theme"] = body.theme
    return ok("Theme updated.", theme=body.theme)
