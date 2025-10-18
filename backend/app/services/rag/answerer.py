from typing import List, Optional, Tuple, Dict, Any
from app.core.logger import logger
from app.core.config import settings
import re
from datetime import date
from app.services.rag.metrics import compute_leaderboard


# ===== Helpers & constants =====

_MONTHS_ID = {
    1: "januari", 2: "februari", 3: "maret", 4: "april",
    5: "mei", 6: "juni", 7: "juli", 8: "agustus",
    9: "september", 10: "oktober", 11: "november", 12: "desember",
}
_MONTHS_REV = {v: k for k, v in _MONTHS_ID.items()}
_MONTHS_REV.update({
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6, "jul": 7,
    "agu": 8, "sep": 9, "sept": 9, "okt": 10, "nov": 11, "des": 12,
})


def _detect_month(query: str) -> Optional[int]:
    q = (query or "").lower()
    m = re.search(r"\b(bulan|bln)\s*(1[0-2]|0?[1-9])\b", q)
    if m:
        return int(m.group(2))
    for name, num in _MONTHS_REV.items():
        if re.search(rf"\b{name}\b", q):
            return num
    return None


def _detect_year(query: str) -> Optional[int]:
    q = (query or "").lower()
    m = re.search(r"\b(tahun|thn)\s*(20\d{2})\b", q)
    if m:
        return int(m.group(2))
    m2 = re.search(r"\b(20\d{2})\b", q)
    if m2:
        return int(m2.group(1))
    return None


def _extract_member_names_from_ctx(ctxs: List[str]) -> Dict[int, str]:
    names: Dict[int, str] = {}
    for i, c in enumerate(ctxs, start=1):
        # Format 1 (per-member): "<Nama> melakukan beberapa aktivitas lari: - YYYY-MM-DD: ..."
        m1 = re.match(r"^([^:\n]+?)\s+melakukan\s+beberapa\s+aktivitas\s+lari\s*:\s*", c, flags=re.IGNORECASE)
        if m1:
            names[i] = m1.group(1).strip()
            continue
        # Format 2 (fallback, per-aktivitas lama): "<Nama>: YYYY-MM-DD: ..."
        m2 = re.match(r"^([^:\n]+?)\s*:\s*\d{4}-\d{2}-\d{2}\s*:\s*", c)
        if m2:
            names[i] = m2.group(1).strip()
    return names


def _detect_member_from_query_or_ctx(query: str, ctxs: List[str]) -> Optional[Tuple[str, int]]:
    names = _extract_member_names_from_ctx(ctxs)
    if not names:
        return None
    q = (query or "").lower()
    # Exact substring match
    for idx, name in names.items():
        if name.lower() in q:
            return (name, idx)
    # Token overlap match
    tokens = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 3]
    best, best_score, best_idx = None, 0, -1
    for idx, name in names.items():
        parts = [p for p in name.lower().split() if len(p) >= 3]
        score = sum(1 for p in parts if p in tokens)
        if score > best_score:
            best, best_score, best_idx = name, score, idx
    return (best, best_idx) if best else None


def _detect_two_members_from_query(query: str, ctxs: List[str]) -> Optional[List[Tuple[str, int]]]:
    names = _extract_member_names_from_ctx(ctxs)
    if not names:
        return None
    q = (query or "").lower()
    picks: List[Tuple[str, int]] = []
    # exact matches first
    for idx, name in names.items():
        if name.lower() in q:
            picks.append((name, idx))
    # if less than 2, try token overlap ranking
    if len(picks) < 2:
        tokens = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 3]
        scored = []
        for idx, name in names.items():
            parts = [p for p in name.lower().split() if len(p) >= 3]
            score = sum(1 for p in parts if p in tokens)
            if score > 0 and (name, idx) not in picks:
                scored.append(((name, idx), score))
        scored.sort(key=lambda x: x[1], reverse=True)
        for (item, _) in scored:
            if len(picks) >= 2:
                break
            picks.append(item)
    return picks[:2] if picks else None


def _sum_km_from_ctx_text(text: str, month: Optional[int] = None) -> Tuple[float, int]:
    total = 0.0
    count = 0
    for line in text.split(" - "):
        dm = re.search(r"(20\d{2})-(\d{2})-(\d{2})\s*:\s*", line)
        if dm:
            mm = int(dm.group(2))
            if month and mm != month:
                continue
        elif month is not None:
            # if month filtering but no date found on the line, skip
            continue
        m = re.search(r"sejauh\s+([0-9]+(?:[.,][0-9]+)?)\s*km", line, flags=re.IGNORECASE)
        if m:
            val = float(m.group(1).replace(",", "."))
            total += val
            count += 1
    return (round(total, 2), count)


def _detect_threshold_km(query: str) -> Optional[float]:
    q = (query or "").lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:k|km)\b", q)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except Exception:
            return None
    return None


def _any_run_ge_km(text: str, km: float, month: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    for line in text.split(" - "):
        dm = re.search(r"(20\d{2})-(\d{2})-(\d{2})\s*:\s*", line)
        if dm:
            mm = int(dm.group(2))
            if month and mm != month:
                continue
        elif month is not None:
            continue
        m = re.search(r"sejauh\s+([0-9]+(?:[.,][0-9]+)?)\s*km", line, flags=re.IGNORECASE)
        if m:
            val = float(m.group(1).replace(",", "."))
            if val >= km:
                return True, line.strip()
    return False, None


def _detect_intent(query: str) -> str:
    """Intent sederhana: 'threshold' | 'total' | 'compare' | 'generic'."""
    q = (query or "").lower()
    if re.search(r"\b(pernah|>=|lebih dari|minimal)\b", q) and re.search(r"\b\d+\s*(?:k|km)\b|\b10k\b", q):
        return "threshold"
    if re.search(r"\b(total|jumlah|akumulasi)\b", q) or re.search(r"\bberapa\s*(?:km|kilometer)\b", q):
        return "total"
    if re.search(r"\b(banding|vs|lebih\s+(?:jauh|banyak)|paling\s+(?:jauh|banyak)|terjauh)\b", q):
        return "compare"
    return "generic"


def _join_context(ctxs: List[str], max_chars: int = 6000) -> str:
    if not ctxs:
        return ""
    joined, total = [], 0
    for i, c in enumerate(ctxs, start=1):
        line = f"[{i}] {c}"
        if total + len(line) > max_chars:
            break
        joined.append(line)
        total += len(line)
    return "\n".join(joined)


def _build_prompts(query: str, ctx: str) -> Tuple[str, str]:
    system_prompt = (
        "Kamu adalah asisten untuk Apaan Yaa Running Club yang ramah, playful, dan relevan. "
        "Gunakan HANYA fakta dari 'Konteks'; boleh melakukan penalaran ringan (menjumlahkan, membandingkan) berbasis data. "
        "Jika data tidak ada di konteks, jelaskan dengan jujur dan tawarkan pertanyaan klarifikasi singkat. "
        "Selalu sertakan rujukan [nomor] pada fakta utama."
    )
    user_prompt = f"Konteks:\n{ctx}\n\nPertanyaan: {query}"
    return system_prompt, user_prompt


def _build_guarded_prompt(query: str, ctx: str, facts: str) -> Tuple[str, str]:
    system_prompt = (
        "Kamu adalah asisten Apaan Yaa. Jawab dengan ramah dan faktual. "
        "Gunakan HANYA data pada KONTEKS dan FAKTA berikut. Jangan mengubah angka pada FAKTA. "
        "Jika data tidak memadai, katakan terus terang dan tawarkan langkah lanjut yang spesifik. "
        "Sertakan rujukan [nomor] saat menyebut fakta dari konteks."
    )
    user_prompt = (
        f"KONTEKS:\n{ctx}\n\n"
        f"FAKTA (boleh dirujuk, JANGAN ubah angka):\n{facts}\n\n"
        f"PERTANYAAN: {query}"
    )
    return system_prompt, user_prompt


def _call_openai(prompt: Tuple[str, str], model: str) -> Optional[str]:
    try:
        import os
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": prompt[0]}, {"role": "user", "content": prompt[1]}],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"OpenAI call failed: {e}")
        return None


def _call_groq(prompt: Tuple[str, str], model: str) -> Optional[str]:
    try:
        import os
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": prompt[0]}, {"role": "user", "content": prompt[1]}],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Groq call failed: {e}")
        return None


def answer_with_llm(query: str, contexts: List[str]) -> Tuple[str, str]:
    """
    Jawab berbasis konteks. Jika LLM tersedia, biarkan LLM menyusun jawaban natural
    dengan guardrails: hanya pakai data dari konteks + fakta yang dihitung. Fallback
    deterministik jika LLM tidak tersedia.

    Return: (answer, provider)
    """
    intent = _detect_intent(query)

    # Untuk compare: jangan sempitkan konteks. Selain itu, fokuskan ke member yang disebut.
    narrowed_contexts = contexts
    if intent != "compare":
        m = None
        try:
            m = _detect_member_from_query_or_ctx(query, contexts)
        except Exception:
            m = None
        if m:
            name, idx = m
            if 1 <= idx <= len(contexts):
                narrowed_contexts = [contexts[idx - 1]]

    ctx_text = _join_context(narrowed_contexts)
    if not ctx_text:
        return ("Maaf, aku tidak menemukan data relevan di basis data. Coba refresh dulu ya.", "none")

    provider = getattr(settings, "LLM_PROVIDER", "none").lower()

    # ===== Deterministic calculations (as facts) =====
    month = _detect_month(query)
    year = _detect_year(query)  # belum dipakai secara khusus pada parsing, tapi tetap dideteksi

    facts_lines: List[str] = []
    if intent in ("total", "compare"):
        # cari hingga 2 member untuk disajikan sebagai fakta
        duo = _detect_two_members_from_query(query, contexts) if intent == "compare" else None
        targets: List[Tuple[str, int]] = []
        if duo and len(duo) >= 2:
            targets = [duo[0], duo[1]]
        else:
            one = _detect_member_from_query_or_ctx(query, contexts)
            if one:
                targets = [one]

        for (member, idx) in targets:
            text = contexts[idx - 1] if 1 <= idx <= len(contexts) else contexts[0]
            total_km, n = _sum_km_from_ctx_text(text, month=month)
            tag = f"bulan {_MONTHS_ID.get(month)}" if month else "semua"
            facts_lines.append(f"- {member}: total {total_km:.2f} km ({tag}), {n} aktivitas. Rujukan: [{idx}]")

    if intent == "threshold":
        one = _detect_member_from_query_or_ctx(query, contexts)
        thr = _detect_threshold_km(query)
        if one and thr is not None:
            member, idx = one
            text = contexts[idx - 1] if 1 <= idx <= len(contexts) else contexts[0]
            ok, example = _any_run_ge_km(text, thr, month=month)
            tag = f" di bulan {_MONTHS_ID.get(month)}" if month else ""
            if ok:
                facts_lines.append(f"- {member} pernah ≥ {thr:.2f} km{tag}. Contoh: {example} (rujukan [{idx}])")
            else:
                facts_lines.append(f"- {member} belum mencapai {thr:.2f} km{tag} (berdasarkan konteks) (rujukan [{idx}])")

    facts_text = "\n".join(facts_lines) if facts_lines else "(tidak ada fakta hitungan yang relevan)"

    # ===== Use LLM when available =====
    if provider in ("groq", "openai"):
        if intent in ("total", "compare", "threshold") and facts_text:
            prompt = _build_guarded_prompt(query, ctx_text, facts_text)
            out = _call_groq(prompt, getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")) if provider == "groq" else _call_openai(prompt, getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"))
            if out:
                return (out, f"{provider}:{getattr(settings, 'GROQ_MODEL' if provider=='groq' else 'OPENAI_MODEL', '')}")
        else:
            prompt = _build_prompts(query, ctx_text)
            out = _call_groq(prompt, getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")) if provider == "groq" else _call_openai(prompt, getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"))
            if out:
                return (out, f"{provider}:{getattr(settings, 'GROQ_MODEL' if provider=='groq' else 'OPENAI_MODEL', '')}")

    # ===== Fallback deterministic answers =====
    if intent == "threshold":
        one = _detect_member_from_query_or_ctx(query, contexts)
        thr = _detect_threshold_km(query)
        if one and thr is not None:
            member, idx = one
            text = contexts[idx - 1] if 1 <= idx <= len(contexts) else contexts[0]
            ok, example = _any_run_ge_km(text, thr, month=month)
            if ok:
                ex = f" Contoh: {example}" if example else ""
                return (f"Ya, {member} pernah ≥ {thr:.2f} km.{ex} Rujukan: [{idx}]", "calc")
            else:
                return (f"Sejauh konteks yang ada, {member} belum mencapai {thr:.2f} km. Rujukan: [{idx}]", "calc")

    if intent == "total":
        one = _detect_member_from_query_or_ctx(query, contexts)
        if one:
            member, idx = one
            text = contexts[idx - 1] if 1 <= idx <= len(contexts) else contexts[0]
            total_km, n = _sum_km_from_ctx_text(text, month=month)
            tag = f"bulan {_MONTHS_ID.get(month)}" if month else "semua di konteks"
            return (f"Total jarak lari {member} pada {tag}: {total_km:.2f} km (dari {n} aktivitas). Rujukan: [{idx}]", "calc")

    if intent == "compare":
        duo = _detect_two_members_from_query(query, contexts)
        if duo and len(duo) >= 2:
            (m1, i1), (m2, i2) = duo[0], duo[1]
            t1, n1 = _sum_km_from_ctx_text(contexts[i1 - 1], month=month)
            t2, n2 = _sum_km_from_ctx_text(contexts[i2 - 1], month=month)
            if n1 + n2 > 0:
                who = m1 if t1 >= t2 else m2
                diff = round(abs(t1 - t2), 2)
                per = f"bulan {_MONTHS_ID.get(month)}" if month else "periode yang ada di konteks"
                return (f"Perbandingan {per}: {m1} {t1:.2f} km (rujukan [{i1}]) vs {m2} {t2:.2f} km (rujukan [{i2}]). Lebih jauh: {who} (+{diff:.2f} km).", "calc")
        else:
            # Jika user minta 'leader/siapa paling jauh' tanpa menyebut dua nama, gunakan leaderboard all‑time
            scope = "all"
            board = compute_leaderboard(scope=scope)
            if board:
                top = board[0]
                # Cari rujukan indeks untuk top (ambil pertama yang cocok di contexts)
                ref_idx = None
                names = _extract_member_names_from_ctx(contexts)
                for idx, nm in names.items():
                    if nm.lower() == top["member"].lower():
                        ref_idx = idx
                        break
                ref_txt = f" (rujukan [{ref_idx}])" if ref_idx else ""
                return (f"Leader (all‑time) berdasarkan total jarak: {top['member']} {top['total_km']:.2f} km dengan {top['activities']} aktivitas{ref_txt}.", "calc")

    # Generic fallback
    preview = (narrowed_contexts[0] if narrowed_contexts else "")[:220].replace("\n", " ")
    answer = (
        "Halo! Dari konteks yang ada, ini cuplikan singkat:\n"
        f"{preview} ...\n"
        "Mau aku bantu ringkas aktivitas member tertentu atau cari rekap terbaru?"
    )
    return (answer, "fallback")
