from typing import Dict, Any, List, Optional
from datetime import date
import re
from app.services.chroma.db_client import get_collection


def compute_leaderboard(scope: str = "all", year: Optional[int] = None, month: Optional[int] = None, week: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Hitung total km per member dari seluruh koleksi dokumen (per-member text).
    scope: "all" | "year" | "month" | "week" (ISO week)
    Return list urut desc: {member, total_km, activities}
    """
    scope = (scope or "all").lower()
    today = date.today()
    y = year or today.year
    m = month or today.month
    w = week

    col = get_collection()
    # ChromaDB: do not include "ids" explicitly; ids are always returned
    got = col.get(include=["documents", "metadatas"], limit=100000)
    docs: List[str] = got.get("documents") or []
    ids: List[str] = got.get("ids") or []
    metas: List[dict] = got.get("metadatas") or []

    totals: Dict[str, Dict[str, Any]] = {}
    rx = re.compile(r"(20\d{2})-(\d{2})-(\d{2}).*?sejauh\s+([0-9]+(?:[.,][0-9]+)?)\s*km", re.IGNORECASE)

    for i, text in enumerate(docs):
        if not text:
            continue
        member = None
        md = metas[i] if i < len(metas) else {}
        if isinstance(md, dict) and md.get("member_name"):
            member = str(md["member_name"]).strip()
        if not member:
            member = ids[i] if i < len(ids) else f"member-{i}"

        for match in rx.finditer(text):
            yy, mm, dd, km = match.groups()
            try:
                dt = date(int(yy), int(mm), int(dd))
                val = float(km.replace(",", "."))
            except Exception:
                continue

            ok = False
            if scope == "all":
                ok = True
            elif scope == "year":
                ok = (dt.year == y)
            elif scope == "month":
                ok = (dt.year == y and dt.month == m)
            elif scope == "week":
                iso = dt.isocalendar()
                ok = (iso[0] == y and (w or iso[1]) == iso[1])

            if not ok:
                continue

            if member not in totals:
                totals[member] = {"member": member, "total_km": 0.0, "activities": 0}
            totals[member]["total_km"] += val
            totals[member]["activities"] += 1

    board = sorted(totals.values(), key=lambda x: x["total_km"], reverse=True)
    # round values
    for r in board:
        r["total_km"] = round(r["total_km"], 2)
    return board
