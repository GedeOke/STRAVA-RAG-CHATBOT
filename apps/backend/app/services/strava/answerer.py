from typing import List, Dict, Any
from sqlalchemy.orm import Session
import os, re, traceback, logging
from groq import Groq
from . import retriever

logger = logging.getLogger(__name__)

# Persona system prompt
_SYS_PROMPT = (
    "Kamu adalah Asisten Strava untuk klub. "
    "Jawablah dengan gaya santai tapi tetap faktual, 100% hanya dari konteks yang diberikan. "
    "Gunakan bahasa sehari-hari, boleh bullet list bila membantu. "
    "Jika tidak yakin, katakan tidak tahu dan tawarkan opsi tindak lanjut. "
    "Selalu cantumkan referensi [nomor] sesuai sumber yang dipakai."
)

# ===================== Utils =====================

def _join_contexts(contexts: List[Dict], max_ctx_chars: int = 8000) -> str:
    """Gabungkan data aktivitas jadi konteks kaya (nama, jarak, dll)."""
    parts, used = [], 0
    for i, it in enumerate(contexts, start=1):
        km_val = f"{it['km']:.2f} km" if it.get("km") is not None else "?"
        desc = f"[{i}] {it['summary']} • Jarak: {km_val}"
        chunk = desc[:800]
        if used + len(chunk) + 1 > max_ctx_chars:
            break
        parts.append(chunk)
        used += len(chunk) + 1
    return "\n".join(parts)


def _parse_citation_indices(text: str) -> List[int]:
    """Ambil angka di dalam bracket, mis. [1][3] -> [1,3]."""
    nums = re.findall(r"\[(\d+)\]", text)
    return sorted(set(int(n) for n in nums if n.isdigit()))

def _extract_km_from_question(q: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*km\b", q.lower())
    if not m:
        return None
    return float(m.group(1).replace(",", "."))

def _filter_contexts_by_km(ctx: List[Dict], target_km: float, tol: float = 0.3) -> List[Dict]:
    lo, hi = target_km - tol, target_km + tol
    return [it for it in ctx if (it.get("km") is not None and lo <= float(it["km"]) <= hi)]

def _unique_by_athlete(ctx: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for it in ctx:
        s = it.get("summary") or ""
        name = s.split(" melakukan", 1)[0].strip()
        if name and name not in seen:
            seen.add(name)
            out.append(it)
    return out

def _detect_intent(q: str) -> str:
    ql = q.lower()
    if re.search(r"\bsiapa( aja| saja)?\b|\bwho\b", ql): return "who"
    if re.search(r"\bberapa kali|count|jumlah\b", ql): return "count"
    if re.search(r"\bbanding(kan)?|compare\b", ql): return "compare"
    if re.search(r"\btren|trend|minggu|bulan\b", ql): return "trend"
    if re.search(r"\btercepat|terlama|top\b", ql): return "top"
    return "generic"

# ===================== LLM =====================

def _llm_answer_groq(question: str, contexts: List[Dict]) -> Dict[str, Any]:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY belum diset.")

    model = (os.getenv("GROQ_MODEL") or "llama-3.1-8b-instant").strip()
    client = Groq(api_key=api_key, timeout=60)

    ctx_text = _join_contexts(contexts)
    intent = _detect_intent(question)

    user = (
        f"Intent: {intent}\n"
        f"Pertanyaan: {question}\n\n"
        f"Sumber (ringkasan aktivitas):\n{ctx_text}\n\n"
        "Instruksi:\n"
        "- Jawab maksimal 3 kalimat, gaya santai.\n"
        "- Format sesuai intent (who, count, compare, top, trend, generic).\n"
        "- Jika pertanyaan menyebut jarak (mis. 5 km), fokus pada aktivitas di jarak itu (±0.3 km).\n"
        "- Jangan mengarang data di luar sumber.\n"
        "- Selalu cantumkan referensi [nomor] sesuai sumber."
    )

    resp = client.chat.completions.create(
        model=model,
        temperature=float(os.getenv("GROQ_TEMPERATURE", "0.35")),
        max_tokens=300,
        top_p=1.0,
        messages=[
            {"role": "system", "content": _SYS_PROMPT},
            {"role": "user", "content": user},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    cites = _parse_citation_indices(text)
    return {"answer": text, "used_model": model, "cites": cites}

# ===================== Sources projection =====================

def _project_sources(ctx: List[Dict], cite_indices: List[int]) -> List[Dict]:
    out = []
    for i, it in enumerate(ctx, start=1):
        out.append({
            "slot": i,
            "id": it.get("id"),
            "km": it.get("km"),
            "emb_dist": it.get("emb_dist"),
            "ce_score": it.get("ce_score"),
            "summary": it.get("summary"),
            "cited": (i in cite_indices),
        })
    return out

# ===================== Main entry =====================

def answer(db: Session, question: str, top_k: int = 5, include_sources: bool = True) -> Dict[str, Any]:
    # 1) Ambil konteks terbaik
    ctx = retriever.search_similar(db, question, top_k=top_k)

    # 2) Filter by km jika disebut di pertanyaan
    km_q = _extract_km_from_question(question)
    if km_q is not None:
        filtered = _filter_contexts_by_km(ctx, km_q, tol=0.3)
        if filtered:
            ctx = _unique_by_athlete(filtered)

    # 3) Jawab pakai Groq (dengan error handling)
    try:
        out = _llm_answer_groq(question, ctx)
    except Exception as e:
        logger.error("Groq API error: %s", e, exc_info=True)
        return {
            "question": question,
            "answer": f"Maaf, ada error saat menghubungi LLM: {str(e)}",
            "used_model": "llm-error",
            "sources": [],
        }

    # 4) Build payload
    payload: Dict[str, Any] = {
        "question": question,
        "answer": out["answer"],
        "used_model": out["used_model"],
    }
    if include_sources:
        payload["sources"] = _project_sources(ctx, out.get("cites", []))

    return payload
