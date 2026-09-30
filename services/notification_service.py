from models import queries

# notification_type values used across the app
MEETING_REQUESTED = "MEETING_REQUESTED"
MEETING_ACCEPTED = "MEETING_ACCEPTED"
MEETING_REJECTED = "MEETING_REJECTED"
MEETING_CANCELLED = "MEETING_CANCELLED"
MEETING_COMPLETED = "MEETING_COMPLETED"
MEETING_REMINDER = "MEETING_REMINDER"
SUPPORTING_REQUESTED = "SUPPORTING_REQUESTED"
SUPPORTING_RESPONDED = "SUPPORTING_RESPONDED"
PERMISSION_REQUESTED = "PERMISSION_REQUESTED"
PERMISSION_RESPONDED = "PERMISSION_RESPONDED"
NEW_MESSAGE = "NEW_MESSAGE"
ASSIGNMENT_REQUESTED = "ASSIGNMENT_REQUESTED"
ASSIGNMENT_RESPONDED = "ASSIGNMENT_RESPONDED"
ASSIGNMENT_CHANGED = "ASSIGNMENT_CHANGED"


def notify(user_id, notification_type, title, message, related_entity_type=None, related_entity_id=None):
    return queries.create_notification(
        user_id, notification_type, title, message, related_entity_type, related_entity_id
    )


def get_unread_count(user_id):
    return queries.get_unread_notification_count(user_id)


def list_notifications(user_id):
    return queries.list_notifications_for_user(user_id)


def mark_read(notification_id, user_id):
    queries.mark_notification_read(notification_id, user_id)


def mark_all_read(user_id):
    queries.mark_all_notifications_read(user_id)
