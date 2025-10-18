from typing import List, Optional, Set
from app.core.logger import logger
from app.core.utils import clean_text
from app.services.chroma.db_client import get_collection
from app.services.chroma.embeddings import embed_texts
import re


def _normalize_query(q: str) -> str:
    """
    Normalisasi ringan untuk query user agar retrieval stabil.
    """
    q = clean_text(q or "")
    # Normalisasi bulan angka -> nama (Indonesia), contoh: "bulan 9" -> "september"
    months = {
        1: "januari", 2: "februari", 3: "maret", 4: "april",
        5: "mei", 6: "juni", 7: "juli", 8: "agustus",
        9: "september", 10: "oktober", 11: "november", 12: "desember",
    }
    m = re.search(r"\b(bulan|bln)\s*(1[0-2]|0?[1-9])\b", q, flags=re.IGNORECASE)
    if m:
        num = int(m.group(2))
        q = re.sub(r"\b(bulan|bln)\s*(1[0-2]|0?[1-9])\b", months.get(num, str(num)), q, flags=re.IGNORECASE)
    # Normalisasi singkat: sept -> september, okt -> oktober, dst.
    short_map = {
        r"\bsept\b": "september",
        r"\bokt\b": "oktober",
        r"\bnov\b": "november",
        r"\bdes\b": "desember",
    }
    for pat, rep in short_map.items():
        q = re.sub(pat, rep, q, flags=re.IGNORECASE)
    return q


def _collect_member_names() -> Set[str]:
    try:
        collection = get_collection()
        # ChromaDB: do not include "ids" explicitly; ids are always returned
        data = collection.get(where={}, include=["metadatas"], limit=10000)
        names: Set[str] = set()
        # from metadatas
        for md in (data.get("metadatas") or []):
            if isinstance(md, dict) and md.get("member_name"):
                names.add(str(md["member_name"]))
        # also consider ids (doc_id == member_name in our index)
        for _id in (data.get("ids") or []):
            if _id:
                names.add(str(_id))
        return names
    except Exception:
        return set()


def _detect_member_in_query(query: str, member_names: Set[str]) -> Optional[str]:
    q = (query or "").lower()
    q = re.sub(r"\s+", " ", q).strip()
    if not q or not member_names:
        return None

    # Exact substring match first
    for name in member_names:
        if name.lower() in q:
            return name

    # Token-based loose match (any token >=3 chars)
    tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", q) if len(t) >= 3]
    best = None
    best_score = 0
    for name in member_names:
        parts = [p for p in name.lower().split() if len(p) >= 3]
        score = sum(1 for p in parts if p in tokens)
        if score > best_score:
            best_score = score
            best = name
    return best if best_score > 0 else None


def retrieve_context(query: str, top_k: int = 5, member: Optional[str] = None, month: Optional[int] = None, year: Optional[int] = None) -> List[str]:
    """
    Ambil dokumen paling relevan dari Chroma berdasarkan query.
    Aman untuk kondisi:
    - collection kosong
    - embedding gagal
    - hasil kosong
    """
    try:
        q = _normalize_query(query)
        if not q:
            logger.warning("Query kosong saat retrieve_context.")
            return []

        # Detect target member early (explicit param takes precedence)
        member_names = _collect_member_names()
        target_member = None
        if member:
            mnorm = member.strip().lower()
            # exact match by available names (ids/metadatas)
            for name in member_names:
                if name.lower() == mnorm:
                    target_member = name
                    break
            if not target_member:
                target_member = _detect_member_in_query(member, member_names)
        if not target_member:
            target_member = _detect_member_in_query(q, member_names)
        q_for_embed = f"{q} {target_member}" if target_member else q

        q_embs = embed_texts([q_for_embed])
        if not q_embs:
            logger.error("Gagal membuat embedding untuk query.")
            return []

        collection = get_collection()
        # kalau koleksi masih kosong, .count() bisa nol
        try:
            if collection.count() == 0:
                logger.warning("Koleksi Chroma kosong.")
                return []
        except Exception:
            # beberapa versi Chroma punya behavior berbeda
            logger.warning("Tidak bisa membaca jumlah dokumen koleksi.")

        # Build operator-style where (Chroma v1+). Note: per-member index only has member_name metadata.
        where = None
        if target_member:
            where = {"member_name": {"$eq": target_member}}

        results = collection.query(
            query_embeddings=q_embs,
            n_results=max(1, top_k),
            **({"where": where} if where else {}),
        )

        docs = results.get("documents", [[]])
        docs = docs[0] if docs else []
        docs = [d for d in docs if d]

        # Name-aware retrieval: if query mentions a member, include ONLY that member's doc to avoid mixing
        if target_member:
            # First, try to fetch by ID (since our doc_id equals member_name)
            got = collection.get(ids=[target_member], include=["documents"], limit=1)
            docs2 = (got.get("documents") or [])
            if not docs2:
                # Fallback to a filtered semantic query (in case of collection backend specifics)
                try:
                    filtered = collection.query(
                        query_embeddings=q_embs,
                        n_results=max(1, top_k),
                        where={"member_name": {"$eq": target_member}},
                    )
                    docs2 = filtered.get("documents", [[]])
                    docs2 = docs2[0] if docs2 else []
                    docs2 = [d for d in docs2 if d]
                except Exception:
                    docs2 = []

            # Use only the member-specific docs to keep context focused
            docs = [d for d in docs2 if d][: max(1, top_k)]

        logger.info(f"retrieve_context: ditemukan {len(docs)} dokumen.")
        return docs

    except Exception as e:
        logger.exception(f"retrieve_context error: {e}")
        return []
