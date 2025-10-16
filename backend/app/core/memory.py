from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from app.core.logger import logger


_STORE: Dict[str, Dict[str, Any]] = {}
_DEFAULT_TTL_SECONDS = 60 * 60  # 1 hour


def _now() -> datetime:
    return datetime.utcnow()


def get_session(session_id: Optional[str]) -> Dict[str, Any]:
    sid = session_id or "default"
    sess = _STORE.get(sid)
    if not sess or sess.get("expires_at") and sess["expires_at"] < _now():
        sess = {
            "member": None,
            "month": None,
            "year": None,
            "last_query": None,
            "created_at": _now(),
            "expires_at": _now() + timedelta(seconds=_DEFAULT_TTL_SECONDS),
        }
        _STORE[sid] = sess
    return sess


def update_session(session_id: Optional[str], *, member: Optional[str] = None, month: Optional[int] = None, year: Optional[int] = None, last_query: Optional[str] = None) -> None:
    sid = session_id or "default"
    sess = get_session(sid)
    if member:
        sess["member"] = member
    if month is not None:
        sess["month"] = month
    if year is not None:
        sess["year"] = year
    if last_query is not None:
        sess["last_query"] = last_query
    # refresh ttl
    sess["expires_at"] = _now() + timedelta(seconds=_DEFAULT_TTL_SECONDS)
    _STORE[sid] = sess
    logger.info(f"memory: updated session {sid} -> member={sess['member']}, month={sess['month']}, year={sess['year']}")


def clear_session(session_id: Optional[str]) -> None:
    sid = session_id or "default"
    if sid in _STORE:
        del _STORE[sid]
        logger.info(f"memory: cleared session {sid}")

