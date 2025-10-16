from typing import List, Optional, Tuple, Dict, Any
from app.core.logger import logger
from app.core.config import settings
import re


# ===== Deterministic helpers for precise, grounded answers =====

_MONTHS_ID = {
    1: "januari", 2: "februari", 3: "maret", 4: "april",
    5: "mei", 6: "juni", 7: "juli", 8: "agustus",
    9: "september", 10: "oktober", 11: "november", 12: "desember",
}
_MONTHS_REV = {v: k for k, v in _MONTHS_ID.items()}
_MONTHS_REV.update({
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6, "jul": 7,
    "agu": 8, "sept": 9, "sep": 9, "okt": 10, "nov": 11, "des": 12,
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


def _detect_intent(query: str) -> str:
    """Intent sederhana: 'threshold' | 'total' | 'compare' | 'generic'."""
    q = (query or "").lower()
    # threshold (pernah >= N km? 10k?)
    if re.search(r"\b(pernah|>=|lebih dari|minimal)\b", q) and re.search(r"\b\d+\s*(?:k|km)\b|\b10k\b", q):
        return "threshold"
    # total
    if re.search(r"\b(total|jumlah|akumulasi)\b", q) or re.search(r"\bberapa\s*(?:km|kilometer)\b", q):
        return "total"
    # compare
    if re.search(r"\b(banding|vs|lebih\s+(?:jauh|banyak))\b", q):
        return "compare"
    return "generic"


def _extract_member_names_from_ctx(ctxs: List[str]) -> Dict[int, str]:
    names = {}
    for i, c in enumerate(ctxs, start=1):
        # Format 1 (per-member): "<Nama> melakukan beberapa aktivitas lari: - YYYY-MM-DD: ..."
        m1 = re.match(r"^([^:\n]+?)\s+melakukan\s+beberapa\s+aktivitas\s+lari\s*:\s*", c, flags=re.IGNORECASE)
        if m1:
            names[i] = m1.group(1).strip()
            continue
        # Format 2 (per-aktivitas): "<Nama>: YYYY-MM-DD: <aktivitas> sejauh X km ..."
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
        # Cari tanggal di prefix "YYYY-MM-DD:"
        dm = re.search(r"(20\d{2})-(\d{2})-(\d{2})\s*:\s*", line)
        if dm:
            mm = int(dm.group(2))
            if month and mm != month:
                continue
        elif month is not None:
            # Jika filter bulan diminta tapi tanggal tidak ditemukan → skip
            continue
        m = re.search(r"sejauh\s+([0-9]+(?:[.,][0-9]+)?)\s*km", line, flags=re.IGNORECASE)
        if m:
            val = float(m.group(1).replace(",", "."))
            total += val
            count += 1
    return (round(total, 2), count)


def _detect_threshold_km(query: str) -> Optional[float]:
    q = (query or "").lower()
    # examples: "pernah 10 km", "udah 5k?", "pernah lari >= 10?"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:km|k\b)", q)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except Exception:
            return None
    return None


def _any_run_ge_km(text: str, km: float, month: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    # returns (found, example_line)
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


def _join_context(ctxs: List[str], max_chars: int = 6000) -> str:
    """
    Gabungkan konteks, batasi panjang supaya aman untuk LLM.
    """
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
    """
    Bangun sepasang (system_prompt, user_prompt) agar gaya lebih terkontrol:
    - Nada: ramah, playful, tapi tetap faktual dan ringkas.
    - Batasan: hanya gunakan data pada konteks. Selalu beri referensi [n].
    - Jika pertanyaan generik (mis. salam), balas hangat + ajukan pertanyaan klarifikasi
      dan tawarkan opsi terkait data pada konteks (tanpa mengarang fakta baru).
    """
    system_prompt = (
        "Kamu adalah asisten untuk Apaan Yaa Running Club yang ramah, playful, dan relevan. "
        "Jawab SINGKAT (1–3 kalimat), dengan bahasa Indonesia santai. "
        "Gunakan HANYA fakta dari 'Konteks'; boleh melakukan penalaran ringan (menjumlahkan, membandingkan) berbasis data. "
        "Jika data tidak ada di konteks: jelaskan dengan jujur dan tawarkan langkah lanjut/pertanyaan klarifikasi. "
        "Selalu sertakan rujukan [nomor] pada fakta utama. "
        "Jika ambigu (beberapa kandidat member/periode), ajukan SATU pertanyaan klarifikasi singkat."
    )

    user_prompt = (
        f"Konteks:\n{ctx}\n\n"
        f"Pertanyaan: {query}"
    )
    return system_prompt, user_prompt


def _call_openai(prompt: Tuple[str, str], model: str) -> Optional[str]:
    try:
        import os
        from openai import OpenAI  # openai>=1.x
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY tidak ditemukan. Melewati OpenAI.")
            return None
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt[0]},
                {"role": "user", "content": prompt[1]},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except ImportError:
        logger.warning("Paket openai belum terpasang. `pip install openai` jika perlu.")
    except Exception as e:
        logger.exception(f"Error panggil OpenAI: {e}")
    return None


def _call_groq(prompt: Tuple[str, str], model: str) -> Optional[str]:
    try:
        import os
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY tidak ditemukan. Melewati Groq.")
            return None
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt[0]},
                {"role": "user", "content": prompt[1]},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except ImportError:
        logger.warning("Paket groq belum terpasang. `pip install groq` jika perlu.")
    except Exception as e:
        logger.exception(f"Error panggil Groq: {e}")
    return None


def answer_with_llm(query: str, contexts: List[str]) -> Tuple[str, str]:
    """
    Menghasilkan jawaban berbasis konteks.
    Urutan preferensi:
    1) GROQ (jika GROQ_API_KEY + model tersedia di config)
    2) OPENAI (jika OPENAI_API_KEY + model tersedia di config)
    3) Fallback: format jawaban ringkas dari konteks (tanpa LLM)

    Return: (answer, provider)
    """
    # Fokus konteks ke member yang disebut jika bisa dideteksi
    narrowed_contexts = contexts
    try:
        m = _detect_member_from_query_or_ctx(query, contexts)
        if m:
            name, idx = m
            narrowed_contexts = [contexts[idx - 1]]
    except Exception:
        pass

    ctx_text = _join_context(narrowed_contexts)
    if not ctx_text:
        return (
            "Maaf, aku tidak menemukan data relevan di basis data. Coba refresh dulu ya.",
            "none",
        )

    # Intent gating: jika pertanyaan bersifat non-numerik/generik, langsung gunakan LLM
    try:
        intent_q = (query or "").lower()
        is_threshold = bool(re.search(r"\b(pernah|>=|lebih dari|minimal)\b", intent_q) and re.search(r"\b\d+\s*(?:k|km)\b|\b10k\b", intent_q))
        is_total = bool(re.search(r"\b(total|jumlah|akumulasi)\b", intent_q) or re.search(r"\bberapa\s*(?:km|kilometer)\b", intent_q))
        is_compare = bool(re.search(r"\b(banding|vs|lebih\s+(?:jauh|banyak))\b", intent_q))
        if not (is_threshold or is_total or is_compare):
            system_user = _build_prompts(query, ctx_text)
            # 1) Groq jika ada
            if getattr(settings, "LLM_PROVIDER", "none").lower() == "groq":
                model = getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")
                out = _call_groq(system_user, model)
                if out:
                    return (out, f"groq:{model}")
            # 2) OpenAI jika ada
            if getattr(settings, "LLM_PROVIDER", "none").lower() == "openai":
                model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
                out = _call_openai(system_user, model)
                if out:
                    return (out, f"openai:{model}")
    except Exception:
        pass

    # Jika pertanyaan generik (non‑numerik), langsung pakai LLM biar leluasa namun tetap on‑context
    intent = _detect_intent(query)
    if intent == "generic":
        system_user = _build_prompts(query, ctx_text)
        if getattr(settings, "LLM_PROVIDER", "none").lower() == "groq":
            model = getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")
            out = _call_groq(system_user, model)
            if out:
                return (out, f"groq:{model}")
        if getattr(settings, "LLM_PROVIDER", "none").lower() == "openai":
            model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
            out = _call_openai(system_user, model)
            if out:
                return (out, f"openai:{model}")
        # fallback
        preview = (narrowed_contexts[0] if narrowed_contexts else "")[:220].replace("\n", " ")
        answer = (
            "Aku belum menemukan datanya di konteks. "
            "Coba sebutkan member/periode yang kamu maksud, atau tanya total/rekap.\n"
            f"Cuplikan konteks: {preview} ..."
        )
        return (answer, "fallback")

    # Binary threshold question handler: "pernah 10 km?"
    try:
        target = _detect_member_from_query_or_ctx(query, narrowed_contexts)
        month = _detect_month(query)
        thr = _detect_threshold_km(query)
        if target and thr is not None:
            member, idx = target
            member_ctx = narrowed_contexts[idx - 1] if idx - 1 < len(narrowed_contexts) else narrowed_contexts[0]
            ok, example = _any_run_ge_km(member_ctx, thr, month=month)
            if ok:
                mon_txt = f" pada bulan {_MONTHS_ID.get(month)}" if month else ""
                ex = f" Contoh: {example}" if example else ""
                return (f"Ya, {member} pernah ≥ {thr:.2f} km{mon_txt}.{ex} Rujukan: [{idx}]", "calc")
            else:
                mon_txt = f" pada bulan {_MONTHS_ID.get(month)}" if month else ""
                return (f"Sejauh konteks yang ada, {member} belum mencapai {thr:.2f} km{mon_txt}. Rujukan: [{idx}]", "calc")
    except Exception as e:
        logger.warning(f"Threshold check gagal: {e}")

    # Deterministic calculation path for queries like "total berapa km ..." → paling akurat
    try:
        target = _detect_member_from_query_or_ctx(query, narrowed_contexts)
        month = _detect_month(query)
        year = _detect_year(query)
        if target:
            member, idx = target
            # Pakai konteks index milik member saja supaya ringkas dan akurat
            member_ctx = narrowed_contexts[idx - 1] if idx - 1 < len(narrowed_contexts) else narrowed_contexts[0]
            # Year filter: konteks kita mengandung tahun di tanggal, jadi cukup filter via bulan saja di sum;
            # untuk tahun, jika disebut dan tidak cocok di konteks, hasil bisa nol (itu benar secara data).
            total_km, n = _sum_km_from_ctx_text(member_ctx, month=month)
            if n > 0:
                if month:
                    mon_name = _MONTHS_ID.get(month, str(month))
                    period = f"bulan {mon_name}"
                    if year:
                        period += f" {year}"
                    ans = (
                        f"Total jarak lari {member} pada {period}: {total_km:.2f} km "
                        f"(dari {n} aktivitas). Rujukan: [{idx}]"
                    )
                else:
                    ans = (
                        f"Total jarak lari {member} (semua di konteks): {total_km:.2f} km "
                        f"(dari {n} aktivitas). Rujukan: [{idx}]"
                    )
                return (ans, "calc")

        # Comparison: two members mentioned
        duo = _detect_two_members_from_query(query, contexts)
        if duo and len(duo) >= 2:
            (m1, i1), (m2, i2) = duo[0], duo[1]
            t1, n1 = _sum_km_from_ctx_text(contexts[i1 - 1], month=_detect_month(query))
            t2, n2 = _sum_km_from_ctx_text(contexts[i2 - 1], month=_detect_month(query))
            if n1 + n2 > 0:
                who = m1 if t1 >= t2 else m2
                diff = round(abs(t1 - t2), 2)
                mon = _MONTHS_ID.get(_detect_month(query), None)
                per = f"bulan {mon}" if mon else "periode yang ada di konteks"
                ans = (
                    f"Perbandingan {per}: {m1} {t1:.2f} km (rujukan [{i1}]) vs {m2} {t2:.2f} km (rujukan [{i2}]). "
                    f"Lebih jauh: {who} (+{diff:.2f} km)."
                )
                return (ans, "calc")
    except Exception as e:
        logger.warning(f"Deterministic calc gagal, lanjut ke LLM: {e}")

    system_user = _build_prompts(query, ctx_text)

    # 1) Groq dulu jika dikonfigurasi
    if getattr(settings, "LLM_PROVIDER", "none").lower() == "groq":
        model = getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")
        out = _call_groq(system_user, model)
        if out:
            return (out, f"groq:{model}")

    # 2) OpenAI jika dikonfigurasi
    if getattr(settings, "LLM_PROVIDER", "none").lower() == "openai":
        model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
        out = _call_openai(system_user, model)
        if out:
            return (out, f"openai:{model}")

    # 3) Fallback: no external LLM
    # Ambil highlight dari konteks untuk jawaban singkat
    preview = (contexts[0] if contexts else "")[:220].replace("\n", " ")
    answer = (
        "Halo! Dari konteks yang ada, ini cuplikan singkat:\n"
        f"{preview} ...\n"
        "Mau aku bantu ringkas aktivitas member tertentu atau cari rekap terbaru?"
    )
    return (answer, "fallback")
