import requests
from typing import List, Dict, Any, Optional
from .auth import auth_headers
import logging, time

BASE = "https://www.strava.com/api/v3"

# --- session dengan retry & timeout ---
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(max_retries=3)
_session.mount("https://", _adapter)
DEFAULT_TIMEOUT = 10  # detik


def _get(url: str, params: Optional[Dict[str, Any]] = None, allow_404: bool = False) -> Any:
    try:
        r = _session.get(url, headers=auth_headers(), params=params, timeout=DEFAULT_TIMEOUT)
        if allow_404 and r.status_code in (403, 404):
            return None
        if r.status_code == 429:  # rate limit Strava
            reset_time = int(r.headers.get("X-RateLimit-Reset", "5"))
            logging.warning(f"Rate limit hit. Sleeping {reset_time} sec")
            time.sleep(reset_time)
            return _get(url, params, allow_404)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"Request error {url}: {e}")
        raise


def me() -> Dict[str, Any]:
    return _get(f"{BASE}/athlete")


def club_activities(club_id: int, page: int = 1, per_page: int = 50) -> List[Dict[str, Any]]:
    return _get(
        f"{BASE}/clubs/{club_id}/activities",
        params={"page": page, "per_page": per_page},
    ) or []


def activity_detail(activity_id: int) -> Optional[Dict[str, Any]]:
    return _get(f"{BASE}/activities/{activity_id}", allow_404=True)


def activity_streams(activity_id: int, keys: str = "time,heartrate,latlng,velocity_smooth,cadence,watts",
                     key_by_type: bool = True) -> Dict[str, Any]:
    params = {"keys": keys, "key_by_type": "true" if key_by_type else "false"}
    data = _get(f"{BASE}/activities/{activity_id}/streams", params=params, allow_404=True)
    if data is None:
        logging.info(f"No streams for activity {activity_id}")
        return {}
    return data


def club_activities_full(club_id: int, pages: int = 2, per_page: int = 50,
                         include_streams: bool = False, include_detail: bool = True) -> List[Dict[str, Any]]:
    """Loop feed club -> ambil detail (dan opsional streams) untuk tiap aktivitas."""
    results: List[Dict[str, Any]] = []
    for page in range(1, pages + 1):
        feed = club_activities(club_id, page=page, per_page=per_page)
        if not feed:
            break
        for item in feed:
            act_id = item.get("id")
            if not act_id:
                continue

            data = {"feed": item}
            if include_detail:
                detail = activity_detail(act_id)
                if detail:
                    data["detail"] = detail
            if include_streams:
                data["streams"] = activity_streams(act_id)
            results.append(data)
    return results
