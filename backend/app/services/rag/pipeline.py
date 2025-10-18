from typing import Dict, Any, Optional, Set, List
from app.core.logger import logger
from app.core.utils import timer
from app.services.rag.retriever import retrieve_context
from app.services.rag.answerer import answer_with_llm, _detect_month, _detect_year, _detect_member_from_query_or_ctx
from app.services.chroma.db_client import get_collection
from app.core.memory import get_session, update_session


@timer
def rag_answer(query: str, top_k: int = 5, member: str = None, month: int = None, year: int = None, session_id: str = None) -> Dict[str, Any]:
    """
    Pipeline lengkap:
    - retrieve konteks dari Chroma
    - jawab pakai LLM (opsional), fallback kalau tidak ada API key
    """
    try:
        # memory backfill
        sess = get_session(session_id)
        eff_member = member or sess.get("member")
        eff_month = month or sess.get("month")
        eff_year = year or sess.get("year")

        # If query clearly mentions another member, override memory for this turn
        try:
            # Collect known member names from collection
            names: Set[str] = set()
            col = get_collection()
            meta = col.get(where={}, include=["ids", "metadatas"], limit=10000)
            for md in (meta.get("metadatas") or []):
                if isinstance(md, dict) and md.get("member_name"):
                    names.add(str(md["member_name"]))
            for _id in (meta.get("ids") or []):
                if _id:
                    names.add(str(_id))
            qlow = (query or "").lower()
            detected_list: List[str] = [n for n in names if n and n.lower() in qlow]
            if len(detected_list) >= 2:
                eff_member = None
            elif len(detected_list) == 1:
                detected = detected_list[0]
                if not eff_member or detected.lower() != str(eff_member).lower():
                    eff_member = detected
        except Exception:
            pass

        ctx = retrieve_context(query, top_k=top_k, member=eff_member)
        answer, provider = answer_with_llm(query, ctx)

        # update memory from result
        try:
            target = _detect_member_from_query_or_ctx(query, ctx)
            detected_member = target[0] if target else eff_member
            detected_month = _detect_month(query) or eff_month
            detected_year = _detect_year(query) or eff_year
            update_session(session_id, member=detected_member, month=detected_month, year=detected_year, last_query=query)
        except Exception:
            pass
        return {
            "status": "ok",
            "query": query,
            # kembalikan filter yang sudah terselesaikan (post-detection)
            "filters": {"member": detected_member if 'detected_member' in locals() else eff_member, "month": detected_month if 'detected_month' in locals() else eff_month, "year": detected_year if 'detected_year' in locals() else eff_year},
            "provider": provider,
            "contexts": ctx,
            "answer": answer,
        }
    except Exception as e:
        logger.exception(f"rag_answer error: {e}")
        return {"status": "error", "query": query, "message": str(e)}
