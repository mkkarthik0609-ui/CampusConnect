"""/api/notifications* - the signed-in user's own notifications."""
from fastapi import APIRouter, Depends

from api.deps import CurrentUser, get_current_user, ok
from api.errors import ApiError
from services import notification_service as notif

router = APIRouter(prefix="/api/notifications")


def _item(row):
    return {
        "id": row["id"],
        "type": row["notification_type"],
        "title": row["title"],
        "message": row["message"],
        "related_entity_type": row["related_entity_type"],
        "related_entity_id": row["related_entity_id"],
        "is_read": bool(row["is_read"]),
        "created_at": row["created_at"],
    }


@router.get("")
def list_notifications(user: CurrentUser = Depends(get_current_user)):
    rows = notif.list_notifications(user["id"])
    return {"items": [_item(r) for r in rows], "unread_count": notif.get_unread_count(user["id"])}


@router.post("/read-all")
def mark_all_read(user: CurrentUser = Depends(get_current_user)):
    notif.mark_all_read(user["id"])
    return ok("All notifications marked as read.", unread_count=0)


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, user: CurrentUser = Depends(get_current_user)):
    if not notif.mark_read(notification_id, user["id"]):
        raise ApiError(404, "not_found", "Notification not found.")
    return ok("Notification marked as read.", unread_count=notif.get_unread_count(user["id"]))
