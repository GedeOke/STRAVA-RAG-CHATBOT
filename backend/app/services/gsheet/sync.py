import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import json
from pathlib import Path
from app.core.config import settings
from app.core.logger import logger
from app.core.utils import md5_hash, timer
from app.services.chroma.embeddings import embed_texts
from app.services.chroma.manager import upsert_document
from app.core.utils import clean_text


# ==================================================
# Load Google Sheet Client
# ==================================================
def get_gsheet_client():
    """Inisialisasi koneksi Google Sheet API."""
    try:
        # Jika GSHEET_ID diberikan, kita bisa pakai scope spreadsheets saja (tanpa Drive API)
        if getattr(settings, "GSHEET_ID", "").strip():
            scope = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
            ]
        else:
            # open by name butuh Drive API untuk menemukan sheet
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]

        # Resolve credential path robustly (support running from repo root or backend/)
        cred_candidate = Path(settings.GSHEET_CRED_FILE)
        if not cred_candidate.is_file():
            # try relative to CWD
            rel1 = Path.cwd() / settings.GSHEET_CRED_FILE
            # try inside backend/
            rel2 = Path.cwd() / "backend" / settings.GSHEET_CRED_FILE
            # try next to this file's backend folder
            rel3 = Path(__file__).resolve().parents[3] / settings.GSHEET_CRED_FILE  # backend/
            for p in (rel1, rel2, rel3):
                if p.is_file():
                    cred_candidate = p
                    break

        if not cred_candidate.is_file():
            raise FileNotFoundError(
                f"File kredensial '{settings.GSHEET_CRED_FILE}' tidak ditemukan. Coba set path lengkap atau letakkan di 'backend/'."
            )

        creds = ServiceAccountCredentials.from_json_keyfile_name(str(cred_candidate), scope)
        client = gspread.authorize(creds)
        if getattr(settings, "GSHEET_ID", "").strip():
            logger.info("Koneksi ke Google Sheets API berhasil (mode by_key, tanpa Drive API).")
        else:
            logger.info(f"Koneksi ke Google Sheet '{settings.GSHEET_NAME}' berhasil (requires Drive API).")
        return client

    except Exception as e:
        logger.exception(f"Gagal konek ke Google Sheet: {e}")
        raise e


# ==================================================
# Build Text per Member (aggregated)
# ==================================================
def build_member_texts(df: pd.DataFrame):
    """
    Gabungkan semua aktivitas per member jadi satu teks panjang.
    Contoh:
    Yoga Setiyawan melakukan beberapa aktivitas lari:
    - 2025-07-20: Berlari Pagi sejauh 3 km ...
    """
    grouped = df.groupby("member_name")
    docs = []

    for name, group in grouped:
        activities = "\n".join(
            f"- {r.date}: {r.activity_name} sejauh {r.distance_km} km "
            f"(pace {r.avg_pace}, waktu {r.moving_time}, elevasi {r.elevation_gain_m} m)"
            for r in group.itertuples()
        )
        text = f"{name} melakukan beberapa aktivitas lari:\n{activities}"
        docs.append({"member_name": str(name).strip(), "text": clean_text(text)})
    return docs


# ==================================================
# Main Sync Function
# ==================================================
@timer
def sync_gsheet_to_chroma():
    """
    Sinkronisasi data dari Google Sheet ke ChromaDB.
    - Update per member_name (entitas)
    - Skip kalau data member belum berubah
    """
    try:
        client = get_gsheet_client()
        if getattr(settings, "GSHEET_ID", "").strip():
            sheet = client.open_by_key(settings.GSHEET_ID).worksheet(settings.GSHEET_TAB)
        else:
            sheet = client.open(settings.GSHEET_NAME).worksheet(settings.GSHEET_TAB)
        data = sheet.get_all_records()

        if not data:
            logger.warning("Tidak ada data di Google Sheet.")
            return {"updated": 0, "skipped": 0}

        df = pd.DataFrame(data)
        member_docs = build_member_texts(df)

        # cache hash buat deteksi perubahan
        CACHE_PATH = "./cache/cache_hash.json"
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r") as f:
                cache_hash = json.load(f)
        else:
            cache_hash = {}

        updated, skipped = 0, 0

        # loop tiap member
        for doc in member_docs:
            text_hash = md5_hash(doc["text"])
            name = doc["member_name"]

            if cache_hash.get(name) != text_hash:
                embeddings = embed_texts([doc["text"]])
                if embeddings:
                    upsert_document(
                        doc_id=name,
                        text=doc["text"],
                        embedding=embeddings[0],
                        metadata={"member_name": name},
                    )
                    cache_hash[name] = text_hash
                    updated += 1
            else:
                skipped += 1

        with open(CACHE_PATH, "w") as f:
            json.dump(cache_hash, f, indent=2)

        logger.info(f"Sinkronisasi selesai - updated: {updated}, skipped: {skipped}")
        return {"updated": updated, "skipped": skipped}

    except Exception as e:
        logger.exception(f"Gagal sinkronisasi: {e}")
        return {"status": "error", "message": str(e)}
