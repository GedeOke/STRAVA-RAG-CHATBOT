import requests
from typing import List, Dict, Any, Optional
from .auth import auth_headers

BASE = "https://www.strava.com/api/v3"

def me() -> Dict[str, Any]:
    r = requests.get(f"{BASE}/athlete", headers=auth_headers())
    r.raise_for_status()
    return r.json()

def club_activities(club_id: int, page: int = 1, per_page: int = 50) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{BASE}/clubs/{club_id}/activities",
        headers=auth_headers(),
        params={"page": page, "per_page": per_page},
    )
    r.raise_for_status()
    return r.json()

def activity_detail(activity_id: int) -> Dict[str, Any]:
    r = requests.get(f"{BASE}/activities/{activity_id}", headers=auth_headers())
    r.raise_for_status()
    return r.json()

def activity_streams(activity_id: int, keys: str = "time,heartrate,latlng,velocity_smooth,cadence,watts",
                     key_by_type: bool = True) -> Dict[str, Any]:
    params = {"keys": keys, "key_by_type": "true" if key_by_type else "false"}
    r = requests.get(f"{BASE}/activities/{activity_id}/streams",
                     headers=auth_headers(), params=params)
    # Streams bisa 404/403 jika tidak ada izin atau tidak ada data—jangan raise.
    if r.status_code == 200:
        return r.json()
    return {}

def club_activities_full(club_id: int, pages: int = 2, per_page: int = 50,
                         include_streams: bool = False) -> List[Dict[str, Any]]:
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
            detail = activity_detail(act_id)
            data = {"feed": item, "detail": detail}
            if include_streams:
                data["streams"] = activity_streams(act_id)
            results.append(data)
    return results
