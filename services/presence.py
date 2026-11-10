"""Typing indicators and "last active" presence for the messaging screens.

"Last active" is persisted (table ``presence``, throttled to one write per user per PERSIST_EVERY seconds, written
after the request's own transaction so it never commits half-finished work), so it survives restarts and works
with several instances. Typing indicators are 5-second signals and stay in process memory on purpose.
"""
import time

TYPING_TTL = 5.0     # seconds a "typing..." signal stays alive without a refresh
ONLINE_WINDOW = 30.0  # a participant who fetched/polled within this many seconds counts as online

_typing = {}   # (scope, conversation_id, user_id) -> expiry (monotonic seconds)
_active = {}   # user_id -> unix seconds of the last request that touched a conversation (read-through cache)
_persisted = {}  # user_id -> unix seconds of the last database write for that user
PERSIST_EVERY = 20.0


def _mono():
    return time.monotonic()


def _wall():
    return time.time()


def touch(user_id):
    """The user's client just fetched / polled / sent something."""
    now = _wall()
    _active[user_id] = now
    if now - _persisted.get(user_id, 0) >= PERSIST_EVERY:
        from api import db as dbmod
        if dbmod.defer_write(
                "INSERT INTO presence (user_id, last_seen_epoch) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET last_seen_epoch = EXCLUDED.last_seen_epoch",
                (user_id, int(now))):
            _persisted[user_id] = now


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
    if seen is None:  # after a restart (or on another instance): fall back to the persisted value
        from api import db as dbmod
        if dbmod.has_db_context():
            row = dbmod.get_db().execute("SELECT last_seen_epoch FROM presence WHERE user_id = ?", (user_id,)).fetchone()
            seen = float(row[0]) if row else None
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
    _persisted.clear()
