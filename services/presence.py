"""In-memory typing indicators and "last active" presence for the messaging screens.

shortcut: process-local dicts, which is right for the single-worker deployment this app runs as; switch to a
shared store (Redis / a table) before running more than one worker. After a restart everybody is simply
"unknown" until their next request.
"""
import time

TYPING_TTL = 5.0     # seconds a "typing..." signal stays alive without a refresh
ONLINE_WINDOW = 30.0  # a participant who fetched/polled within this many seconds counts as online

_typing = {}   # (scope, conversation_id, user_id) -> expiry (monotonic seconds)
_active = {}   # user_id -> unix seconds of the last request that touched a conversation


def _mono():
    return time.monotonic()


def _wall():
    return time.time()


def touch(user_id):
    """The user's client just fetched / polled / sent something."""
    _active[user_id] = _wall()


def set_typing(scope, conversation_id, user_id):
    _typing[(scope, conversation_id, user_id)] = _mono() + TYPING_TTL
    touch(user_id)


def clear_typing(scope, conversation_id, user_id):
    _typing.pop((scope, conversation_id, user_id), None)


def is_typing(scope, conversation_id, user_id):
    key = (scope, conversation_id, user_id)
    expires = _typing.get(key)
    if expires is None:
        return False
    if expires <= _mono():
        _typing.pop(key, None)
        return False
    return True


def status(user_id):
    """``{"online": bool, "last_active_at": 'YYYY-MM-DD HH:MM:SS' (UTC) | None}``."""
    seen = _active.get(user_id)
    if seen is None:
        return {"online": False, "last_active_at": None}
    return {
        "online": _wall() - seen <= ONLINE_WINDOW,
        "last_active_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(seen)),
    }


def reset():
    """Forget everything (tests)."""
    _typing.clear()
    _active.clear()
