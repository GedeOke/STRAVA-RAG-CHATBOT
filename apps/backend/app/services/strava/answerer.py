from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import os, re, logging, calendar
from datetime import datetime, timedelta
import dateparser, pytz
from groq import Groq
from . import retriever

logger = logging.getLogger(__name__)

# ===================== Persona =====================
_SYS_PROMPT = (
    "Kamu adalah Asisten Strava Club yang ngobrol santai, seperti teman satu klub olahraga. "
    "Jawablah dengan bahasa sehari-hari yang ramah dan enak dibaca, seolah-olah manusia biasa. "
    "Kalau cocok, boleh pakai bullet list atau paragraf pendek biar jelas. "
    "Jawab selalu berdasarkan data aktivitas yang aku kasih — jangan bikin cerita sendiri. "
    "Kalau datanya memang nggak ada, jujur aja bilang belum ada catatan. "
    "Kalau pertanyaan menyebut angka, tanggal, atau nama, fokuslah pada informasi itu. "
    "Selipkan referensi [nomor] sesuai sumber data yang dipakai."
)

# ===================== LLM Client =====================
_GROQ_CLIENT = None

def get_groq_client() -> Groq:
    global _GROQ_CLIENT
    if _GROQ_CLIENT is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY belum diset.")
        _GROQ_CLIENT = Groq(api_key=api_key, timeout=60)
    return _GROQ_CLIENT

# ===================== Utils =====================

def _join_contexts(contexts: List[Dict], max_ctx_chars: int = 8000) -> str:
    """Gabungkan context jadi teks natural untuk LLM"""
    parts, used = [], 0
    for i, it in enumerate(contexts, start=1):
        km = f"{it.get('km'):.2f} km" if it.get('km') else "?"
        pace = f"pace {it.get('pace')}/km" if it.get('pace') else ""
        elev = f"elev {it.get('elev')} m" if it.get('elev') else ""
        desc = f"[{i}] {it.get('summary','')} • {km} {pace} {elev}".strip()
        chunk = desc[:800]
        if used + len(chunk) > max_ctx_chars:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts)

def _parse_citation_indices(text: str) -> List[int]:
    return sorted(set(int(n) for n in re.findall(r"\[(\d+)\]", text)))

def _extract_km_from_question(q: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*km\b", q.lower())
    return float(m.group(1).replace(",", ".")) if m else None

def _filter_contexts_by_km(ctx: List[Dict], target_km: float, tol: float = 0.3):
    lo, hi = target_km - tol, target_km + tol
    return [it for it in ctx if (it.get("km") and lo <= float(it["km"]) <= hi)]

def _unique_by_athlete(ctx: List[Dict]):
    seen, out = set(), []
    for it in ctx:
        name = (it.get("summary") or "").split(" melakukan", 1)[0].strip()
        if name and name not in seen:
            seen.add(name)
            out.append(it)
    return out

# ===================== Date parsing =====================

def parse_date_range(q: str, default_days: int = 7) -> Tuple[datetime, datetime]:
    tz = pytz.timezone("Asia/Jakarta")
    now = datetime.now(tz)

    # format eksplisit "8 sampai 13 September 2025"
    m = re.search(r"(\d{1,2})\s*(?:sampai|sd|-|hingga|to)\s*(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})", q.lower())
    if m:
        d1, d2, month, year = m.groups()
        start = dateparser.parse(f"{d1} {month} {year}", settings={"TIMEZONE": "Asia/Jakarta"})
        end = dateparser.parse(f"{d2} {month} {year}", settings={"TIMEZONE": "Asia/Jakarta"}) + timedelta(days=1)
        return start, end

    ql = q.lower()
    if "hari ini" in ql:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if "kemarin" in ql:
        y = now - timedelta(days=1)
        return y.replace(hour=0, minute=0), y.replace(hour=23, minute=59)
    if "minggu ini" in ql:
        start = now - timedelta(days=now.weekday())
        return start, start + timedelta(days=7)
    if "bulan ini" in ql:
        start = now.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year+1, month=1)
        else:
            end = start.replace(month=start.month+1)
        return start, end

    # fallback: default_days terakhir
    return now - timedelta(days=default_days), now

# ===================== SQL Helpers =====================

def _sql_metric(db: Session, athlete: str, start: datetime, end: datetime, metric: str) -> float | int:
    if metric == "sum_distance":
        sql = """
            SELECT SUM(distance_m)/1000.0
            FROM activities a
            JOIN athletes at ON a.athlete_id = at.id
            WHERE LOWER(at.firstname) = LOWER(:name)
              AND a.date BETWEEN :start AND :end
              AND a.distance_m IS NOT NULL
        """
    elif metric == "count":
        sql = """
            SELECT COUNT(*)
            FROM activities a
            JOIN athletes at ON a.athlete_id = at.id
            WHERE LOWER(at.firstname) = LOWER(:name)
              AND a.date BETWEEN :start AND :end
              AND a.distance_m IS NOT NULL
        """
    else:
        return 0
    row = db.execute(text(sql), {"name": athlete.lower(), "start": start, "end": end}).fetchone()
    return float(row[0]) if row and row[0] else 0.0

def _extract_names(db: Session, q: str) -> List[str]:
    ql = q.lower()
    names = db.execute(text("SELECT DISTINCT LOWER(firstname) FROM athletes")).fetchall()
    return [n for (n,) in names if n and n in ql]

# ===================== Intent =====================

def _detect_intent(q: str) -> str:
    ql = q.lower()
    if re.search(r"\bsiapa( aja| saja)?\b|\bwho\b", ql): return "who"
    if re.search(r"\bberapa kali|count|jumlah\b", ql): return "count"
    if re.search(r"\bbanding(kan)?|compare\b", ql): return "compare"
    if re.search(r"\btren|trend|minggu|bulan\b", ql): return "trend"
    if re.search(r"\btercepat|terlama|top\b", ql): return "top"
    if "total" in ql and "km" in ql: return "sum_distance"
    return "generic"

# ===================== LLM =====================

def _llm_answer_groq(question: str, contexts: List[Dict], intent: str):
    client = get_groq_client()
    model = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()

    ctx_text = _join_contexts(contexts) if contexts else ""
    user = f"Intent: {intent}\nPertanyaan: {question}\nSumber:\n{ctx_text}\n"

    resp = client.chat.completions.create(
        model=model, temperature=0.35, max_tokens=400, top_p=1.0,
        messages=[{"role": "system", "content": _SYS_PROMPT}, {"role": "user", "content": user}]
    )
    text = resp.choices[0].message.content.strip()
    cites = _parse_citation_indices(text)
    return {"answer": text, "used_model": model, "cites": cites}

# ===================== Sources =====================

def _project_sources(ctx: List[Dict], cite_indices: List[int]):
    return [{
        "slot": i, "id": it.get("id"), "km": it.get("km"),
        "emb_dist": it.get("emb_dist"), "ce_score": it.get("ce_score"),
        "summary": it.get("summary"), "cited": (i in cite_indices)
    } for i, it in enumerate(ctx, start=1)]

# ===================== Main =====================

def answer(db: Session, question: str, top_k: int = 50, include_sources: bool = True):
    intent = _detect_intent(question)
    start, end = parse_date_range(question)

    # Structured SQL intents
    if intent in ["sum_distance", "count", "compare"]:
        names = _extract_names(db, question)
        if names:
            if intent == "sum_distance" and len(names) == 1:
                total = _sql_metric(db, names[0], start, end, "sum_distance")
                q2 = f"{names[0].title()} total lari {total:.2f} km antara {start.date()} dan {end.date()}. Buat narasi santai."
                out = _llm_answer_groq(q2, [], "sum_distance")
                return {"question": question, "answer": out["answer"], "used_model": "sql+llm", "sources": []}

            if intent == "count" and len(names) == 1:
                cnt = int(_sql_metric(db, names[0], start, end, "count"))
                q2 = f"{names[0].title()} lari {cnt} kali antara {start.date()} dan {end.date()}. Buat narasi santai."
                out = _llm_answer_groq(q2, [], "count")
                return {"question": question, "answer": out["answer"], "used_model": "sql+llm", "sources": []}

            if intent == "compare" or len(names) >= 2:
                stats = []
                for n in names:
                    km = _sql_metric(db, n, start, end, "sum_distance")
                    cnt = int(_sql_metric(db, n, start, end, "count"))
                    stats.append(f"{n.title()}: {km:.2f} km dalam {cnt} aktivitas")
                q2 = question + "\n\nData perbandingan:\n" + "\n".join(stats)
                out = _llm_answer_groq(q2, [], "compare")
                return {"question": question, "answer": out["answer"], "used_model": "sql+llm", "sources": []}

    # === Fallback ke RAG ===
    ctx = retriever.search_similar(db, question, top_k=top_k)
    if not ctx:
        return {"question": question, "answer": "Aku nggak nemu data.", "used_model": "no-context", "sources": []}

    km_q = _extract_km_from_question(question)
    if km_q:
        filtered = _filter_contexts_by_km(ctx, km_q, tol=0.3)
        if filtered:
            ctx = _unique_by_athlete(filtered)

    try:
        out = _llm_answer_groq(question, ctx, intent)
    except Exception as e:
        logger.error("Groq API error: %s", e, exc_info=True)
        return {"question": question, "answer": f"Error LLM: {e}", "used_model": "llm-error", "sources": []}

    payload = {"question": question, "answer": out["answer"], "used_model": out["used_model"]}
    if include_sources:
        payload["sources"] = _project_sources(ctx, out.get("cites", []))
    return payload
